# EPL Bets

## Project Overview

A full-stack portfolio demo: fake EPL sports betting platform built with **Django + HTMX + Redis + Celery**. Real EPL data, real bookmaker odds, simulated betting. No JavaScript frameworks — everything server-rendered with HTMX for interactivity.

## Tech Stack

- **Django 5.x** — views, ORM, admin, templates
- **HTMX 2.0** — partial updates, polling, WebSocket integration (via htmx-ext-ws)
- **Tailwind CSS** (CDN) — dark theme with custom color palette
- **Redis** — cache, Celery broker, Channels layer
- **Celery + Celery Beat** — background tasks, periodic API polling
- **Django Channels / Daphne** — ASGI, WebSocket consumers
- **PostgreSQL 16** — persistent data store
- **Docker Compose** — local dev orchestration (web, worker, beat, redis, db)

## Running Commands

Always run management commands through Docker:
```bash
docker compose run --rm web python manage.py <command>
```

Common commands:
- `migrate` — run migrations
- `seed_epl` — seed initial EPL data from APIs
- `createsuperuser` — create admin user

## Django Apps

| App | Purpose | Key Files |
|-----|---------|-----------|
| `config/` | Settings, Celery config, URL root, ASGI | `settings.py`, `celery.py`, `asgi.py` |
| `users/` | Custom user model (email-based auth) | `models.py` |
| `matches/` | Match, Team, Standing models; dashboard, fixtures, league table, match detail | `models.py`, `views.py`, `services.py`, `tasks.py`, `consumers.py` |
| `betting/` | Odds, BetSlip, UserBalance; odds board, bet placement, my bets | `models.py`, `views.py`, `services.py`, `tasks.py`, `forms.py` |
| `website/` | Base template, navbar, footer, auth views, How It Works page | `views.py`, `forms.py`, `templates/website/base.html` |

## Project Structure

```
config/          Django project config (settings, urls, celery, asgi)
users/           Custom user model
matches/         Core football data + pages
  services.py    football-data.org API client
  tasks.py       Celery tasks (fetch_fixtures, fetch_standings, fetch_live_scores)
  consumers.py   WebSocket consumers for live scores
  templatetags/  Custom filters (status_badge, score_display, format_odds)
betting/         Betting data + pages
  services.py    The Odds API client
  tasks.py       Celery tasks (fetch_odds, settle_bets)
website/         Shared layout, auth, static assets, How It Works page
  static/        CSS (styles.css), images
docs/            Phase implementation docs
```

## Templates & HTMX Patterns

- Templates use `{% extends "website/base.html" %}` with `{% block content %}`
- HTMX partials live in `<app>/templates/<app>/partials/`
- Polling: `hx-trigger="every 30s"` on odds board and match detail odds
- WebSocket: `hx-ext="ws" ws-connect="/ws/live/..."` on dashboard and match detail
- OOB updates: `hx-swap-oob="true"` for live score pushes
- Loading indicators: `hx-indicator` + `.spinner` CSS class
- Form submission: `hx-post` with `hx-disabled-elt` to prevent double-click
- Empty states: reusable `{% include "website/components/empty_state.html" %}`

## Styling

- Tailwind CDN with custom colors defined in `base.html` `tailwind.config`
- Custom CSS in `website/static/website/css/styles.css` (HTMX transitions, spinners, toasts, mobile menu)
- Color palette: dark (`#1a1a2e`), surface (`#16213e`), accent (`#00e676`), danger (`#ff1744`), warning (`#ffab00`), muted (`#9e9e9e`), epl (`#38003c`)
- Fonts: Oswald (headings), Inter (body), Roboto Mono (numbers)

## External APIs

- **football-data.org** (v4) — fixtures, scores, standings. Free tier: 10 req/min. Key: `FOOTBALL_DATA_API_KEY`
- **The Odds API** — bookmaker odds. Free tier: 500 credits/month. Key: `ODDS_API_KEY`

## Linting

Uses **ruff** with `select = ["E", "F", "I"]`, target Python 3.11.

## Documentation

Implementation plan and phase docs live in `docs/`:
- `0000-PLAN.md` — master plan with architecture, models, pages, implementation phases
- `0001-PHASE_1.md` through `0004-PHASE_4.md` — detailed phase implementation notes
- Phases 5 and 6 are complete but don't have standalone docs yet
