"""
cogs/stats.py
Slash commands for looking up Hive stats, plus build_full_stats_embed()
which is shared with cogs/tracking.py for the /livestats dashboard.
"""
from __future__ import annotations

import json
import logging

import discord
from discord import app_commands
from discord.ext import commands

from hive_api import HiveAPIError
from formatting import label_for_key, compute_kd, MODE_ALIASES, is_excluded

log = logging.getLogger("hivebot.stats")

GAME_NAMES = {
    "wars": "Treasure Wars", "dr": "Deathrun", "hide": "Hide & Seek",
    "sg": "Survival Games", "murder": "Murder Mystery", "sky": "SkyWars",
    "ctf": "Capture the Flag", "drop": "Just Drop", "ground": "Ground Wars",
    "build": "Build Battle", "party": "Party Games", "bridge": "The Bridge",
    "grav": "Gravity", "bed": "BedWars",
}


def _is_mode_split(data: dict) -> bool:
    return any(k.lower() in MODE_ALIASES for k in data.keys())


def _format_block(data: dict, limit: int = 10) -> str:
    lines = []
    for key, value in list(data.items()):
        if is_excluded(key):
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            emoji, label = label_for_key(key)
            lines.append(f"{emoji} **{label}**: {value}")
    kd = compute_kd(data)
    if kd is not None:
        lines.append(f"⚡ **KD**: {kd}")
    return "\n".join(lines[:limit]) if lines else "_No displayable fields found_"


def build_full_stats_embed(name: str, data: dict, game: str | None = None) -> discord.Embed:
    """Shared embed builder used by /stats and the /livestats dashboard."""
    embed = discord.Embed(title=f"🐝 Hive Stats: {name}", color=0xF5A623)

    if game:
        if _is_mode_split(data):
            for mode_key, mode_data in data.items():
                if isinstance(mode_data, dict) and mode_data:
                    mode_label = MODE_ALIASES.get(mode_key.lower(), mode_key.capitalize())
                    embed.add_field(
                        name=f"{GAME_NAMES.get(game, game)} · {mode_label}",
                        value=_format_block(mode_data),
                        inline=True,
                    )
        else:
            embed.add_field(name=GAME_NAMES.get(game, game), value=_format_block(data), inline=False)
    else:
        for game_key, game_data in data.items():
            if not isinstance(game_data, dict) or not game_data:
                continue
            label = GAME_NAMES.get(game_key, game_key)
            if _is_mode_split(game_data):
                first_mode_key, first_mode_data = next(iter(game_data.items()))
                mode_label = MODE_ALIASES.get(first_mode_key.lower(), first_mode_key.capitalize())
                embed.add_field(
                    name=f"{label} ({mode_label}, more via /stats game:{game_key})",
                    value=_format_block(first_mode_data, limit=6),
                    inline=False,
                )
            else:
                embed.add_field(name=label, value=_format_block(game_data, limit=6), inline=False)

    if not embed.fields:
        embed.description = "No displayable fields found — try `/raw` for the raw data."
    return embed


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hive = bot.hive

    @app_commands.command(description="Show a player's Hive stats")
    @app_commands.describe(
        name="Minecraft Bedrock username",
        game="Game code like bed, sky, wars, murder ... (leave empty for all games)",
    )
    async def stats(self, interaction: discord.Interaction, name: str, game: str | None = None):
        await interaction.response.defer()
        try:
            data = await self.hive.get_game_stats(game, name) if game else await self.hive.get_all_stats(name)
        except HiveAPIError as e:
            await interaction.followup.send(f"⚠️ API error: {e}")
            return
        except Exception:
            log.exception("Unexpected error in /stats for %s", name)
            await interaction.followup.send("⚠️ Something went wrong fetching that player's stats.")
            return

        if data is None:
            await interaction.followup.send(f"❌ Player `{name}` not found.")
            return

        embed = build_full_stats_embed(name, data, game)
        await interaction.followup.send(embed=embed)

    @app_commands.command(description="Show the raw API response (e.g. to find mode/winstreak field names)")
    @app_commands.describe(name="Minecraft Bedrock username", game="Game code like bed, sky, wars ... (leave empty for all games)")
    async def raw(self, interaction: discord.Interaction, name: str, game: str | None = None):
        await interaction.response.defer()
        try:
            data = await self.hive.get_game_stats(game, name) if game else await self.hive.get_all_stats(name)
        except HiveAPIError as e:
            await interaction.followup.send(f"⚠️ API error: {e}")
            return
        except Exception:
            log.exception("Unexpected error in /raw for %s", name)
            await interaction.followup.send("⚠️ Something went wrong fetching that player's data.")
            return
        if data is None:
            await interaction.followup.send(f"❌ Player `{name}` not found.")
            return
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if len(text) > 1900:
            text = text[:1900] + "\n... (truncated, use game=<code> to narrow it down)"
        await interaction.followup.send(f"```json\n{text}\n```")


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
