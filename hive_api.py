"""
Schlanker Wrapper um die offizielle Hive (Bedrock) API.
Dokumentation: https://support.playhive.com/api/
OpenAPI-Spec:  https://api.playhive.com/docs/api-docs.json

WICHTIG: Diese API bietet KEINE Online-/Offline-/"aktuelles Spiel"-Daten.
Es gibt nur Statistik-Endpunkte (Wins, Kills, ...). Siehe README.md.
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
            headers = {"User-Agent": "HiveStatsDiscordBot/1.0 (+github.com/dein-repo)"}
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
                retry_after = resp.headers.get("Retry-After", "unbekannt")
                raise HiveAPIError(f"Rate-Limit erreicht (Retry-After: {retry_after}s). "
                                    f"Ohne HIVE_API_KEY ist das Limit sehr niedrig.")
            if resp.status >= 400:
                raise HiveAPIError(f"HTTP {resp.status} bei {path}")
            return await resp.json()

    async def search_player(self, partial: str):
        """Spieler per Namens-Praefix suchen (min. 4 Zeichen)."""
        return await self._get(f"/player/search/{partial}")

    async def get_all_stats(self, identifier: str):
        """Alle Spiel-Statistiken eines Spielers in einem Call (effizient fuers Polling)."""
        return await self._get(f"/game/all/all/{identifier}")

    async def get_main_stats(self, identifier: str):
        return await self._get(f"/game/all/main/{identifier}")

    async def get_game_stats(self, game: str, identifier: str):
        """Statistiken fuer ein einzelnes Spiel, z.B. game='bed' fuer BedWars."""
        return await self._get(f"/game/all/{game}/{identifier}")
