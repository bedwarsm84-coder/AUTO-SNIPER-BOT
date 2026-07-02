"""
cogs/tracking.py
Spieler-Beobachtung: periodischer Stats-Vergleich + Discord-Meldung bei Aenderung.

Upgrade:
 - Kuerzeres Standard-Intervall (siehe README fuer Rate-Limit-Hinweis ohne API-Key)
 - Requests werden ueber das Intervall gestaffelt (kein Burst aller Spieler gleichzeitig)
 - Alerts gruppieren nach Spiel UND Modus (Solo/Duos/Squads/Mega), zeigen KD-Aenderung

Wichtig: Das ist weiterhin KEIN Live-Online-Status. Die Hive-API bietet das nicht.
Ein "Runde beendet"-Alert ist ein verzoegerter Hinweis anhand gestiegener Stat-Werte.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import storage
from cogs.stats import GAME_NAMES
from formatting import (
    label_for_key, compute_kd, split_game_mode, is_excluded,
    leaf_stat_dicts, extract_wins_played, update_streak,
)
from hive_api import HiveAPIError

log = logging.getLogger("hivebot.tracking")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "45"))
DEFAULT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID", "0")) or None


def diff_stats(old, new, path: str = "") -> list[tuple[str, float, float]]:
    """Findet alle numerischen Felder, die in `new` hoeher sind als in `old`."""
    changes: list[tuple[str, float, float]] = []
    if not isinstance(new, dict):
        return changes
    for key, new_val in new.items():
        if is_excluded(key):
            continue
        old_val = old.get(key) if isinstance(old, dict) else None
        full_path = f"{path}.{key}" if path else key
        if isinstance(new_val, dict):
            changes.extend(diff_stats(old_val or {}, new_val, full_path))
        elif isinstance(new_val, (int, float)) and not isinstance(new_val, bool):
            old_num = old_val if isinstance(old_val, (int, float)) and not isinstance(old_val, bool) else 0
            if new_val > old_num:
                changes.append((full_path, old_num, new_val))
    return changes


def _find_stats_dict(data: dict, path_prefix: str) -> dict | None:
    """Navigiert im Stats-Dict entlang eines Pfad-Prefixes wie 'bed.solo'."""
    node = data
    for part in path_prefix.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


class TrackingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hive = bot.hive
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    @app_commands.command(description="Beobachtet einen Spieler: meldet in diesem Kanal, wenn sich Stats aendern")
    @app_commands.describe(name="Minecraft-Bedrock-Name")
    async def track(self, interaction: discord.Interaction, name: str):
        ok = storage.add_player(name, interaction.channel_id)
        if ok:
            await interaction.response.send_message(
                f"✅ `{name}` wird jetzt beobachtet (Check alle ~{POLL_INTERVAL}s, gestaffelt).\n"
                f"⚠️ Kein Live-Online-Status möglich – nur verzögerte Meldung bei Stats-Erhöhung."
            )
        else:
            await interaction.response.send_message(f"`{name}` wird bereits beobachtet.")

    @app_commands.command(description="Beendet die Beobachtung eines Spielers")
    @app_commands.describe(name="Minecraft-Bedrock-Name")
    async def untrack(self, interaction: discord.Interaction, name: str):
        ok = storage.remove_player(name)
        await interaction.response.send_message("✅ Entfernt." if ok else f"`{name}` war nicht in der Liste.")

    @app_commands.command(description="Listet aktuell beobachtete Spieler auf")
    async def tracked(self, interaction: discord.Interaction):
        players = storage.get_players()
        if not players:
            await interaction.response.send_message("Aktuell wird niemand beobachtet.")
            return
        names = ", ".join(p["display_name"] for p in players.values())
        await interaction.response.send_message(f"Beobachtet: {names}")

    @app_commands.command(description="Zeigt die aktuell mitgezählten Live-Winstreaks eines beobachteten Spielers")
    @app_commands.describe(name="Minecraft-Bedrock-Name")
    async def streak(self, interaction: discord.Interaction, name: str):
        streaks = storage.get_streaks(name)
        if not streaks:
            await interaction.response.send_message(
                f"Noch keine Streak-Daten für `{name}`. Erst `/track` starten und einen Poll-Zyklus abwarten."
            )
            return
        embed = discord.Embed(title=f"🔥 Live-Winstreaks: {name}", color=0xE67E22,
                               description="Selbst mitgezählt (Hive liefert keinen Winstreak über die API).")
        for streak_key, value in streaks.items():
            game_key, _, mode_label = streak_key.partition("|")
            label = GAME_NAMES.get(game_key, game_key)
            if mode_label:
                label += f" · {mode_label}"
            embed.add_field(name=label, value=f"🔥 **{value}**", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Zeigt an, ob ein beobachteter Spieler kürzlich aktiv war (basiert auf Stats-Änderungen, kein echter Live-Status)")
    @app_commands.describe(name="Minecraft-Bedrock-Name")
    async def online(self, interaction: discord.Interaction, name: str):
        last_active_iso = storage.get_last_active(name)
        if last_active_iso is None:
            await interaction.response.send_message(
                f"Für `{name}` liegt noch keine Aktivitätsdaten vor. "
                f"Erst `/track` starten und einen Poll-Zyklus abwarten – oder es gab bisher keine erkannte Stats-Änderung."
            )
            return

        last_active = datetime.fromisoformat(last_active_iso)
        now = datetime.now(timezone.utc)
        delta = now - last_active
        minutes = int(delta.total_seconds() // 60)

        if minutes < 5:
            status = "🟢 **Wahrscheinlich aktiv**"
            detail = f"Stats haben sich vor {int(delta.total_seconds())}s geändert."
        elif minutes < 30:
            status = "🟡 **Kürzlich aktiv**"
            detail = f"Letzte erkannte Stats-Änderung vor {minutes} Minuten."
        else:
            status = "⚪ **Vermutlich inaktiv**"
            hours = minutes // 60
            detail = f"Letzte erkannte Stats-Änderung vor {hours}h {minutes % 60}min." if hours else f"Letzte erkannte Stats-Änderung vor {minutes} Minuten."

        embed = discord.Embed(title=f"{name}", description=f"{status}\n{detail}", color=0x3498DB)
        embed.set_footer(text="Kein echter Live-Status – basiert auf periodischem Stats-Vergleich (Poll-Intervall: "
                               f"{POLL_INTERVAL}s). Hive bietet keinen offiziellen Online-Status.")
        await interaction.response.send_message(embed=embed)

    @tasks.loop(seconds=POLL_INTERVAL)
    async def poll_loop(self):
        players = storage.get_players()
        if not players:
            return

        # Requests ueber das Intervall staffeln statt alle gleichzeitig zu feuern
        # (schont das Rate-Limit, besonders ohne HIVE_API_KEY)
        gap = max(POLL_INTERVAL / max(len(players), 1) * 0.8, 1.0)

        for info in players.values():
            name = info["display_name"]
            channel_id = info.get("channel_id") or DEFAULT_CHANNEL_ID

            window_start_iso = storage.get_last_checked(name)
            now_iso = datetime.now(timezone.utc).isoformat()

            try:
                new_stats = await self.hive.get_all_stats(name)
            except HiveAPIError as e:
                log.warning("Rate-Limit/Fehler bei %s: %s", name, e)
                storage.set_last_checked(name, now_iso)
                await asyncio.sleep(gap)
                continue
            except Exception:
                log.exception("Unerwarteter Fehler beim Abrufen von %s", name)
                storage.set_last_checked(name, now_iso)
                await asyncio.sleep(gap)
                continue

            if new_stats is None:
                storage.set_last_checked(name, now_iso)
                await asyncio.sleep(gap)
                continue

            old_stats = info.get("last_stats")
            storage.update_last_stats(name, new_stats)
            storage.set_last_checked(name, now_iso)

            if old_stats is None:
                await asyncio.sleep(gap)
                continue  # erster Durchlauf: nur Baseline speichern

            streaks = self._update_streaks(name, old_stats, new_stats)

            changes = diff_stats(old_stats, new_stats)
            if changes:
                storage.set_last_active(name, now_iso)
            if changes and channel_id:
                await self._send_alert(channel_id, name, old_stats, new_stats, changes, streaks,
                                        window_start_iso, now_iso)

            await asyncio.sleep(gap)

    def _update_streaks(self, name: str, old_stats: dict, new_stats: dict) -> dict[str, int]:
        """Schreibt den client-seitigen Live-Winstreak pro (Spiel, Modus) fort und persistiert ihn."""
        current = storage.get_streaks(name)
        updated = dict(current)

        for game_key, new_game_data in new_stats.items():
            if not isinstance(new_game_data, dict) or not new_game_data:
                continue
            old_game_data = old_stats.get(game_key) if isinstance(old_stats, dict) else None
            if not isinstance(old_game_data, dict):
                continue

            new_leaves = leaf_stat_dicts(new_game_data)
            old_leaves = leaf_stat_dicts(old_game_data)

            for mode_label, new_leaf in new_leaves.items():
                old_leaf = old_leaves.get(mode_label)
                if not isinstance(old_leaf, dict):
                    continue

                new_wins, new_played = extract_wins_played(new_leaf)
                old_wins, old_played = extract_wins_played(old_leaf)
                if None in (new_wins, new_played, old_wins, old_played):
                    continue  # dieses Spiel hat keine erkennbaren wins/played-Felder

                streak_key = f"{game_key}|{mode_label or ''}"
                old_streak = current.get(streak_key, 0)
                new_streak = update_streak(old_streak, new_played - old_played, new_wins - old_wins)

                if new_streak != old_streak:
                    storage.set_streak(name, streak_key, new_streak)
                updated[streak_key] = new_streak

        return updated

    async def _send_alert(self, channel_id: int, name: str, old_stats: dict, new_stats: dict,
                           changes: list[tuple[str, float, float]], streaks: dict[str, int],
                           window_start_iso: str | None, window_end_iso: str):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        # Gruppieren nach (Spiel, Modus)
        grouped: dict[tuple[str, str | None], list[tuple[str, float, float]]] = {}
        for full_path, old_v, new_v in changes:
            game_key, mode_label, stat_key = split_game_mode(full_path)
            grouped.setdefault((game_key, mode_label), []).append((stat_key, old_v, new_v))

        # Zeitfenster fuers Rundenende: irgendwo zwischen dem letzten Check ohne
        # Aenderung und diesem Check. Rundenstart ist ueber diese Methode NICHT
        # feststellbar - die API liefert kein "Runde gestartet"-Signal.
        end_time = datetime.fromisoformat(window_end_iso)
        if window_start_iso:
            start_time = datetime.fromisoformat(window_start_iso)
            window_desc = (f"🕒 Runde vermutlich beendet zwischen "
                            f"**{start_time.strftime('%H:%M:%S')}** und **{end_time.strftime('%H:%M:%S')} UTC**")
        else:
            window_desc = f"🕒 Erkannt um **{end_time.strftime('%H:%M:%S')} UTC**"

        embed = discord.Embed(
            title=f"📈 {name} hat gerade eine Runde beendet",
            description=f"{window_desc}\n_Rundenstart ist über diese Methode nicht feststellbar._",
            color=0x2ECC71,
        )

        for (game_key, mode_label), entries in grouped.items():
            game_label = GAME_NAMES.get(game_key, game_key)
            title = f"{game_label} · {mode_label}" if mode_label else game_label

            lines = []
            for stat_key, old_v, new_v in entries[:6]:
                emoji, label = label_for_key(stat_key)
                lines.append(f"{emoji} **{label}**: {old_v} → **{new_v}**")

            # KD-Delta anzeigen, falls berechenbar
            mode_dict_new = _find_stats_dict(new_stats, game_key)
            mode_dict_old = _find_stats_dict(old_stats, game_key)
            if mode_label and isinstance(mode_dict_new, dict):
                for k, v in mode_dict_new.items():
                    if isinstance(v, dict):
                        mode_dict_new = v
                        break
            kd_new = compute_kd(mode_dict_new) if isinstance(mode_dict_new, dict) else None
            kd_old = compute_kd(mode_dict_old) if isinstance(mode_dict_old, dict) else None
            if kd_new is not None and kd_old is not None and kd_new != kd_old:
                lines.append(f"⚡ **KD**: {kd_old} → **{kd_new}**")

            # Live-Winstreak (client-seitig mitgezaehlt) anzeigen, falls vorhanden
            streak_key = f"{game_key}|{mode_label or ''}"
            if streak_key in streaks:
                streak_val = streaks[streak_key]
                fire = "🔥🔥" if streak_val >= 5 else "🔥"
                lines.append(f"{fire} **Live-Winstreak**: {streak_val}")

            embed.add_field(name=title, value="\n".join(lines), inline=False)

        await channel.send(embed=embed)

    @poll_loop.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackingCog(bot))
