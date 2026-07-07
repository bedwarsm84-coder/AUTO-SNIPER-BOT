"""
bot.py
Entry point: sets up the Discord bot and loads all cogs from cogs/.
"""
from __future__ import annotations

import asyncio
import logging
import os

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from hive_api import HiveAPI

load_dotenv()

DISCORD_TOKEN = os.environ["DISCORD_TOKEN"]
HIVE_API_KEY = os.getenv("HIVE_API_KEY") or None

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("hivebot")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)
bot.hive = HiveAPI(HIVE_API_KEY)  # used by cogs via bot.hive

INITIAL_COGS = [
    "cogs.stats",
    "cogs.tracking",
]


@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync()
        log.info("Logged in as %s | synced %d slash command(s)", bot.user, len(synced))
    except Exception:
        log.exception("Failed to sync application commands")


@bot.event
async def on_close():
    await bot.hive.close()


# ─── Owner-only: Bot von einem Server entfernen ───────────────────────────
# Setze hier deine eigene Discord User-ID ein (Entwicklermodus an →
# Rechtsklick auf deinen Namen → "ID kopieren").
OWNER_ID = 1315317603773710377  # <-- HIER ANPASSEN


@bot.tree.command(name="leaveserver", description="Lässt den Bot einen Server verlassen (nur Owner)")
@app_commands.describe(guild_id="Die ID des Servers, den der Bot verlassen soll")
async def leaveserver(interaction: discord.Interaction, guild_id: str):
    if interaction.user.id != OWNER_ID:
        await interaction.response.send_message("Keine Berechtigung.", ephemeral=True)
        return
    try:
        guild = bot.get_guild(int(guild_id))
    except ValueError:
        await interaction.response.send_message("Ungültige Server-ID.", ephemeral=True)
        return
    if guild is None:
        await interaction.response.send_message("Server nicht gefunden (Bot ist dort evtl. nicht mehr Mitglied).", ephemeral=True)
        return
    name = guild.name
    await guild.leave()
    await interaction.response.send_message(f"Habe **{name}** verlassen.", ephemeral=True)


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    """Global fallback so command bugs show a clear message instead of a
    silent 'This interaction failed' in Discord."""
    log.exception("Slash command error in /%s", getattr(interaction.command, "name", "?"), exc_info=error)
    message = "⚠️ Something went wrong running that command. The error has been logged."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)
    except discord.HTTPException:
        pass


async def main():
    async with bot:
        for ext in INITIAL_COGS:
            try:
                await bot.load_extension(ext)
                log.info("Loaded cog: %s", ext)
            except Exception:
                log.exception("Failed to load cog: %s", ext)
                raise
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
    
