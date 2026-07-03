# 🐝 HIVE STATS BOT

<div align="center">

```
██╗  ██╗██╗██╗   ██╗███████╗    ███████╗████████╗ █████╗ ████████╗███████╗
██║  ██║██║██║   ██║██╔════╝    ██╔════╝╚══██╔══╝██╔══██╗╚══██╔══╝██╔════╝
███████║██║██║   ██║█████╗      ███████╗   ██║   ███████║   ██║   ███████╗
██╔══██║██║╚██╗ ██╔╝██╔══╝      ╚════██║   ██║   ██╔══██║   ██║   ╚════██║
██║  ██║██║ ╚████╔╝ ███████╗    ███████║   ██║   ██║  ██║   ██║   ███████║
╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝    ╚══════╝   ╚═╝   ╚═╝  ╚═╝   ╚═╝   ╚══════╝
```

**A Discord bot for Hive (Minecraft Bedrock) stats — polling-based, embed-driven, crash-resistant.**

![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white)
![discord.py](https://img.shields.io/badge/discord.py-2.4+-5865F2?style=for-the-badge&logo=discord&logoColor=white)
![Railway](https://img.shields.io/badge/Deploy-Railway-0B0D0E?style=for-the-badge&logo=railway&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge)

</div>

---

## 📖 Table of Contents

- [What is this?](#-what-is-this)
- [⚠️ Limitations — please read](#️-limitations--please-read)
- [Features](#-features)
- [Commands](#-commands)
- [Architecture](#-architecture)
- [Project Structure](#-project-structure)
- [How it works](#-how-it-works)
- [Setup — Step by Step](#-setup--step-by-step)
- [Launching on Railway](#-launching-on-railway)
- [Environment Variables](#-environment-variables)
- [Troubleshooting](#-troubleshooting)
- [FAQ](#-faq)

---

## 🎯 What is this?

`hive-stats-bot` is a modular Discord bot that queries the official Hive API
(`api.playhive.com/v0`) and displays player stats — on demand via slash
command, or automatically as an alert when a tracked player's stats change.

Built with `discord.py` using the Cog pattern, with defensive error handling
throughout: a single bad API response, missing field, or formatting edge
case can't take the whole bot down or silently kill the background tracker.

---

## ⚠️ Limitations — please read

The Hive API does **not** expose live online status, current game/server, or
a player's location — that's a deliberate anti-sniping design choice by
Hive. Nothing built on top of this API can show that in real time, no matter
how it's built.

**What this bot does instead:**
- **`/online`** — infers "recently active" from the *last time a stat change
  was detected*. Not a real status; labeled as such in the response.
- **Round-finished alerts** — report a *time window* (between the last clean
  check and the check that found a change), never an exact live moment.
  Round **start** time cannot be determined at all this way — there is no
  "player joined a game" signal in the API, only stat totals.
- **Live winstreak** — Hive's API doesn't provide a winstreak field, so this
  bot counts it client-side: detected win → +1, detected non-win round → 0.
  If several rounds happen within one poll interval and at least one was a
  loss, it conservatively resets to 0 (can't tell which round came first).

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Stats on Demand** | Stats for 14 Hive games, cleanly formatted with emoji + KD |
| 🔍 **Raw JSON Viewer** | Inspect raw data to discover new/undocumented fields |
| 👁️ **Player Watchlist** | Track any number of players per channel |
| 🔔 **Round-Finished Alerts** | Posts an embed with a time window when stats increase |
| 🔥 **Live Winstreak** | Client-side computed streak, persisted across restarts |
| 🟢 **Activity Indicator** | `/online` shows a best-effort "recently active" status |
| 🧩 **Cog Architecture** | Cleanly separated modules, easy to extend |
| 🛡️ **Crash-Resistant Polling** | Per-player error isolation + auto-restarting background loop |
| ☁️ **One-Click Deploy** | Runs straight from GitHub via Railway |

---

## 💬 Commands

| Command | Arguments | Description |
|---|---|---|
| `/stats` | `name`, `game` *(optional)* | Shows a player's stats |
| `/raw` | `name`, `game` *(optional)* | Shows the raw API response as JSON |
| `/track` | `name` | Starts tracking a player in the current channel |
| `/untrack` | `name` | Stops tracking a player |
| `/tracked` | – | Lists all currently tracked players |
| `/streak` | `name` | Shows the current client-side live winstreak(s) |
| `/online` | `name` | Shows a best-effort "recently active" indicator |

**Game codes:** `wars` `dr` `hide` `sg` `murder` `sky` `ctf` `drop` `ground` `build` `party` `bridge` `grav` `bed`

```
/stats name:Steve123 game:bed
/track name:Steve123
/online name:Steve123
/streak name:Steve123
```

---

## 🏗️ Architecture

```
┌─────────────┐   Slash Commands   ┌──────────────┐
│   Discord    │ ◄─────────────────► │   bot.py     │
│   Server     │                     │  (loader +   │
└─────────────┘                     │ error handler)│
                                     └──────┬───────┘
                                            │ loads
                    ┌────────────────────────┼────────────────────────┐
                    ▼                                                 ▼
           ┌────────────────┐                                ┌────────────────┐
           │ cogs/stats.py  │                                │cogs/tracking.py│
           │ /stats  /raw   │                                │/track /untrack │
           └───────┬────────┘                                │/streak /online │
                    │                                         │  poll_loop()   │
                    │                                         └───────┬────────┘
                    └──────────────┐                   ┌──────────────┘
                                    ▼                   ▼
                             ┌─────────────┐    ┌─────────────┐
                             │ hive_api.py │    │ storage.py  │
                             │ API wrapper │    │ JSON store  │
                             └──────┬──────┘    └─────────────┘
                                    ▼
                         api.playhive.com/v0

              formatting.py: shared labels, KD, mode detection,
                     streak math — used by both cogs
```

---

## 📂 Project Structure

```
hive-bot/
├── bot.py                 # Entry point — starts the bot, loads cogs, global error handler
├── hive_api.py             # Async wrapper around the Hive REST API
├── storage.py               # Persists the watchlist + streaks + timestamps as JSON
├── formatting.py             # Shared labels, KD calc, mode detection, streak logic
├── requirements.txt
├── Procfile                 # Start command for Railway
├── .env.example
├── .gitignore
├── README.md                 # ← you are here
└── cogs/
    ├── __init__.py
    ├── stats.py            # /stats, /raw
    └── tracking.py         # /track, /untrack, /tracked, /streak, /online, poll_loop
```

---

## ⚙️ How it works

1. **Startup:** `bot.py` reads `.env`, builds the Discord client + `HiveAPI`
   client, loads both cogs, and registers a global error handler for slash
   commands so failures show a clear message instead of a silent
   "This interaction failed."
2. **Slash sync:** on `on_ready`, the bot syncs its command tree with
   Discord and logs how many commands were synced.
3. **`/stats` / `/raw`:** fetch from `api.playhive.com/v0/game/all/...` and
   render an embed or raw JSON. Wrapped in try/except so any failure returns
   a clean error message instead of crashing.
4. **`/track`:** stores the player in `data/tracked.json`.
5. **`poll_loop`** (runs every `POLL_INTERVAL_SECONDS`): for each tracked
   player — in its own try/except so one player's failure can't affect
   others — fetches current stats, diffs them against the last snapshot,
   updates the live winstreak, updates the "last active" timestamp, and
   posts an alert if anything increased. If the loop itself ever crashes
   unexpectedly, a registered error handler logs it and restarts it after
   10 seconds.

---

## 🚀 Setup — Step by Step

### 1. Create a Discord bot
1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**
2. **Bot** tab → **Reset Token** → copy it → this is your `DISCORD_TOKEN`
3. **Installation** tab (or **OAuth2 → URL Generator** in the classic view):
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`, `Use Application Commands`
   - Save changes, then copy the install link
4. Open the link in a browser tab → select your server → Authorize

### 2. Get a Hive API key (recommended)
Send a plain-text request to **api@hivemc.com** — without a key, rate limits are very low.

### 3. Add the files
Add all files exactly as laid out in the project structure above.

---

## ☁️ Launching on Railway

1. [railway.app](https://railway.app) → sign in with GitHub
2. **New Project → Deploy from GitHub repo** → select your repo
3. Railway auto-detects Python (Nixpacks) and uses the `Procfile`
4. Set the **Variables** (see table below)
5. **Settings → Volumes → Add Volume** → mount path `/data` (otherwise the
   watchlist, streaks, and activity data are lost on every redeploy)
6. Done — Railway auto-deploys on every push to `main`

Check **Deployments → View Logs → Deploy Logs**. You should see:
```
Loaded cog: cogs.stats
Loaded cog: cogs.tracking
Logged in as YourBot#1234 | synced 7 slash command(s)
```

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from the Developer Portal |
| `HIVE_API_KEY` | recommended | Significantly raises the API rate limit |
| `POLL_INTERVAL_SECONDS` | – | How often tracked players are checked (default: `45`) |
| `ALERT_CHANNEL_ID` | – | Fallback channel if `/track` runs without channel context |
| `DATA_FILE` | – | Path to the watchlist JSON (Railway: `/data/tracked.json`) |

---

## 🔧 Troubleshooting

**A command doesn't show up in Discord at all**
1. Confirm the file that defines it is actually committed and pushed to GitHub
2. Confirm Railway redeployed after that push (Deployments tab, latest entry should be after your commit time, status "Success")
3. Check Deploy Logs for `Loaded cog: cogs.tracking` and `synced N slash command(s)`
4. Fully close and reopen the Discord app (slash commands are cached client-side)
5. New commands can take up to an hour to propagate globally, though it's usually minutes

**Alerts stopped appearing after they used to work**
- Check Deploy Logs for a line starting with `poll_loop crashed unexpectedly` — this version auto-restarts the loop after logging, so it should recover within 10s on its own. If you see repeated crashes, copy the traceback from the logs so the root cause can be fixed.
- Make sure a Volume is mounted at `/data` — without persistence, a redeploy wipes the tracked list and `/track` needs to be re-run.

**"This interaction failed" in Discord**
- As of this version, command errors are caught and reported back as a visible message instead. If you still see the generic Discord error, check Deploy Logs — the actual exception is logged there.

---

## ❓ FAQ

**Does the bot show when someone comes online/goes offline?**
No official API can. `/online` gives a best-effort "recently active" guess based on stat changes — clearly labeled as such.

**Why don't I see `winstreak` in `/stats`?**
Hive's API doesn't expose that field. Use `/streak` for the client-side computed live winstreak instead.

**Can I track multiple players at once?**
Yes — run `/track` for each, in whichever channel you want alerts to post in.
