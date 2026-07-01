"""
Sehr simple JSON-Datei-Persistenz fuer beobachtete Spieler + letzten Stats-Snapshot.
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
