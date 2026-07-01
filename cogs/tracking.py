"""
cogs/tracking.py
Spieler-Beobachtung: periodischer Stats-Vergleich + Discord-Meldung bei Aenderung.
"""
from __future__ import annotations

import logging
import os

import discord
from discord import app_commands
from discord.ext import commands, tasks

import storage
from cogs.stats import GAME_NAMES
from hive_api import HiveAPIError

log = logging.getLogger("hivebot.tracking")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "120"))
DEFAULT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID", "0")) or None


def diff_stats(old, new, path: str = "") -> list[tuple[str, float, float]]:
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
                f"✅ `{name}` wird jetzt beobachtet (Check alle {POLL_INTERVAL}s).\n"
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
        for info in players.values():
            name = info["display_name"]
            channel_id = info.get("channel_id") or DEFAULT_CHANNEL_ID

            try:
                new_stats = await self.hive.get_all_stats(name)
            except HiveAPIError as e:
                log.warning("Rate-Limit/Fehler bei %s: %s", name, e)
                continue
            except Exception:
                log.exception("Unerwarteter Fehler beim Abrufen von %s", name)
                continue

            if new_stats is None:
                continue

            old_stats = info.get("last_stats")
            storage.update_last_stats(name, new_stats)

            if old_stats is None:
                continue

            changes = diff_stats(old_stats, new_stats)
            if not changes or not channel_id:
                continue

            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            grouped: dict[str, list[tuple[str, float, float]]] = {}
            for full_path, old_v, new_v in changes:
                game_key = full_path.split(".")[0]
                grouped.setdefault(game_key, []).append((full_path, old_v, new_v))

            embed = discord.Embed(
                title=f"📈 Neue Aktivität: {name}",
                description="Statistik-Änderung erkannt – Runde vermutlich gerade beendet.",
                color=0x2ECC71,
            )
            for game_key, entries in grouped.items():
                label = GAME_NAMES.get(game_key, game_key)
                lines = [f"`{p.split('.', 1)[-1]}`: {o} → **{n}**" for p, o, n in entries[:8]]
                embed.add_field(name=label, value="\n".join(lines), inline=False)

            await channel.send(embed=embed)

    @poll_loop.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackingCog(bot))
