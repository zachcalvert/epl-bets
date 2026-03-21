# NBA Bets — New Project Plan

> A Django/HTMX/Channels betting simulation for the NBA, heavily inspired by the
> architecture of `epl-bets`. This document is written for an implementing agent
> that has no prior context on the EPL project.

---

## 0. Guiding Principles

- **Test coverage is a first-class priority.** Every phase ships with tests. Target 90%+ from the start. Use pytest, factory-boy, respx, and InMemoryChannelLayer.
- **Users and bots coexist from day one.** The User model has an `is_bot` flag. Bot profiles and strategies are seeded early so the site feels alive immediately.
- **Bots have editable personas.** Each bot has a `persona_prompt` field (admin-editable) and a `strategy_type` that governs automated betting behavior. Comments are generated via the Anthropic Claude API.
- **External APIs are spiked first.** The implementing agent should research and evaluate NBA data and odds providers before writing integration code. Candidates are listed below but not locked in.
- **Style/design is not carried over.** Build a clean, functional UI with Tailwind CDN. No need to replicate the EPL site's visual identity.

---

## 1. Tech Stack (Locked)

| Layer | Choice | Notes |
|-------|--------|-------|
| Framework | Django 5.x | ASGI via Daphne |
| Templates | Django templates + HTMX | Partials pattern for dynamic updates |
| WebSockets | Django Channels + channels-redis | Real-time scores, toasts, notifications |
| Task queue | Celery + Redis broker | django-celery-beat for periodic tasks |
| Database | PostgreSQL 16 | |
| Cache/broker | Redis 7 | Shared: cache, Celery broker, Channels layer |
| HTTP client | httpx | For external API calls |
| LLM | Anthropic Claude API | Bot comment generation |
| Containerization | Docker Compose | Services: web, db, redis, worker, beat |
| Testing | pytest + pytest-django + factory-boy + respx + pytest-cov | |
| Linting | ruff | E/F/I rules, Python 3.11 target |
| Deps | Poetry | pyproject.toml |

---

## 2. External API Research (Agent Must Spike)

Before writing any integration code, the implementing agent should research and
evaluate these candidates. The goal is to identify:

1. **An NBA data API** — teams, schedule, live scores, standings, player stats
2. **An odds API** — NBA moneyline, spread, and over/under odds from multiple bookmakers

### NBA Data API Candidates

| Provider | Notes |
|----------|-------|
| [balldontlie.io](https://balldontlie.io) | Free tier, covers teams/games/stats. Check rate limits and live score support. |
| [sportsdata.io](https://sportsdata.io) | Paid, comprehensive. Has live scores, odds, player props. |
| [api-sports.io](https://api-sports.io) (API-Basketball) | Part of API-Sports family. Covers NBA with live scores. |
| [ESPN hidden API](https://site.api.espn.com) | Unofficial, no auth, fragile. Good for prototyping. |

### Odds API Candidates

| Provider | Notes |
|----------|-------|
| [The Odds API](https://the-odds-api.com) | Same provider used in epl-bets. Covers NBA. Likely the best choice for consistency. |
| sportsdata.io | Bundled with their data API if using their paid tier. |

### What to Evaluate

For each candidate:
- Free tier limits (requests/day, data freshness)
- Live score latency (how fast do scores update?)
- Data shape: does it provide the fields we need (game status, scores, team IDs)?
- Odds coverage: moneyline, spread, over/under? How many bookmakers?
- Authentication method (API key header, query param, OAuth?)
- Rate limiting behavior (429 handling, backoff requirements)

### Deliverable

A short writeup in `docs/API-RESEARCH.md` summarizing findings and the chosen
providers, with example response shapes.

---

## 3. Django App Structure

```
nba_bets/
├── config/              # settings.py, urls.py, asgi.py, celery.py, wsgi.py
├── core/                # BaseModel (id_hash, timestamps), shared utilities
├── users/               # Custom User (email-based, is_bot, avatar, display_name)
├── games/               # Team, Game, Standing, GameStats (replaces matches/)
├── betting/             # Odds, BetSlip, Parlay, ParlayLeg, UserBalance, BalanceTransaction, UserStats, Badge
├── bots/                # BotProfile, BotComment, strategies, comment generation
├── discussions/         # Comment (threaded, per-game)
├── board/               # BoardPost (predictions, results, meta), threading
├── activity/            # ActivityEvent, WebSocket broadcast, toasts
├── rewards/             # Reward, RewardDistribution, RewardRule
├── challenges/          # ChallengeTemplate, Challenge, UserChallenge
├── website/             # Auth views, account settings, public pages, components
└── manage.py
```

---

## 4. Phased Build Plan

### Phase 1 — Foundation

**Goal:** Dockerized Django project with Channels, Celery, Redis, Postgres. Custom
User model. Core base model. Basic health check. Full test infrastructure.

- [ ] `docker-compose.yml` — services: `web` (Daphne), `db` (Postgres 16), `redis` (Redis 7), `worker` (Celery), `beat` (Celery Beat)
- [ ] `Dockerfile` — Python 3.11, Poetry, Daphne entrypoint
- [ ] `config/settings.py` — Channels config, Celery config (Redis broker, DatabaseScheduler), cache config, `AUTH_USER_MODEL = "users.User"`
- [ ] `config/asgi.py` — ProtocolTypeRouter with HTTP + WebSocket (AuthMiddlewareStack)
- [ ] `config/celery.py` — Celery app with autodiscover
- [ ] `core/models.py` — `BaseModel` (abstract: `id_hash` short identifier, `created_at`, `updated_at`)
- [ ] `users/models.py` — Custom `User` (email-based, `display_name`, `is_bot`, `currency`, avatar fields, `show_activity_toasts`), custom `UserManager`
- [ ] `conftest.py` — InMemoryChannelLayer, LocMemCache, eager Celery, MD5 hasher, respx auto-mock, test API keys
- [ ] `pyproject.toml` — all dependencies, ruff config, pytest config (90%+ coverage target)
- [ ] `.env.example` — SECRET_KEY, DATABASE_URL, REDIS_URL, API keys
- [ ] Tests: User creation, custom manager, base model behavior

### Phase 2 — NBA Data Models & API Client

**Goal:** Team, Game, Standing models. NBA data API client with sync helpers.
Seed command for teams/schedule/standings.

- [ ] **Spike external APIs first** — write `docs/API-RESEARCH.md`
- [ ] `games/models.py`:
  - `Team` — external_id, name, short_name, abbreviation, logo_url, conference (EAST/WEST), division
  - `Game` — external_id, home_team, away_team, home_score, away_score, status (SCHEDULED/IN_PROGRESS/FINAL/POSTPONED/CANCELLED), game_date, tip_off, season, arena
  - `Standing` — team, season, conference, wins, losses, win_pct, games_behind, streak, home_record, away_record, conference_rank
  - `GameStats` — game (OneToOne), pre-game context JSON fields (H2H, form, injuries), fetched_at
- [ ] `games/services.py` — NBA data API client class:
  - `get_teams(season)` → normalized team dicts
  - `get_games(season, date_from=None, date_to=None)` → normalized game dicts
  - `get_standings(season)` → standings by conference
  - `get_live_scores()` → in-progress games
  - Sync helpers: `sync_teams()`, `sync_games()`, `sync_standings()` using `update_or_create()`
- [ ] `games/tasks.py` — Celery tasks: `fetch_teams`, `fetch_schedule`, `fetch_standings`, `fetch_live_scores`
- [ ] Seed command: `python manage.py seed_nba [--offline]`
- [ ] Static data fixtures for offline dev (`games/static_data/`)
- [ ] Tests: model creation, API client (mocked with respx), sync idempotency, tasks

### Phase 3 — Odds & Betting Models

**Goal:** Odds model (moneyline, spread, over/under). Odds API client. BetSlip,
Parlay, UserBalance, BalanceTransaction ledger. Bet placement flow.

- [ ] `betting/models.py`:
  - `Odds` — game FK, bookmaker, home_moneyline, away_moneyline, spread_line, spread_home, spread_away, total_line, over_odds, under_odds, fetched_at
  - `BetSlip` — user, game, market (MONEYLINE/SPREAD/TOTAL), selection (HOME/AWAY/OVER/UNDER), line (for spread/total), odds_at_placement, stake, status (PENDING/WON/LOST/VOID), payout
  - `Parlay` — user, stake, combined_odds, status, payout, max_payout
  - `ParlayLeg` — parlay FK, game FK, market, selection, line, odds_at_placement, status
  - `UserBalance` — user (OneToOne), balance (default 1000)
  - `BalanceTransaction` — user FK, amount (signed), balance_after, transaction_type, description
  - `UserStats` — total_bets, wins, losses, staked, payout, net_profit, streak tracking
  - `Badge`, `UserBadge` — achievement system
- [ ] `betting/balance.py` — `log_transaction()` with atomic balance update + snapshot
- [ ] `betting/services.py` — Odds API client (likely The Odds API covering NBA), `sync_odds()`, team name alias mapping
- [ ] `betting/tasks.py` — `fetch_odds` periodic task
- [ ] Tests: balance ledger atomicity, bet placement, odds sync, transaction types

### Phase 4 — Bet Settlement

**Goal:** Automated bet settlement when games finish. Parlay evaluation logic.
Bankruptcy/bailout system.

- [ ] `betting/settlement.py`:
  - `settle_game_bets(game_pk)` — determine winners per market:
    - Moneyline: home/away based on final score
    - Spread: apply line to final score
    - Total: over/under based on combined score vs line
  - `settle_parlay_legs()` — settle individual legs, evaluate full parlay
  - `_evaluate_parlay()` — any LOST → parlay LOST, all WON → payout, mix of WON+VOID → recalc
- [ ] `betting/models.py` additions — `Bankruptcy`, `Bailout` models
- [ ] Signal or task trigger: when `Game.status` changes to FINAL, fire `settle_game_bets.delay(game_pk)`
- [ ] `UserStats` update on settlement via `record_bet_result()`
- [ ] Tests: all settlement paths (win, loss, void, spread edge cases, parlay combos, bankruptcy flow)

### Phase 5 — Bot System

**Goal:** Bot profiles with strategies and AI-generated comments. Bots place bets
and participate in discussions.

- [ ] `bots/models.py`:
  - `BotProfile` — user (OneToOne), strategy_type, persona_prompt (admin-editable), favorite_team (for homer), avatar fields, is_active
  - `BotComment` — user, game, comment FK, trigger_type (PRE_GAME/POST_BET/POST_GAME/REPLY), prompt_used, raw_response, filtered, error
  - Unique constraint: (user, game, trigger_type)
- [ ] Strategy types (adapt for NBA):
  - `FRONTRUNNER` — bets favorites (low moneyline odds)
  - `UNDERDOG` — bets underdogs (high moneyline odds)
  - `SPREAD_SHARK` — focuses on spread bets, looks for value
  - `PARLAY` — multi-leg parlays
  - `TOTAL_GURU` — over/under specialist
  - `CHAOS_AGENT` — random picks, aggressive stakes
  - `ALL_IN_ALICE` — max stakes, YOLO
  - `HOMER` — always bets their team
- [ ] `bots/strategies.py` — base `BotStrategy` class with `pick_bets()` and `pick_parlays()`; subclass per type
- [ ] `bots/comment_service.py` — builds prompts from persona_prompt + game context, calls Claude API, filters output
- [ ] `bots/tasks.py`:
  - `run_bot_strategies()` — dispatches bots with staggered delays
  - `execute_bot_strategy(bot_user_id)` — runs strategy, places bets
  - `generate_pregame_comments()`, `generate_postgame_comments()` — LLM generation tasks
  - `generate_bot_reply_task()` — reply to other comments (capped per game)
- [ ] Seed command: `python manage.py seed_bots` — creates bot users + profiles with persona prompts
- [ ] Tests: strategy logic (mocked odds data), comment generation (mocked LLM), dedup, filtering

### Phase 6 — Core Pages & HTMX

**Goal:** All primary views with HTMX-powered interactivity.

- [ ] **Dashboard** — today's games, live scores, recent results
- [ ] **Schedule** — upcoming games by date, filterable by team/conference
- [ ] **Standings** — conference standings (East/West), division breakdowns
- [ ] **Game Detail** — scores, odds comparison, bet form, discussion thread
- [ ] **Odds Board** — all available odds across games, auto-refreshing
- [ ] **My Bets** — pending, settled, parlays, stats
- [ ] **Account** — settings, balance history chart, display name, avatar
- [ ] **Public Profile** — stats, recent bets, badges, comment history
- [ ] **Auth** — signup (creates UserBalance with 1000 credits), login, logout
- [ ] HTMX conventions:
  - Partials in `<app>/templates/<app>/partials/`
  - Reusable components in `website/templates/website/components/`
  - OOB swaps for multi-target updates (balance + form reset + toast)
  - `hx-indicator` with `.spinner` class for loading states
- [ ] Tests: all views (GET/POST), template rendering, auth guards, HTMX partial responses

### Phase 7 — WebSockets & Real-Time

**Goal:** Live score updates, activity toasts, per-user notifications.

- [ ] `games/consumers.py` — `LiveUpdatesConsumer`:
  - Scope "dashboard" → joins `live_scores` group
  - Scope "<game_pk>" → joins `game_<pk>` group
  - Handlers: `score_update`, `game_score_update` → render partials, send as OOB swap
- [ ] `activity/models.py` — `ActivityEvent` (bot_bet, bot_comment, score_change, odds_update, bet_settlement)
- [ ] `activity/consumers.py` — `ActivityConsumer` (all visitors, no auth required, "site_activity" group)
- [ ] `rewards/consumers.py` — `NotificationConsumer` (per-user group, badge/challenge/reward toasts)
- [ ] `config/asgi.py` routing: merge all consumer URL patterns
- [ ] `activity/tasks.py` — `broadcast_next_activity_event` (runs every ~20s), cleanup task
- [ ] Tests: consumer connect/disconnect, group membership, event rendering, activity broadcast

### Phase 8 — Board, Challenges, Rewards

**Goal:** Community message board, daily/weekly challenges, milestone rewards.

- [ ] `board/models.py` — `BoardPost` (post_type: RESULTS/PREDICTION/META, threading, moderation)
- [ ] `challenges/models.py` — `ChallengeTemplate`, `Challenge` (daily/weekly instances), `UserChallenge` (progress)
- [ ] `rewards/models.py` — `Reward`, `RewardDistribution`, `RewardRule`
- [ ] Board views: post list (filterable by type), detail with replies, create, moderate (superuser)
- [ ] Bot auto-posting: Celery tasks for bot board posts (predictions, reactions)
- [ ] Challenge rotation: daily + weekly Celery tasks
- [ ] Reward distribution on milestone completion
- [ ] Tests: board CRUD, moderation, challenge progress, reward triggers

### Phase 9 — Celery Beat Schedule

**Goal:** Configure all periodic tasks for NBA's schedule rhythm.

NBA games are played almost daily Oct–June, with most tip-offs 7–10:30 PM ET.
Playoffs run Apr–June with fewer but higher-stakes games.

```python
CELERY_BEAT_SCHEDULE = {
    # Teams change rarely — monthly sync
    "fetch-teams-monthly": ("games.tasks.fetch_teams", crontab(day_of_month=1, hour=3, minute=0)),

    # Schedule — daily (trades, postponements)
    "fetch-schedule-daily": ("games.tasks.fetch_schedule", crontab(hour=6, minute=0)),

    # Standings — twice daily during season
    "fetch-standings-morning": ("games.tasks.fetch_standings", crontab(hour=8, minute=0)),
    "fetch-standings-postgame": ("games.tasks.fetch_standings", crontab(hour=2, minute=0)),

    # Live scores — every 2 min during game windows (7pm–1am ET / 0–6 UTC)
    "fetch-live-scores": ("games.tasks.fetch_live_scores", crontab(minute="*/2", hour="0-6,23")),

    # Odds — 6x daily
    "fetch-odds": ("betting.tasks.fetch_odds", crontab(hour="6,10,14,17,19,22", minute=0)),

    # Bot strategies — daily during season
    "run-bot-strategies": ("bots.tasks.run_bot_strategies", crontab(hour=14, minute=0)),

    # Bot comments — pregame afternoon, postgame late night
    "generate-pregame-comments": ("bots.tasks.generate_pregame_comments", crontab(hour="14,16,18", minute=0)),
    "generate-postgame-comments": ("bots.tasks.generate_postgame_comments", crontab(hour="0,1,2,3", minute="0,30")),

    # Activity broadcast
    "broadcast-activity": ("activity.tasks.broadcast_next_activity_event", 20.0),
    "cleanup-activity": ("activity.tasks.cleanup_old_activity_events", crontab(hour=5, minute=0)),
}
```

*(These are starting points — tune based on actual API rate limits and game schedules.)*

### Phase 10 — Polish & Launch Prep

- [ ] Error handling: 404/500 pages, API failure graceful degradation
- [ ] Mobile responsiveness (Tailwind utilities)
- [ ] How It Works page
- [ ] README with setup instructions
- [ ] `seed_all` management command (teams → schedule → standings → bots → challenges → badges)
- [ ] CI: GitHub Actions (ruff + pytest + coverage)
- [ ] Deploy: fly.io (or similar)

---

## 5. NBA-Specific Domain Notes

### Key Differences from EPL

| Concept | EPL | NBA |
|---------|-----|-----|
| League structure | 20 teams, single table | 30 teams, 2 conferences, 6 divisions |
| Season length | 38 matchdays (Aug–May) | 82 games (Oct–Apr) + playoffs (Apr–Jun) |
| Game frequency | 2-3 days/week, mostly weekends | Nearly daily, heaviest Tue-Sat |
| Draw possibility | Yes (significant bet market) | No (OT until winner) |
| Primary bet markets | 1X2 (home/draw/away) | Moneyline, spread, over/under |
| Standings | Points (W=3, D=1, L=0) | Win%, conference seeding, games behind |
| Postseason | None (relegation instead) | Playoffs: 8 per conference, best-of-7 series |

### Bet Markets

- **Moneyline** — pick the winner (no draw)
- **Spread** — team must win by more than N points (or lose by fewer)
- **Over/Under (Total)** — combined score vs. a set line
- *(Future: player props, live/in-game bets — out of scope for v1)*

### Game Statuses

```python
class GameStatus(models.TextChoices):
    SCHEDULED = "SCHEDULED"
    IN_PROGRESS = "IN_PROGRESS"
    HALFTIME = "HALFTIME"
    FINAL = "FINAL"
    POSTPONED = "POSTPONED"
    CANCELLED = "CANCELLED"
```

---

## 6. Bot Personas (Starter Set)

| Name | Strategy | Persona |
|------|----------|---------|
| **Chalk Charlie** | FRONTRUNNER | Only bets favorites. Quotes win percentages. Insufferably smug when right. |
| **Longshot Lou** | UNDERDOG | Lives for the upset. Talks about "value" constantly. Celebrates like it's the finals. |
| **Spread Steve** | SPREAD_SHARK | All about the spread. Tracks ATS records obsessively. Dry, analytical tone. |
| **Parlay Pete** | PARLAY | 4-5 leg parlays every night. Eternal optimist. One leg always busts. |
| **Over Ollie** | TOTAL_GURU | Believes every game is going over. Loves high-scoring affairs. |
| **Chaos Cathy** | CHAOS_AGENT | Random picks, random stakes. Chaotic energy. Sometimes accidentally genius. |
| **YOLO Yolanda** | ALL_IN_ALICE | Max bets, no hedging. Rides the highs and lows dramatically. |
| **Homer Hank** | HOMER | Ride-or-die for one team. Delusional optimism. Blames refs on losses. |

Each bot gets an admin-editable `persona_prompt` that feeds into the Claude API
system prompt for comment generation.

---

## 7. Seed Data & Dev Workflow

```bash
# Start everything
docker compose up -d

# Run migrations
docker compose run --rm web python manage.py migrate

# Seed (offline mode for dev without API keys)
docker compose run --rm web python manage.py seed_all --offline

# Run tests
docker compose run --rm web pytest --cov -x

# Lint
docker compose run --rm web ruff check .
```

---

## 8. Out of Scope (v1)

- Player props and in-game/live betting
- Playoff bracket predictions
- Trade deadline speculation features
- Fantasy basketball integration
- Mobile app (web-only, responsive)
- Multi-language support
- Real money (play money only, always)
