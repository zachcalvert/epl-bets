# Calvert Labs — Full-Stack Demo Application

## Overview

A fully transparent, full-stack demo application showcasing **Django + HTMX + Redis + Celery** through a fake English Premier League sports betting platform. The app displays real EPL data (fixtures, standings, odds) with real-time updates powered by WebSockets and background task processing — all rendered server-side with HTMX. No JavaScript frameworks.

The goal is to serve as a portfolio piece that demonstrates the entire stack working together in a production-like architecture, while being fun and visually engaging.

---

## Concept: "Pitch & Odds" — EPL Betting Demo

A Fanatics/DraftKings-style interface for English Premier League matches. Users can browse live and upcoming fixtures, view match odds from real bookmakers, check league standings, and place simulated bets — all updated in real time.

**This is a demo app. No real money. No real gambling.** A prominent disclaimer will be displayed site-wide.

### Core User Experience

1. **Live Match Dashboard** — Today's fixtures with scores updating in real time via WebSocket
2. **Match Detail** — Head-to-head stats, lineups, odds comparison from multiple bookmakers
3. **League Table** — Current EPL standings, updated after each match
4. **Betting Slip** — Simulated bet placement with fake balance (demonstrates form handling + Celery task processing)
5. **Odds Board** — Real bookmaker odds for upcoming matches, auto-refreshing

---

## Data Sources (Free APIs)

### Primary: football-data.org (v4)
- **What:** Fixtures, scores, standings, team/squad info
- **Free tier:** 10 requests/min, EPL guaranteed free forever
- **API key:** Required (free registration)
- **Use for:** Core match data, league table, fixture list

### Supplemental: The Odds API
- **What:** Pre-match and live odds from real bookmakers (Bet365, DraftKings, etc.)
- **Free tier:** 500 credits/month
- **API key:** Required (free registration)
- **Use for:** Real betting odds display, odds comparison tables

### Seed Data: openfootball/football.json (GitHub)
- **What:** Historical EPL match results (static JSON)
- **Use for:** Database seeding, historical stats, development without API calls

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Browser                               │
│  Django Templates + HTMX + WebSocket (htmx-ext-ws)          │
└──────────────┬──────────────────────┬───────────────────────┘
               │ HTTP/HTMX            │ WebSocket
               ▼                      ▼
┌──────────────────────┐  ┌──────────────────────┐
│   Django (Gunicorn)  │  │   Daphne (ASGI)      │
│   Views + API        │  │   WebSocket Channels  │
└──────────┬───────────┘  └──────────┬───────────┘
           │                         │
           ▼                         ▼
┌──────────────────────────────────────────────┐
│              Redis                            │
│  Cache │ Celery Broker │ Channel Layer        │
└──────────────────────────────────────────────┘
           │
           ▼
┌──────────────────────┐  ┌──────────────────────┐
│   PostgreSQL         │  │   Celery Worker       │
│   Match/odds/bet     │  │   API polling tasks   │
│   data               │  │   Odds refresh        │
│                      │  │   Score updates        │
└──────────────────────┘  │   Bet settlement       │
                          └──────────────────────┘
```

### How the Stack Components Demo

| Component | Role in App | What It Demonstrates |
|-----------|------------|---------------------|
| **Django** | Server-side rendering, models, views, admin | Full MVC, ORM, migrations, auth |
| **HTMX** | Partial page updates, real-time UI, form submission | Modern interactivity without JS frameworks |
| **Redis** | Cache layer, message broker, WebSocket channel layer | Multi-purpose in-memory data store |
| **Celery** | Periodic API polling, bet settlement, odds refresh | Background task processing, scheduled jobs |
| **Channels** | WebSocket connections for live score updates | Real-time bidirectional communication |
| **PostgreSQL** | Persistent storage for all match/odds/bet data | Relational data modeling |

---

## Data Models

### `Match`
- `external_id` — football-data.org match ID
- `home_team`, `away_team` — FK to Team
- `home_score`, `away_score` — nullable (null = not started)
- `status` — scheduled / live / finished / postponed
- `matchday` — EPL matchday number
- `kickoff` — datetime
- `season` — e.g. "2025-26"

### `Team`
- `external_id` — football-data.org team ID
- `name`, `short_name`, `tla` (three-letter abbreviation)
- `crest_url` — team badge image URL
- `venue` — stadium name

### `Standing`
- `team` — FK to Team
- `season`
- `position`, `played`, `won`, `drawn`, `lost`
- `goals_for`, `goals_against`, `goal_difference`, `points`

### `Odds`
- `match` — FK to Match
- `bookmaker` — name (e.g. "Bet365")
- `home_win`, `draw`, `away_win` — decimal odds
- `fetched_at` — when odds were pulled

### `BetSlip`
- `user` — FK to User (uses existing auth system)
- `match` — FK to Match
- `selection` — home_win / draw / away_win
- `odds_at_placement` — locked-in odds
- `stake` — decimal (fake currency)
- `status` — pending / won / lost / void
- `payout` — calculated on settlement

### `UserBalance`
- `user` — FK to User (one-to-one)
- `balance` — decimal, starts at 1000.00 (fake credits)

---

## Pages & HTMX Interactions

### 1. Dashboard (`/`) — Live Match Day
- Grid of today's match cards
- Each card shows teams, score, status, top odds
- **HTMX:** Cards swap via WebSocket when scores update (`hx-ext="ws"`)
- **HTMX:** Click card to load match detail into side panel (`hx-get`, `hx-target`)

### 2. Fixtures (`/fixtures/`)
- Week-by-week fixture list with matchday selector
- **HTMX:** Matchday tabs load fixture list without page reload (`hx-get`, `hx-swap`)

### 3. Match Detail (`/match/<id>/`)
- Full match info: lineups, events, head-to-head
- Odds comparison table across bookmakers
- Bet placement form
- **HTMX:** Odds table auto-refreshes every 30s (`hx-trigger="every 30s"`)
- **HTMX:** Bet form submits without page reload (`hx-post`)
- **HTMX:** Live score updates via WebSocket

### 4. League Table (`/table/`)
- Full EPL standings with form indicators (W/D/L last 5)
- **HTMX:** Table refreshes on WebSocket push after match completion

### 5. My Bets (`/bets/`)
- User's bet history with status (pending/won/lost)
- Running P&L display
- **HTMX:** Bet statuses update live as matches finish

### 6. Odds Board (`/odds/`)
- All upcoming matches with odds from multiple bookmakers
- Sortable/filterable
- **HTMX:** Auto-refreshing odds (`hx-trigger="every 60s"`)
- **HTMX:** Quick-bet buttons that add to slip (`hx-post`)

---

## Celery Tasks

### Periodic (Celery Beat)
- `fetch_fixtures` — Pull upcoming EPL fixtures from football-data.org (every 6 hours)
- `fetch_standings` — Pull current league table (every 6 hours)
- `fetch_live_scores` — Poll for live match scores during match windows (every 60s when matches are live)
- `fetch_odds` — Pull latest odds from The Odds API (every 30 minutes)

### Event-Driven
- `settle_bets` — When a match status changes to "finished", settle all pending bets for that match
- `update_balances` — Credit winnings to user balances after bet settlement
- `broadcast_score_update` — Push score change to WebSocket channel layer

---

## Technical Implementation

### New Django Apps

#### `matches` — Core data (matches, teams, standings)
```
matches/
├── models.py          # Match, Team, Standing
├── views.py           # Dashboard, fixtures, match detail, league table
├── urls.py
├── admin.py           # Full admin for all models
├── consumers.py       # WebSocket consumer for live scores
├── routing.py         # WebSocket URL routing
├── tasks.py           # Celery tasks for API polling
├── services.py        # API client wrappers (football-data.org)
├── templatetags/
│   └── match_tags.py  # Custom template tags (score display, status badges)
└── templates/
    └── matches/
        ├── dashboard.html
        ├── fixtures.html
        ├── match_detail.html
        ├── league_table.html
        └── partials/        # HTMX partial templates
            ├── match_card.html
            ├── score_update.html
            ├── odds_table.html
            └── standings_row.html
```

#### `betting` — Odds, bets, user balance
```
betting/
├── models.py          # Odds, BetSlip, UserBalance
├── views.py           # Odds board, bet placement, my bets
├── urls.py
├── admin.py
├── tasks.py           # Celery tasks for odds fetching, bet settlement
├── services.py        # The Odds API client
├── forms.py           # Bet placement form
└── templates/
    └── betting/
        ├── odds_board.html
        ├── my_bets.html
        └── partials/
            ├── bet_slip.html
            ├── odds_row.html
            └── bet_status.html
```

#### `website` — Shared layout, static assets, landing
```
website/
├── templates/
│   └── website/
│       ├── base.html          # Master template (nav, footer, Tailwind, HTMX)
│       └── components/        # Reusable template includes
│           ├── navbar.html
│           ├── footer.html
│           └── disclaimer.html
├── static/
│   └── website/
│       ├── css/styles.css
│       └── images/
└── views.py                   # Static pages if needed
```

### New Dependencies

```toml
# Core
django-htmx = "*"          # HTMX middleware & helpers
channels = {extras = ["daphne"]}  # WebSocket support
channels-redis = "*"        # Redis channel layer
celery = {extras = ["redis"]}     # Task queue
django-celery-beat = "*"    # Periodic task scheduler
redis = "*"                 # Redis client
httpx = "*"                 # Async HTTP client for API calls

# Dev
django-debug-toolbar = "*"  # Debug panel
```

### Docker Compose Services

```yaml
services:
  web:        # Django dev server (or Daphne for WebSocket support)
  worker:     # Celery worker
  beat:       # Celery Beat scheduler
  redis:      # Redis (cache + broker + channel layer)
  db:         # PostgreSQL (existing)
```

### Settings Additions
- `CHANNEL_LAYERS` — Redis-backed channel layer
- `CELERY_BROKER_URL` — `redis://redis:6379/0`
- `CELERY_RESULT_BACKEND` — `redis://redis:6379/0`
- `CELERY_BEAT_SCHEDULER` — `django_celery_beat.schedulers:DatabaseScheduler`
- `CACHES` — Redis cache backend
- `FOOTBALL_DATA_API_KEY` — env var
- `ODDS_API_KEY` — env var

---

## Design Direction

### Dark theme, sports/betting aesthetic
- Dark background with high-contrast data displays
- Green accent for live matches and winning bets
- Red for losses, amber for pending
- Clean data-dense layout inspired by betting platforms
- Responsive — works on mobile (common for betting UIs)

### Color Palette
- **Background**: Deep charcoal `#1a1a2e`
- **Surface**: Slightly lighter `#16213e`
- **Primary accent**: Electric green `#00e676` (live, wins)
- **Danger**: Red `#ff1744` (losses)
- **Warning**: Amber `#ffab00` (pending, caution)
- **Text**: White `#f5f5f5`
- **Muted**: Gray `#9e9e9e`
- **EPL Purple**: `#38003c` (subtle nod to the league branding)

### Typography
- Headings: `Space Groto` or `Oswald` (bold, sporty)
- Body/Data: `Inter` or `Roboto Mono` for odds/numbers (tabular figures)

---

## Implementation Order

### Phase 1: Foundation
1. Add new dependencies to `pyproject.toml`
2. Update `docker-compose.yml` with Redis, Celery worker, Celery Beat
3. Configure Channels, Celery, and Redis in settings
4. Create `website` app with `base.html` (Tailwind CDN + HTMX CDN + dark theme)
5. Create `matches` app with models (Match, Team, Standing)
6. Create `betting` app with models (Odds, BetSlip, UserBalance)
7. Run migrations, register models in admin

### Phase 2: Data Pipeline
8. Build football-data.org API client (`matches/services.py`)
9. Build The Odds API client (`betting/services.py`)
10. Create Celery tasks for fixture/standings/odds fetching
11. Create management command to seed initial data (`python manage.py seed_epl`)
12. Set up Celery Beat schedule for periodic polling

### Phase 3: Core Pages
13. Dashboard — live match day cards
14. Fixtures — matchday-by-matchday browser
15. League Table — full standings
16. Match Detail — stats, odds, bet form
17. Odds Board — all upcoming odds

### Phase 4: Real-Time Features
18. WebSocket consumer for live score updates
19. HTMX WebSocket extension integration on dashboard
20. Auto-refreshing odds via HTMX polling
21. Live bet status updates

### Phase 5: Betting Flow
22. Bet placement form + validation
23. User balance management
24. Bet settlement Celery task
25. My Bets page with history and P&L

### Phase 6: Polish
26. Mobile responsiveness
27. Loading states and HTMX transitions
28. Error handling and empty states
29. "How It Works" page explaining the stack (transparency goal)
30. README with architecture diagram and setup instructions

---

## Transparency Features

Since the goal is to demo the stack transparently:

- **"Under the Hood" panel** — collapsible sidebar showing what just happened (which Celery task ran, what WebSocket message was sent, cache hit/miss)
- **Tech stack badges** on each page section showing which component powers it
- **`/architecture/`** page — interactive diagram of the system with links to relevant source code
- **Django Debug Toolbar** enabled in dev for inspecting queries, cache, signals
- **Admin site** fully configured so viewers can browse the data layer
