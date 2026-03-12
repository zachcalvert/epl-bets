# EPL Bets

[![CI](https://github.com/zachcalvert/epl-bets/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/zachcalvert/epl-bets/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/zachcalvert/epl-bets/branch/main/graph/badge.svg)](https://codecov.io/gh/zachcalvert/epl-bets)
![tests](https://img.shields.io/badge/tests-192%20passing-2ea44f)
![coverage gate](https://img.shields.io/badge/coverage%20gate-98%25-2ea44f)
![local suite](https://img.shields.io/badge/local%20suite-%3C5s-2ea44f)
[![live demo](https://img.shields.io/badge/live%20demo-eplbets.net-0a66c2)](https://eplbets.net)

EPL betting demo built with Django, HTMX, Redis, and Celery. Live scores via WebSocket, real bookmaker odds, and simulated bet placement — all server-rendered with zero JavaScript frameworks.

**This is just a demo. No real money. No real gambling.**

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
docker compose run --rm web python manage.py seed_epl
```

Then open `http://localhost:8000`.

## API Keys

Two free APIs power the data:

- **[football-data.org](https://www.football-data.org/)** — Fixtures, scores, standings (free tier: 10 req/min)
- **[The Odds API](https://the-odds-api.com/)** — Real bookmaker odds (free tier: 500 credits/month)

Add your keys to `.env` after copying `.env.example`.

## Deployment

Production is deployed on Fly at [eplbets.net](https://eplbets.net).

Deploys are configured to run automatically from GitHub Actions on every push to `main`.
To enable automated deploys in GitHub, add a repository secret named `FLY_API_TOKEN` with a Fly deploy token scoped to the `epl-bets` app.
