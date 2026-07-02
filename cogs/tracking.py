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

import discord
from discord import app_commands
from discord.ext import commands, tasks

import storage
from cogs.stats import GAME_NAMES
from formatting import label_for_key, compute_kd, split_game_mode
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

    @tasks.loop(seconds=POLL_INTERVAL)
    async def poll_loop(self):
        players = storage.get_players()
        if not players:
            return

        gap = max(POLL_INTERVAL / max(len(players), 1) * 0.8, 1.0)

        for info in players.values():
            name = info["display_name"]
            channel_id = info.get("channel_id") or DEFAULT_CHANNEL_ID

            try:
                new_stats = await self.hive.get_all_stats(name)
            except HiveAPIError as e:
                log.warning("Rate-Limit/Fehler bei %s: %s", name, e)
                await asyncio.sleep(gap)
                continue
            except Exception:
                log.exception("Unerwarteter Fehler beim Abrufen von %s", name)
                await asyncio.sleep(gap)
                continue

            if new_stats is None:
                await asyncio.sleep(gap)
                continue

            old_stats = info.get("last_stats")
            storage.update_last_stats(name, new_stats)

            if old_stats is None:
                await asyncio.sleep(gap)
                continue

            changes = diff_stats(old_stats, new_stats)
            if changes and channel_id:
                await self._send_alert(channel_id, name, old_stats, new_stats, changes)

            await asyncio.sleep(gap)

    async def _send_alert(self, channel_id: int, name: str, old_stats: dict,
                           new_stats: dict, changes: list[tuple[str, float, float]]):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        grouped: dict[tuple[str, str | None], list[tuple[str, float, float]]] = {}
        for full_path, old_v, new_v in changes:
            game_key, mode_label, stat_key = split_game_mode(full_path)
            grouped.setdefault((game_key, mode_label), []).append((stat_key, old_v, new_v))

        embed = discord.Embed(
            title=f"📈 {name} hat gerade eine Runde beendet",
            description="Erkannt anhand gestiegener Statistik-Werte (nicht in Echtzeit).",
            color=0x2ECC71,
        )

        for (game_key, mode_label), entries in grouped.items():
            game_label = GAME_NAMES.get(game_key, game_key)
            title = f"{game_label} · {mode_label}" if mode_label else game_label

            lines = []
            for stat_key, old_v, new_v in entries[:6]:
                emoji, label = label_for_key(stat_key)
                lines.append(f"{emoji} **{label}**: {old_v} → **{new_v}**")

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

            embed.add_field(name=title, value="\n".join(lines), inline=False)

        await channel.send(embed=embed)

    @poll_loop.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackingCog(bot))
