"""
hive_api.py
Thin async wrapper around the official Hive (Bedrock) API.
Docs: https://support.playhive.com/api/
OpenAPI spec: https://api.playhive.com/docs/api-docs.json

IMPORTANT: This API does NOT expose live online/offline status, current
game/server, or a player's location. There is no endpoint for that. See
README.md for details on what this bot can and cannot do.
"""
from __future__ import annotations

import aiohttp

BASE_URL = "https://api.playhive.com/v0"


class HiveAPIError(Exception):
    pass


class HiveAPI:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key
        self._session: aiohttp.ClientSession | None = None

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            headers = {"User-Agent": "HiveStatsDiscordBot/2.0"}
            if self.api_key:
                headers["Authorization"] = f"Bearer {self.api_key}"
            self._session = aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=15))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def _get(self, path: str):
        session = await self._get_session()
        url = f"{BASE_URL}{path}"
        async with session.get(url) as resp:
            if resp.status == 404:
                return None
            if resp.status == 429:
                retry_after = resp.headers.get("Retry-After", "unknown")
                raise HiveAPIError(
                    f"Rate limit hit (Retry-After: {retry_after}s). "
                    f"Without a HIVE_API_KEY the rate limit is very low."
                )
            if resp.status >= 400:
                raise HiveAPIError(f"HTTP {resp.status} on {path}")
            return await resp.json()

    async def search_player(self, partial: str):
        """Search players by name prefix (min. 4 characters)."""
        return await self._get(f"/player/search/{partial}")

    async def get_all_stats(self, identifier: str):
        """All game stats for a player in a single call (efficient for polling)."""
        return await self._get(f"/game/all/all/{identifier}")

    async def get_main_stats(self, identifier: str):
        return await self._get(f"/game/all/main/{identifier}")

    async def get_game_stats(self, game: str, identifier: str):
        """Stats for a single game, e.g. game='bed' for BedWars."""
        return await self._get(f"/game/all/{game}/{identifier}")
