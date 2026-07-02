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
    "victories": ("🏆", "Wins"),
    "wins": ("🏆", "Wins"),
    "losses": ("💀", "Losses"),
    "kills": ("⚔️", "Kills"),
    "deaths": ("☠️", "Deaths"),
    "finalkills": ("🗡️", "Final Kills"),
    "finaldeaths": ("🪦", "Final Deaths"),
    "bedsdestroyed": ("🛏️", "Beds Destroyed"),
    "level": ("⭐", "Level"),
    "prestige": ("🎖️", "Prestige"),
    "xp": ("✨", "XP"),
    "played": ("🎮", "Games Played"),
    "gamesplayed": ("🎮", "Games Played"),
}

# Felder, die zwar in der API-Antwort stehen, aber keine anzeigbaren Stats sind
# (IDs, Zeitstempel usw.) - werden in /stats und Alerts ausgeblendet.
EXCLUDED_FIELDS: set[str] = {
    "uuid", "id", "firstplayed", "lastplayed", "createdat", "updatedat",
}


def is_excluded(key: str) -> bool:
    """True fuer Felder, die keine anzeigbaren Stats sind (UUID, Timestamps, ...)."""
    norm = re.sub(r"[^a-z]", "", key.lower())
    return norm in EXCLUDED_FIELDS


def label_for_key(key: str) -> tuple[str, str]:
    """Gibt (Emoji, huebsches Label) fuer ein rohes JSON-Feld zurueck.
    Prueft laengere/spezifischere Fragmente zuerst, damit z.B. 'final_kills'
    nicht faelschlich als generisches 'kills' erkannt wird."""
    norm = re.sub(r"[^a-z]", "", key.lower())
    for fragment, (emoji, label) in sorted(KNOWN_FIELDS.items(), key=lambda kv: -len(kv[0])):
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


# ---------------------------------------------------------------------------
# "Live"-Winstreak: von der Hive-API selbst NICHT geliefert (siehe README).
# Wird hier client-seitig mitgezaehlt: jeder erkannte Sieg zaehlt hoch,
# jede erkannte Runde ohne Sieg setzt zurueck auf 0. Basiert auf dem
# periodischen Vergleich von "wins"/"victories" und "played"/"gamesplayed".
# ---------------------------------------------------------------------------

def extract_wins_played(data: dict) -> tuple[float | None, float | None]:
    """Sucht wins- und played-aehnliche Felder in einem flachen Stats-Dict."""
    wins = played = None
    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        norm = re.sub(r"[^a-z]", "", key.lower())
        if norm in ("wins", "victories"):
            wins = value
        elif norm in ("played", "gamesplayed"):
            played = value
    return wins, played


def leaf_stat_dicts(game_data: dict) -> dict[str | None, dict]:
    """
    Zerlegt die Stats eines Spiels in {modus_label_oder_None: flaches_stats_dict}.
    Wenn keine Modus-Unterteilung existiert (haeufig bei Hive), gibt es genau
    einen Eintrag mit Key None.
    """
    if any(k.lower() in MODE_ALIASES for k in game_data.keys()):
        result: dict[str | None, dict] = {}
        for key, value in game_data.items():
            if isinstance(value, dict):
                result[MODE_ALIASES.get(key.lower(), key.capitalize())] = value
        return result
    return {None: game_data}


def update_streak(old_streak: int, delta_played: float, delta_wins: float) -> int:
    """
    Schreibt einen client-seitig gezaehlten Winstreak fort.
    - Keine neue Runde seit dem letzten Check -> Streak bleibt gleich.
    - Alle neuen Runden waren Siege -> Streak steigt um delta_wins.
    - Mindestens eine neue Runde war kein Sieg -> Streak wird auf 0 zurueckgesetzt
      (konservative Annahme, falls im Poll-Intervall mehrere Runden lagen).
    """
    if delta_played <= 0:
        return old_streak
    if delta_wins >= delta_played:
        return old_streak + int(delta_wins)
    return 0
