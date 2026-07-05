"""
cogs/tracking.py
Player watchlist: periodic stat comparison + Discord alert on change,
plus a live-updating "reactor" stats dashboard message (/livestats).

Robustness: every per-player step inside the poll loop is wrapped so a
single failure (bad data, API hiccup, formatting bug) never kills the
background loop for everyone else. Any unexpected exception is logged and
the loop keeps running; a top-level @poll_loop.error handler restarts the
loop automatically if it ever stops for an unforeseen reason.

Important: this is still NOT a live online/offline status. The Hive API does
not provide that. A "round finished" alert is a delayed inference based on
stat values going up.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands, tasks

import storage
from cogs.stats import GAME_NAMES, build_live_dashboard_embed
from formatting import (
    label_for_key, compute_kd, split_game_mode, is_excluded,
    leaf_stat_dicts, extract_wins_played, update_streak,
)
from hive_api import HiveAPIError

log = logging.getLogger("hivebot.tracking")

POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "45"))
DEFAULT_CHANNEL_ID = int(os.getenv("ALERT_CHANNEL_ID", "0")) or None


def diff_stats(old, new, path: str = "") -> list[tuple[str, float, float]]:
    """Finds all numeric fields that are higher in `new` than in `old`."""
    changes: list[tuple[str, float, float]] = []
    if not isinstance(new, dict):
        return changes
    for key, new_val in new.items():
        if is_excluded(key):
            continue
        old_val = old.get(key) if isinstance(old, dict) else None
        full_path = f"{path}.{key}" if path else key
        if isinstance(new_val, dict):
            changes.extend(diff_stats(old_val or {}, new_val, full_path))
        elif isinstance(new_val, (int, float)) and not isinstance(new_val, bool):
            old_num = old_val if isinstance(old_val, (int, float)) and not isinstance(old_val, bool) else 0
            if new_val > old_num:
                changes.append((full_path, old_num, new_val))
    return changes


def _find_stats_dict(data: dict, path_prefix: str) -> dict | None:
    """Navigates a stats dict along a path prefix like 'bed.solo'."""
    node = data
    for part in path_prefix.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node if isinstance(node, dict) else None


class TrackingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.hive = bot.hive
        self.poll_loop.start()

    def cog_unload(self):
        self.poll_loop.cancel()

    # ---------------------------------------------------------------- commands

    @app_commands.command(description="Track a player: alerts post in this channel when their stats change")
    @app_commands.describe(name="Minecraft Bedrock username")
    async def track(self, interaction: discord.Interaction, name: str):
        ok = storage.add_player(name, interaction.channel_id)
        if ok:
            await interaction.response.send_message(
                f"✅ Now tracking `{name}` (checked roughly every {POLL_INTERVAL}s, staggered).\n"
                f"⚠️ No live online status possible — this only reports a delayed signal when stats increase."
            )
        else:
            await interaction.response.send_message(f"`{name}` is already being tracked.")

    @app_commands.command(description="Stop tracking a player")
    @app_commands.describe(name="Minecraft Bedrock username")
    async def untrack(self, interaction: discord.Interaction, name: str):
        ok = storage.remove_player(name)
        await interaction.response.send_message("✅ Removed." if ok else f"`{name}` was not being tracked.")

    @app_commands.command(description="List all currently tracked players")
    async def tracked(self, interaction: discord.Interaction):
        players = storage.get_players()
        if not players:
            await interaction.response.send_message("No one is currently being tracked.")
            return
        names = ", ".join(p["display_name"] for p in players.values())
        await interaction.response.send_message(f"Tracked: {names}")

    @app_commands.command(description="Show the currently tracked live win streaks for a player")
    @app_commands.describe(name="Minecraft Bedrock username")
    async def streak(self, interaction: discord.Interaction, name: str):
        streaks = storage.get_streaks(name)
        if not streaks:
            await interaction.response.send_message(
                f"No streak data for `{name}` yet. Run `/track` first and wait for a poll cycle."
            )
            return
        embed = discord.Embed(
            title=f"🔥 Live Win Streaks: {name}",
            color=0xE67E22,
            description="Tracked client-side (Hive's API does not provide a winstreak field).",
        )
        for streak_key, value in streaks.items():
            game_key, _, mode_label = streak_key.partition("|")
            label = GAME_NAMES.get(game_key, game_key)
            if mode_label:
                label += f" · {mode_label}"
            embed.add_field(name=label, value=f"🔥 **{value}**", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Show whether a tracked player was recently active (based on stat changes, not a real live status)")
    @app_commands.describe(name="Minecraft Bedrock username")
    async def online(self, interaction: discord.Interaction, name: str):
        last_active_iso = storage.get_last_active(name)
        if last_active_iso is None:
            await interaction.response.send_message(
                f"No activity data for `{name}` yet. Run `/track` first and wait for a poll cycle — "
                f"or no stat change has been detected yet."
            )
            return

        last_active = datetime.fromisoformat(last_active_iso)
        now = datetime.now(timezone.utc)
        delta = now - last_active
        minutes = int(delta.total_seconds() // 60)

        if minutes < 5:
            status = "🟢 **Likely active**"
            detail = f"Stats changed {int(delta.total_seconds())}s ago."
        elif minutes < 30:
            status = "🟡 **Recently active**"
            detail = f"Last detected stat change {minutes} minutes ago."
        else:
            hours = minutes // 60
            status = "⚪ **Likely inactive**"
            detail = (f"Last detected stat change {hours}h {minutes % 60}min ago."
                       if hours else f"Last detected stat change {minutes} minutes ago.")

        embed = discord.Embed(title=name, description=f"{status}\n{detail}", color=0x3498DB)
        embed.set_footer(text=f"Not a real live status — based on periodic stat comparison "
                               f"(poll interval: {POLL_INTERVAL}s). Hive has no official online status API.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(description="Post a live-updating stats dashboard for a player (auto-refreshes)")
    @app_commands.describe(name="Minecraft Bedrock username")
    async def livestats(self, interaction: discord.Interaction, name: str):
        await interaction.response.defer()
        storage.add_player(name, interaction.channel_id)  # no-op if already tracked

        try:
            data = await self.hive.get_all_stats(name)
        except HiveAPIError as e:
            await interaction.followup.send(f"⚠️ API error: {e}")
            return
        if data is None:
            await interaction.followup.send(f"❌ Player `{name}` not found.")
            return

        storage.update_last_stats(name, data)

        embed = build_live_dashboard_embed(name, data, storage.get_last_active(name), POLL_INTERVAL)
        msg = await interaction.followup.send(embed=embed)

        storage.set_live_message(name, msg.channel.id, msg.id)

    @app_commands.command(description="Stop the live-updating dashboard for a player")
    @app_commands.describe(name="Minecraft Bedrock username")
    async def stoplive(self, interaction: discord.Interaction, name: str):
        storage.clear_live_message(name)
        await interaction.response.send_message(f"✅ Live dashboard for `{name}` stopped.")

    # ---------------------------------------------------------------- polling

    @tasks.loop(seconds=POLL_INTERVAL)
    async def poll_loop(self):
        players = storage.get_players()
        if not players:
            return

        # Stagger requests across the interval instead of firing them all at
        # once (kinder to the rate limit, especially without a HIVE_API_KEY).
        gap = max(POLL_INTERVAL / max(len(players), 1) * 0.8, 1.0)

        for info in list(players.values()):
            try:
                await self._poll_one_player(info)
            except Exception:
                # Never let a single player's failure kill the whole loop.
                log.exception("Unexpected error while polling %s", info.get("display_name"))
            await asyncio.sleep(gap)

    async def _poll_one_player(self, info: dict):
        name = info["display_name"]
        channel_id = info.get("channel_id") or DEFAULT_CHANNEL_ID

        window_start_iso = storage.get_last_checked(name)
        now_iso = datetime.now(timezone.utc).isoformat()

        try:
            new_stats = await self.hive.get_all_stats(name)
        except HiveAPIError as e:
            log.warning("Rate limit/error for %s: %s", name, e)
            storage.set_last_checked(name, now_iso)
            return

        storage.set_last_checked(name, now_iso)

        if new_stats is None:
            return

        old_stats = info.get("last_stats")
        storage.update_last_stats(name, new_stats)

        streaks = {}
        changes = []
        if old_stats is not None:
            streaks = self._update_streaks(name, old_stats, new_stats)
            changes = diff_stats(old_stats, new_stats)
            if changes:
                storage.set_last_active(name, now_iso)

        # Keep the live dashboard message (if any) fresh every single cycle,
        # regardless of whether anything changed. Must run AFTER
        # set_last_active() above so the activity status reflects this cycle.
        live = storage.get_live_message(name)
        if live:
            await self._update_live_message(name, live, new_stats)

        if old_stats is None:
            return  # first run: just stored the baseline, nothing to alert on

        if changes and channel_id:
            await self._send_alert(channel_id, name, old_stats, new_stats, changes, streaks,
                                    window_start_iso, now_iso)

    async def _update_live_message(self, name: str, live: dict, new_stats: dict):
        channel = self.bot.get_channel(live["channel_id"])
        if channel is None:
            return
        try:
            msg = await channel.fetch_message(live["message_id"])
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            storage.clear_live_message(name)
            return

        embed = build_live_dashboard_embed(name, new_stats, storage.get_last_active(name), POLL_INTERVAL)
        try:
            await msg.edit(embed=embed)
        except discord.HTTPException:
            log.exception("Failed to update live message for %s", name)

    def _update_streaks(self, name: str, old_stats: dict, new_stats: dict) -> dict[str, int]:
        """Advances the client-side live win streak per (game, mode) and persists it."""
        current = storage.get_streaks(name)
        updated = dict(current)

        for game_key, new_game_data in new_stats.items():
            if not isinstance(new_game_data, dict) or not new_game_data:
                continue
            old_game_data = old_stats.get(game_key) if isinstance(old_stats, dict) else None
            if not isinstance(old_game_data, dict):
                continue

            new_leaves = leaf_stat_dicts(new_game_data)
            old_leaves = leaf_stat_dicts(old_game_data)

            for mode_label, new_leaf in new_leaves.items():
                old_leaf = old_leaves.get(mode_label)
                if not isinstance(old_leaf, dict):
                    continue

                new_wins, new_played = extract_wins_played(new_leaf)
                old_wins, old_played = extract_wins_played(old_leaf)
                if None in (new_wins, new_played, old_wins, old_played):
                    continue  # this game has no recognizable wins/played fields

                streak_key = f"{game_key}|{mode_label or ''}"
                old_streak = current.get(streak_key, 0)
                new_streak = update_streak(old_streak, new_played - old_played, new_wins - old_wins)

                if new_streak != old_streak:
                    storage.set_streak(name, streak_key, new_streak)
                updated[streak_key] = new_streak

        return updated

    async def _send_alert(self, channel_id: int, name: str, old_stats: dict, new_stats: dict,
                           changes: list[tuple[str, float, float]], streaks: dict[str, int],
                           window_start_iso: str | None, window_end_iso: str):
        channel = self.bot.get_channel(channel_id)
        if channel is None:
            return

        grouped: dict[tuple[str, str | None], list[tuple[str, float, float]]] = {}
        for full_path, old_v, new_v in changes:
            game_key, mode_label, stat_key = split_game_mode(full_path)
            grouped.setdefault((game_key, mode_label), []).append((stat_key, old_v, new_v))

        end_time = datetime.fromisoformat(window_end_iso)
        if window_start_iso:
            start_time = datetime.fromisoformat(window_start_iso)
            window_desc = (f"🕒 Round likely finished between "
                            f"**{start_time.strftime('%H:%M:%S')}** and **{end_time.strftime('%H:%M:%S')} UTC**")
        else:
            window_desc = f"🕒 Detected at **{end_time.strftime('%H:%M:%S')} UTC**"

        embed = discord.Embed(
            title=f"📈 {name} just finished a round",
            description=f"{window_desc}\n_Round start time can't be determined this way._",
            color=0x2ECC71,
        )

        for (game_key, mode_label), entries in grouped.items():
            game_label = GAME_NAMES.get(game_key, game_key)
            title = f"{game_label} · {mode_label}" if mode_label else game_label

            lines = []
            for stat_key, old_v, new_v in entries[:6]:
                emoji, label = label_for_key(stat_key)
                lines.append(f"{emoji} **{label}**: {old_v} → **{new_v}**")

            mode_dict_new = _find_stats_dict(new_stats, game_key)
            mode_dict_old = _find_stats_dict(old_stats, game_key)
            if mode_label and isinstance(mode_dict_new, dict):
                for _, v in mode_dict_new.items():
                    if isinstance(v, dict):
                        mode_dict_new = v
                        break
            kd_new = compute_kd(mode_dict_new) if isinstance(mode_dict_new, dict) else None
            kd_old = compute_kd(mode_dict_old) if isinstance(mode_dict_old, dict) else None
            if kd_new is not None and kd_old is not None and kd_new != kd_old:
                lines.append(f"⚡ **KD**: {kd_old} → **{kd_new}**")

            streak_key = f"{game_key}|{mode_label or ''}"
            if streak_key in streaks:
                streak_val = streaks[streak_key]
                fire = "🔥🔥" if streak_val >= 5 else "🔥"
                lines.append(f"{fire} **Live Winstreak**: {streak_val}")

            embed.add_field(name=title, value="\n".join(lines), inline=False)

        try:
            await channel.send(embed=embed)
        except discord.HTTPException:
            log.exception("Failed to send alert for %s", name)

    @poll_loop.before_loop
    async def before_poll(self):
        await self.bot.wait_until_ready()

    @poll_loop.error
    async def poll_loop_error(self, error: BaseException):
        # Safety net: discord.ext.tasks stops a loop after an unhandled
        # exception. Log it and restart so tracking never silently dies.
        log.error("poll_loop crashed unexpectedly, restarting in 10s", exc_info=error)
        await asyncio.sleep(10)
        if not self.poll_loop.is_running():
            self.poll_loop.restart()


async def setup(bot: commands.Bot):
    await bot.add_cog(TrackingCog(bot))
