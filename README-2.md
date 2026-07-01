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

**A Discord bot for Hive (Minecraft Bedrock) stats — automated, live-polled, embed-based.**

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
- [FAQ](#-faq)
- [Roadmap](#-roadmap)

---

## 🎯 What is this?

`hive-stats-bot` is a lightweight, modular Discord bot that queries the **official Hive
API** (`api.playhive.com/v0`) and displays player stats directly in your server — on
demand via slash command, or automatically as an alert when a tracked player's stats
change.

Built with `discord.py` using the **Cog pattern** (each feature group lives in its own
file), so you can extend it piece by piece instead of maintaining one 500-line monolith.

---

## ⚠️ Limitations — please read

The Hive API does **not** expose live online status, current game/server, or a player's
location. That's a deliberate design choice by Hive (anti-sniping measure).

**What the bot does instead:** it periodically (`POLL_INTERVAL_SECONDS`) checks tracked
players' stats and reports when a number has increased (e.g. `wins`). That's a **delayed
signal** that a match was just finished — not real-time tracking. Anything more than
that simply isn't possible with the official API.

---

## ✨ Features

| Feature | Description |
|---|---|
| 📊 **Stats on Demand** | Stats for 14 Hive games at the press of a button, as an embed |
| 🔍 **Raw JSON Viewer** | Inspect raw data to discover new/undocumented fields |
| 👁️ **Player Watchlist** | Track any number of players per channel |
| 🔔 **Auto-Alerts** | Automatic embed alert when a stat changes |
| 🧩 **Cog Architecture** | Cleanly separated modules, easy to extend |
| 💾 **Persistent Watchlist** | JSON-based, Railway Volume compatible |
| ☁️ **One-Click Deploy** | Runs straight from GitHub via Railway, no server management needed |

---

## 💬 Commands

| Command | Arguments | Description |
|---|---|---|
| `/stats` | `name`, `game` *(optional)* | Shows a player's stats. No `game` = overview of all games |
| `/raw` | `name`, `game` *(optional)* | Shows the raw API response as a JSON code block |
| `/track` | `name` | Starts tracking a player, alerts post in the current channel |
| `/untrack` | `name` | Stops tracking a player |
| `/tracked` | – | Lists all currently tracked players |

**Game codes:** `wars` `dr` `hide` `sg` `murder` `sky` `ctf` `drop` `ground` `build` `party` `bridge` `grav` `bed`

```
/stats name:Steve123 game:bed
/raw name:Steve123
/track name:Steve123
```

---

## 🏗️ Architecture

```
┌─────────────┐      Slash Commands      ┌──────────────┐
│   Discord    │ ◄───────────────────────► │   bot.py     │
│   Server     │                            │  (Loader)    │
└─────────────┘                            └──────┬───────┘
                                                    │ loads
                          ┌─────────────────────────┼─────────────────────────┐
                          ▼                                                   ▼
                 ┌────────────────┐                                 ┌────────────────┐
                 │ cogs/stats.py  │                                 │cogs/tracking.py│
                 │ /stats  /raw   │                                 │/track /untrack │
                 └───────┬────────┘                                 │  poll_loop()   │
                         │                                          └───────┬────────┘
                         └──────────────┐                    ┌──────────────┘
                                         ▼                    ▼
                                  ┌─────────────┐      ┌─────────────┐
                                  │ hive_api.py │      │ storage.py  │
                                  │ API Wrapper │      │ JSON Store  │
                                  └──────┬──────┘      └─────────────┘
                                         ▼
                              api.playhive.com/v0
```

---

## 📂 Project Structure

```
hive-bot/
├── bot.py                 # Entry point — starts the bot, loads all cogs
├── hive_api.py             # Async wrapper around the Hive REST API
├── storage.py               # Persists the watchlist as a JSON file
├── requirements.txt
├── Procfile                 # Start command for Railway
├── .env.example
├── .gitignore
├── README.md                 # ← you are here
└── cogs/
    ├── __init__.py
    ├── stats.py            # /stats, /raw
    └── tracking.py         # /track, /untrack, /tracked, poll_loop
```

---

## ⚙️ How it works

1. **Startup:** `bot.py` reads `.env`, builds the Discord client + `HiveAPI` client, and
   loads both cogs as extensions.
2. **Slash sync:** on the `on_ready` event, the bot syncs its command tree with
   Discord — the commands then appear in your server.
3. **`/stats` / `/raw`:** `StatsCog` calls into `hive_api.py`, which fetches from
   `api.playhive.com/v0/game/all/...` and turns the result into an embed or raw output.
4. **`/track`:** `storage.py` stores the player in `data/tracked.json` (name + channel ID
   + `last_stats: null`).
5. **`poll_loop` (runs every `POLL_INTERVAL_SECONDS`):** for each tracked player,
   `get_all_stats()` is called and recursively compared against the last snapshot
   (`diff_stats()`); any increase in a numeric field triggers an alert embed in the
   stored channel.

---

## 🚀 Setup — Step by Step

### 1. Create a Discord bot
1. [discord.com/developers/applications](https://discord.com/developers/applications) → **New Application**
2. **Bot** tab → **Reset Token** → copy it → this is your `DISCORD_TOKEN`
3. **OAuth2 → URL Generator** tab:
   - Scopes: `bot`, `applications.commands`
   - Permissions: `Send Messages`, `Embed Links`
4. Open the generated link → invite the bot to your server

### 2. Get a Hive API key (recommended)
Send a plain-text request to **api@hivemc.com** — without a key, rate limits are very low.

### 3. Set up the repo files
Add all files as laid out in the project structure above (copy-paste from the earlier
chat history, or clone the repo directly from GitHub if you've already pushed it).

---

## ☁️ Launching on Railway

1. [railway.app](https://railway.app) → sign in with GitHub
2. **New Project → Deploy from GitHub repo** → select your `hive-bot` repo
3. Railway auto-detects Python (Nixpacks) and uses the `Procfile`
4. Set the **Variables** (see table below)
5. **Settings → Volumes → Add Volume** → mount path `/data` (otherwise the watchlist is
   lost on every redeploy!)
6. Done — Railway auto-deploys on every push to `main`

Check **Deployments → Logs** — you should see `Logged in as <BotName>` once it's running.

---

## 🔑 Environment Variables

| Variable | Required | Description |
|---|---|---|
| `DISCORD_TOKEN` | ✅ | Bot token from the Developer Portal |
| `HIVE_API_KEY` | recommended | Significantly raises the API rate limit |
| `POLL_INTERVAL_SECONDS` | – | How often tracked players are checked (default: `120`) |
| `ALERT_CHANNEL_ID` | – | Fallback channel if `/track` runs without channel context |
| `DATA_FILE` | – | Path to the watchlist JSON (Railway: `/data/tracked.json`) |

---

## ❓ FAQ

**Does the bot show when someone comes online/goes offline?**
No — no Hive API-based app can, because Hive doesn't expose that data publicly.

**Why don't I see `winstreak` in `/stats`?**
Not every game has that field. Use `/raw name:<player> game:bed` to see the full raw
data and check which fields actually exist.

**Can I track multiple players at once?**
Yes, as many as you want — just run `/track` in whichever channel you want the alerts
to post in.

**The bot isn't responding to slash commands?**
Discord can take up to an hour to propagate global commands, though it usually shows up
within a few minutes of the first startup.

---

## 🗺️ Roadmap

- [ ] `/leaderboard <game>` — global top lists
- [ ] Configurable alert thresholds (e.g. only alert past a certain wins increase)
- [ ] SQLite instead of JSON for larger watchlists
- [ ] Graphical stats history (chart embed)

---

<div align="center">

**Built with 🐍 Python & discord.py — running 24/7 on Railway**

</div>
