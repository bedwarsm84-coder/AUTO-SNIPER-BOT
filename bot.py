"""
bot.py
Einstiegspunkt: initialisiert den Discord-Bot und laedt alle Cogs aus cogs/.
"""
from __future__ import annotations

import asyncio
import logging
import os

import discord
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
bot.hive = HiveAPI(HIVE_API_KEY)  # von den Cogs ueber bot.hive genutzt

INITIAL_COGS = [
    "cogs.stats",
    "cogs.tracking",
]


@bot.event
async def on_ready():
    await bot.tree.sync()
    log.info("Eingeloggt als %s", bot.user)


@bot.event
async def on_close():
    await bot.hive.close()


async def main():
    async with bot:
        for ext in INITIAL_COGS:
            await bot.load_extension(ext)
            log.info("Cog geladen: %s", ext)
        await bot.start(DISCORD_TOKEN)


if __name__ == "__main__":
    asyncio.run(main())
