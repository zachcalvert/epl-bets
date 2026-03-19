# EPL Bets

[![CI](https://github.com/zachcalvert/epl-bets/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zachcalvert/epl-bets/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/zachcalvert/epl-bets/branch/main/graph/badge.svg)](https://codecov.io/gh/zachcalvert/epl-bets)

EPL betting demo built with Django, HTMX, Redis, and Celery. Live scores via WebSocket, real bookmaker odds, and simulated bet placement — all server-rendered with zero JavaScript frameworks.

**This just demo. No real money. No real gambling.**

**Live demo:** [eplbets.net](https://eplbets.net)

## Tech Stack

- **Django** — Server-side rendering, ORM, admin
- **HTMX** — Partial page updates, polling, WebSocket integration
- **Redis** — Cache, Celery broker, Channels layer (triple duty)
- **Celery** — Background API polling, bet settlement
- **Django Channels / Daphne** — WebSocket live score updates
- **PostgreSQL** — Persistent data store

## Architecture

```
         ┌────────────────────┐
         │       Browser      │
         │      HTMX + WS     │
         └────┬──────────┬────┘
              │          │ 
          HTTP/HTMX   WebSocket
         ┌────┴──-┐ ┌────┴---──┐
         │ Django │ │ Daphne/  │
         │        │ │ Channels │
         └────┬───┘ └───────┬──┘
              └──────┬──────┘
               ┌─────┴────────┐
               │     Redis    │
               └────┬───────┬─┘
            ┌───────┴──┐  ┌─┴───────┐
            │ Postgres │  │ Celery  │
            └──────────┘  └─────────┘
```

## Quick Start

```bash
git clone https://github.com/zachcalvert/epl-bets.git
cd epl-bets
cp .env.example .env   # Add your API keys
docker compose up -d
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_all
```

Then open `http://localhost:8000`.

## Seed Commands

`seed_all` is the master seed command — it runs all individual commands in dependency order:

| Step | Command | What it does |
|------|---------|--------------|
| 1 | `seed_epl` | Teams, fixtures, standings, and odds from external APIs |
| 2 | `seed_challenge_templates` | Challenge template definitions |
| 3 | `seed_badges` | Badge definitions |
| 4 | `seed_bots` | Bot user accounts |
| 5 | `backfill_stats` | UserStats from existing bet history |

All commands are idempotent (safe to re-run). Flags:

```bash
# Skip external API calls entirely (useful offline / in CI)
docker compose run --rm web python manage.py seed_all --skip-epl

# Use bundled JSON fixture instead of live API
docker compose run --rm web python manage.py seed_all --offline

# Skip odds fetch to save Odds API credits
docker compose run --rm web python manage.py seed_all --skip-odds
```

## Utility Commands

| Command | What it does | Options |
|---------|--------------|---------|
| `simulate_prematch` | Bots place bets and post comments on upcoming matches | `--matches N` (default: 3), `--reset-bets` (cancel pending bot bets first) |
| `reset_bot_comments` | Delete all bot-generated comments | `--yes` (skip confirmation) |

Example:
```bash
# Simulate bot activity on the 5 soonest matches
docker compose run --rm web python manage.py simulate_prematch --matches 5
```

## API Keys

Three free APIs power the app:

- **[football-data.org](https://www.football-data.org/)** — Fixtures, scores, standings (free tier: 10 req/min)
- **[The Odds API](https://the-odds-api.com/)** — Real bookmaker odds (free tier: 500 credits/month)
- **[Anthropic Claude API](https://console.anthropic.com/)** — Bot commentary generation (pay-as-you-go)

Add your keys to `.env` after copying `.env.example`.

## Deployment

Production is deployed on Fly at [eplbets.net](https://eplbets.net).
