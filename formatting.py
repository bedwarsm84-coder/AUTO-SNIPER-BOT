"""
formatting.py
Shared helpers for StatsCog and TrackingCog:
 - detecting BedWars/SkyWars modes (Solo/Duos/Squads/Mega) from the JSON path
 - KD calculation
 - pretty labels/emoji for known stat fields
 - client-side "live" win streak tracking

Note: Hive does not publicly document its exact JSON field names. The aliases
below cover the most common spellings seen in real responses. If Hive uses a
different name for something, check with /raw and extend the tables below.
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

# Known stat-field fragments -> (emoji, pretty label).
# NOTE: order does not matter for correctness — label_for_key() always checks
# the longest fragments first so e.g. "final_kills" is never mislabeled as
# generic "kills".
KNOWN_FIELDS: dict[str, tuple[str, str]] = {
    "winstreak": ("🔥", "Winstreak"),
    "win_streak": ("🔥", "Winstreak"),
    "streak": ("🔥", "Winstreak"),
    "victories": ("🏆", "Wins"),
    "wins": ("🏆", "Wins"),
    "losses": ("💀", "Losses"),
    "finalkills": ("🗡️", "Final Kills"),
    "finaldeaths": ("🪦", "Final Deaths"),
    "kills": ("⚔️", "Kills"),
    "deaths": ("☠️", "Deaths"),
    "bedsdestroyed": ("🛏️", "Beds Destroyed"),
    "level": ("⭐", "Level"),
    "prestige": ("🎖️", "Prestige"),
    "xp": ("✨", "XP"),
    "gamesplayed": ("🎮", "Games Played"),
    "played": ("🎮", "Games Played"),
}

# Fields that exist in the API response but aren't displayable stats
# (IDs, timestamps, ...) - hidden from /stats, /raw formatting, and alerts.
EXCLUDED_FIELDS: set[str] = {
    "uuid", "id", "firstplayed", "lastplayed", "createdat", "updatedat",
}


def is_excluded(key: str) -> bool:
    """True for fields that aren't displayable stats (UUID, timestamps, ...)."""
    norm = re.sub(r"[^a-z]", "", key.lower())
    return norm in EXCLUDED_FIELDS


def label_for_key(key: str) -> tuple[str, str]:
    """Returns (emoji, pretty label) for a raw JSON field.
    Checks longer/more specific fragments first so e.g. 'final_kills' is not
    mislabeled as generic 'kills'."""
    norm = re.sub(r"[^a-z]", "", key.lower())
    for fragment, (emoji, label) in sorted(KNOWN_FIELDS.items(), key=lambda kv: -len(kv[0])):
        if fragment in norm:
            return emoji, label
    return "📊", key


def split_game_mode(full_path: str) -> tuple[str, str | None, str]:
    """
    Splits a diff_stats path like 'bed.solo.wins' into
    (game_key='bed', mode_label='Solo', stat_key='wins').
    If no known mode is recognized, mode_label is None and stat_key is
    everything from the second segment onward.
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
    """Looks for kills/deaths at the top level of a stats dict and computes KD."""
    kills = deaths = None
    for key, value in data.items():
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            continue
        norm = re.sub(r"[^a-z]", "", key.lower())
        if norm == "kills":
            kills = value
        elif norm == "deaths":
            deaths = value
    if kills is None or deaths is None:
        return None
    if deaths == 0:
        return float(kills)
    return round(kills / deaths, 2)


# ---------------------------------------------------------------------------
# "Live" win streak: NOT provided by the Hive API itself (see README).
# Tracked client-side here: every detected win increments it, every detected
# non-win round resets it to 0. Based on periodically comparing "wins"/
# "victories" and "played"/"gamesplayed" fields.
# ---------------------------------------------------------------------------

def extract_wins_played(data: dict) -> tuple[float | None, float | None]:
    """Finds wins-like and played-like fields in a flat stats dict."""
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
    Splits a game's stats into {mode_label_or_None: flat_stats_dict}.
    If there's no mode split (common on Hive), returns a single entry keyed
    by None.
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
    Advances a client-side tracked win streak.
    - No new round since the last check -> streak stays the same.
    - All new rounds were wins -> streak increases by delta_wins.
    - At least one new round was not a win -> streak resets to 0
      (conservative assumption if multiple rounds happened within one
      poll interval).
    """
    if delta_played <= 0:
        return old_streak
    if delta_wins >= delta_played:
        return old_streak + int(delta_wins)
    return 0
