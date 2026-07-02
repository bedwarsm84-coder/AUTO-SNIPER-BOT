"""
Sehr simple JSON-Datei-Persistenz fuer beobachtete Spieler + letzten Stats-Snapshot.
Fuer den Anfang voellig ausreichend; bei Bedarf spaeter durch eine echte DB ersetzbar.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

DATA_FILE = Path(os.getenv("DATA_FILE", "data/tracked.json"))


def _ensure():
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    if not DATA_FILE.exists():
        DATA_FILE.write_text(json.dumps({"players": {}}, indent=2))


def load() -> dict:
    _ensure()
    return json.loads(DATA_FILE.read_text())


def save(data: dict) -> None:
    _ensure()
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False))


def add_player(name: str, channel_id: int) -> bool:
    data = load()
    key = name.lower()
    if key in data["players"]:
        return False
    data["players"][key] = {
        "display_name": name,
        "channel_id": channel_id,
        "last_stats": None,
        "streaks": {},       # z.B. {"bed|": 5, "sky|Solo": 2}
        "last_active_at": None,  # ISO-Timestamp der letzten erkannten Stats-Aenderung
    }
    save(data)
    return True


def remove_player(name: str) -> bool:
    data = load()
    key = name.lower()
    if key not in data["players"]:
        return False
    del data["players"][key]
    save(data)
    return True


def get_players() -> dict:
    return load()["players"]


def update_last_stats(name: str, stats: dict) -> None:
    data = load()
    key = name.lower()
    if key in data["players"]:
        data["players"][key]["last_stats"] = stats
        save(data)


def get_streaks(name: str) -> dict:
    data = load()
    key = name.lower()
    return data["players"].get(key, {}).get("streaks", {})


def set_streak(name: str, streak_key: str, value: int) -> None:
    data = load()
    key = name.lower()
    if key in data["players"]:
        data["players"][key].setdefault("streaks", {})[streak_key] = value
        save(data)


def set_last_active(name: str, iso_timestamp: str) -> None:
    data = load()
    key = name.lower()
    if key in data["players"]:
        data["players"][key]["last_active_at"] = iso_timestamp
        save(data)


def get_last_active(name: str) -> str | None:
    data = load()
    key = name.lower()
    return data["players"].get(key, {}).get("last_active_at")
