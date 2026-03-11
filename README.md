# Pitch & Odds

EPL betting demo built with Django, HTMX, Redis, and Celery. Live scores via WebSocket, real bookmaker odds, and simulated bet placement — all server-rendered with zero JavaScript frameworks.

**This is a portfolio demo. No real money. No real gambling.**

## Tech Stack

- **Django** — Server-side rendering, ORM, admin
- **HTMX** — Partial page updates, polling, WebSocket integration
- **Redis** — Cache, Celery broker, Channels layer (triple duty)
- **Celery** — Background API polling, bet settlement
- **Django Channels / Daphne** — WebSocket live score updates
- **PostgreSQL** — Persistent data store

## Architecture

```
         ┌─────────────┐
         │   Browser    │
         │ HTMX + WS   │
         └──┬───────┬───┘
    HTTP/HTMX│       │WebSocket
         ┌──┴──┐ ┌──┴──────┐
         │Django│ │Daphne/  │
         │     │ │Channels │
         └──┬──┘ └──┬──────┘
            └──┬────┘
          ┌────┴────┐
          │  Redis   │
          └──┬────┬──┘
        ┌────┴┐ ┌─┴──────┐
        │Postgres│ │ Celery  │
        └───────┘ └────────┘
```

## Quick Start

```bash
git clone https://github.com/zachcalvert/epl-bets.git
cd epl-bets
cp .env.example .env   # Add your API keys
docker compose up -d
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_epl
docker compose run --rm web python manage.py runserver 0.0.0.0:8000
```

## API Keys

Two free APIs power the data:

- **[football-data.org](https://www.football-data.org/)** — Fixtures, scores, standings (free tier: 10 req/min)
- **[The Odds API](https://the-odds-api.com/)** — Real bookmaker odds (free tier: 500 credits/month)

Add your keys to `.env` after copying `.env.example`.
