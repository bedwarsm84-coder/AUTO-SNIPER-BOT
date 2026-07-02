"""
formatting.py
Gemeinsame Helfer fuer StatsCog und TrackingCog:
 - Erkennung von BedWars/SkyWars-Modi (Solo/Duos/Squads/Mega) anhand des JSON-Pfads
 - KD-Berechnung
 - huebsche Labels/Emojis fuer bekannte Stat-Felder

Hinweis: Hive dokumentiert die genauen JSON-Feldnamen nicht oeffentlich.
Die Aliase unten decken die gaengigsten Schreibweisen ab. Falls Hive andere
Namen verwendet, per /raw pruefen und hier ergaenzen.
"""
from __future__ import annotations

import re

MODE_ALIASES: dict[str, str] = {
    "solo": "Solo", "solos": "Solo",
    "duo": "Duos", "duos": "Duos",
    "squad": "Squads", "squads": "Squads",
    "mega": "Mega", "megawalls": "Mega",
    "manor": "Manor",
}

# Bekannte Stat-Feld-Fragmente -> (Emoji, huebsches Label)
KNOWN_FIELDS: dict[str, tuple[str, str]] = {
    "winstreak": ("🔥", "Winstreak"),
    "win_streak": ("🔥", "Winstreak"),
    "streak": ("🔥", "Winstreak"),
    "wins": ("🏆", "Wins"),
    "losses": ("💀", "Losses"),
    "kills": ("⚔️", "Kills"),
    "deaths": ("☠️", "Deaths"),
    "finalkills": ("🗡️", "Final Kills"),
    "finaldeaths": ("🪦", "Final Deaths"),
    "bedsdestroyed": ("🛏️", "Beds Destroyed"),
    "level": ("⭐", "Level"),
    "xp": ("✨", "XP"),
    "gamesplayed": ("🎮", "Games Played"),
}


def label_for_key(key: str) -> tuple[str, str]:
    """Gibt (Emoji, huebsches Label) fuer ein rohes JSON-Feld zurueck."""
    norm = re.sub(r"[^a-z]", "", key.lower())
    for fragment, (emoji, label) in KNOWN_FIELDS.items():
        if fragment in norm:
            return emoji, label
    return "📊", key


def split_game_mode(full_path: str) -> tuple[str, str | None, str]:
    """
    Zerlegt einen diff_stats-Pfad wie 'bed.solo.wins' in
    (game_key='bed', mode_label='Solo', stat_key='wins').
    Wenn kein bekannter Modus erkannt wird, ist mode_label None
    und stat_key ist der Rest ab dem zweiten Segment.
    """
    parts = full_path.split(".")
    game_key = parts[0]
    if len(parts) >= 3 and parts[1].lower() in MODE_ALIASES:
        mode_label = MODE_ALIASES[parts[1].lower()]
        stat_key = ".".join(parts[2:])
    else:
        mode_label = None
        stat_key = ".".join(parts[1:]) if len(parts) > 1 else parts[0]
    return game_key, mode_label, stat_key


def compute_kd(data: dict) -> float | None:
    """Sucht kills/deaths auf oberster Ebene eines Stats-Dicts und berechnet KD."""
    kills = deaths = None
    for key, value in data.items():
        norm = re.sub(r"[^a-z]", "", key.lower())
        if norm == "kills" and isinstance(value, (int, float)):
            kills = value
        elif norm == "deaths" and isinstance(value, (int, float)):
            deaths = value
    if kills is None or deaths is None:
        return None
    if deaths == 0:
        return float(kills)
    return round(kills / deaths, 2)
