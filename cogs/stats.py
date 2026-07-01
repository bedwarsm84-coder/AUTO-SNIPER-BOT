"""
cogs/stats.py
Slash-Commands zum Abfragen von Hive-Statistiken.
"""
from __future__ import annotations

import json

import discord
from discord import app_commands
from discord.ext import commands

from hive_api import HiveAPIError

GAME_NAMES = {
    "wars": "Treasure Wars", "dr": "Deathrun", "hide": "Hide & Seek",
    "sg": "Survival Games", "murder": "Murder Mystery", "sky": "SkyWars",
    "ctf": "Capture the Flag", "drop": "Just Drop", "ground": "Ground Wars",
    "build": "Build Battle", "party": "Party Games", "bridge": "The Bridge",
    "grav": "Gravity", "bed": "BedWars",
}


def _flat_lines(data: dict, limit: int = 12) -> list[str]:
    lines = []
    for key, value in list(data.items())[:limit]:
        if isinstance(value, (int, float, str)):
            lines.append(f"**{key}**: {value}")
    return lines


class StatsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hive = bot.hive

    @app_commands.command(description="Zeigt Hive-Statistiken eines Spielers")
    @app_commands.describe(
        name="Minecraft-Bedrock-Name",
        game="Kuerzel wie bed, sky, wars, murder ... (leer = alle Spiele)",
    )
    async def stats(self, interaction: discord.Interaction, name: str, game: str | None = None):
        await interaction.response.defer()
        try:
            data = await self.hive.get_game_stats(game, name) if game else await self.hive.get_all_stats(name)
        except HiveAPIError as e:
            await interaction.followup.send(f"⚠️ API-Fehler: {e}")
            return

        if data is None:
            await interaction.followup.send(f"❌ Spieler `{name}` nicht gefunden.")
            return

        embed = discord.Embed(title=f"Hive-Stats: {name}", color=0xF5A623)
        if game:
            lines = _flat_lines(data)
            if lines:
                embed.add_field(name=GAME_NAMES.get(game, game), value="\n".join(lines), inline=False)
        else:
            for game_key, game_data in data.items():
                if isinstance(game_data, dict) and game_data:
                    lines = _flat_lines(game_data, limit=6)
                    if lines:
                        embed.add_field(name=GAME_NAMES.get(game_key, game_key), value="\n".join(lines), inline=False)

        if not embed.fields:
            embed.description = "Keine auswertbaren Felder gefunden – probier `/raw` fuer die Rohdaten."
        await interaction.followup.send(embed=embed)

    @app_commands.command(description="Zeigt die rohe API-Antwort (z.B. um winstreak-Feldnamen zu finden)")
    @app_commands.describe(name="Minecraft-Bedrock-Name", game="Kuerzel wie bed, sky, wars ... (leer = alle Spiele)")
    async def raw(self, interaction: discord.Interaction, name: str, game: str | None = None):
        await interaction.response.defer()
        try:
            data = await self.hive.get_game_stats(game, name) if game else await self.hive.get_all_stats(name)
        except HiveAPIError as e:
            await interaction.followup.send(f"⚠️ API-Fehler: {e}")
            return
        if data is None:
            await interaction.followup.send(f"❌ Spieler `{name}` nicht gefunden.")
            return
        text = json.dumps(data, indent=2, ensure_ascii=False)
        if len(text) > 1900:
            text = text[:1900] + "\n... (gekuerzt, mit game=<kuerzel> gezielter abfragen)"
        await interaction.followup.send(f"```json\n{text}\n```")


async def setup(bot: commands.Bot):
    await bot.add_cog(StatsCog(bot))
