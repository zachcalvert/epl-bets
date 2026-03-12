# Launch Plan

Prepare the codebase for public release as a transparent, portfolio-quality open source project.

---

## Phase 7: Community & Testing
Status: Complete
Outcome: community files shipped, pytest scaffold added, full app test suite in place, 95% enforced repo-wide coverage gate with 97.52% current coverage

### 7A — Community Files
- `CODE_OF_CONDUCT.md` — Contributor Covenant
- `CONTRIBUTING.md` — How to set up locally, run tests, submit PRs
- `LICENSE` — MIT

### 7B — Test Scaffold
- Install pytest, pytest-django, pytest-cov, pytest-xdist, factory-boy
- Configure `pyproject.toml` with pytest settings and coverage config
- Create `conftest.py` at project root with shared DB fixtures (teams, matches, standings, odds, users with balances)
- Add `codecov.yml` with coverage floor (target: 90%)

### 7C — Tests: users app
- Custom user model creation (email-based, no username)
- User authentication (email + password)
- UserBalance auto-creation on signup

### 7D — Tests: matches app
- Models: Match, Team, Standing (creation, relationships, constraints)
- Services: football-data.org API client (mocked HTTP responses)
- Tasks: fetch_fixtures, fetch_standings, fetch_live_scores (mocked API, DB assertions)
- Views: Dashboard, Fixtures, LeagueTable, MatchDetail (status codes, context, HTMX partials)
- Consumers: WebSocket connection, group messaging (if feasible with test tooling)
- Template tags: status_badge, score_display, format_odds

### 7E — Tests: betting app
- Models: Odds, BetSlip (status transitions, selection choices), UserBalance (balance operations)
- Services: The Odds API client (mocked HTTP)
- Tasks: fetch_odds, settle_bets (mocked data, balance assertions, payout calculations)
- Views: OddsBoard, PlaceBet, MyBets, QuickBetForm (auth required, form validation, insufficient balance, HTMX responses)
- Forms: PlaceBetForm (decimal validation, min/max stake)

### 7F — Tests: website app
- Auth views: signup, login, logout (redirects, form errors, balance creation)
- HowItWorksView: renders page, context has components and flows
- ComponentDetailView: valid component returns 200, invalid returns 404, HTMX partial response
- Template rendering: navbar active states, footer links

### 7G — Coverage Gate
- Run full suite with coverage: `pytest --cov --cov-report=term-missing`
- Verify repo-wide coverage stays at or above 95%
- Keep extending tests where uncovered code reflects real product risk, not percentage chasing

---

## Phase 8: CI/CD
Status: Complete

### 8A — GitHub Actions
- `.github/workflows/ci.yml`:
  - Trigger: push to main, pull requests
  - Services: PostgreSQL, Redis
  - Steps: install deps, ruff lint, full pytest suite with coverage gate, upload to Codecov when configured
- Add CI and Codecov badges to README

---

## Phase 9: Deploy & Publish
Status: Complete

Outcome: live Fly deployment at `eplbets.net`, README updated with production links, and public GitHub repo connected to automated deploys

### 9A — Deploy to fly.io
- `fly.toml` configuration
- Fly Postgres + Fly Redis provisioning
- Environment secrets (API keys, Django secret key, allowed hosts)
- Run migrations + seed data on deploy
- Verify all pages work in production

### 9B — Update README with live demo link
- Add live URL to README header
- Add screenshot(s) if desired

### 9C — Create GitHub repo and push
- Create public repo: `gh repo create zachcalvert/epl-bets --public`
- Push all history
- Verify README renders, badges work, demo link is live

---

## Phase 10: Production Hardening & Observability
Status: Planned

### 10A — Operational Visibility
- Structured application logging for web, worker, beat, and websocket paths
- Error reporting integration for server errors and failed background jobs
- Health endpoints/checks for web and worker processes
- Admin-facing operational notes for common production issues
- Runbook for safe Fly maintenance commands and production recovery

### 10B — Runtime Guardrails
- Production settings audit for security, caching, cookie, and host configuration
- Basic rate limiting / abuse protection on auth and bet placement surfaces
- Safer startup/deploy handling for migrations and seed behavior
- Data retention rules for odds snapshots, stale matches, and task artifacts
- Documented baseline memory sizing for Fly `app`, `worker`, and `beat` process groups

### 10C — Performance & Resilience
- Query review on high-traffic pages (`dashboard`, `odds board`, `match detail`, `my bets`)
- Cache strategy for standings, fixtures, and computed betting summaries
- Fallback UI and retry behavior when upstream APIs are unavailable
- Production smoke-check checklist for deploy verification
- Post-deploy memory/headroom validation after migrations and seed workflows

---

## Phase 11: Homepage Leaderboard
Status: Complete

### Goal
- Add a live leaderboard to the homepage that showcases the top ten user balances
- Refresh the section every 30 seconds via backend-driven HTMX polling

### 11A — Leaderboard Data + Ranking
- [x] Query `UserBalance` records ordered by highest balance
- [x] Limit to ten entries with deterministic tie-breaking
- [x] Mask public email display on leaderboard entries

### 11B — Homepage Integration
- [x] Add the leaderboard to the root dashboard page without displacing live match content
- [x] Include rank, user label, balance, and a clear empty state
- [x] Show a signed-in "your rank" callout on the homepage when the user is outside the top ten
- [x] Link the homepage rank callout to a rank summary section in `My Bets`

### 11C — HTMX Refresh + Tests
- [x] Serve the leaderboard through a reusable partial and polling endpoint
- [x] Refresh every 30 seconds from the backend
- [x] Add tests for render, ordering, limits, partial responses, masking, and rank states

---

## Checklist

- [x] CODE_OF_CONDUCT.md
- [x] CONTRIBUTING.md
- [x] LICENSE
- [x] pytest scaffold + shared fixtures
- [x] codecov.yml
- [x] Tests: users
- [x] Tests: matches
- [x] Tests: betting
- [x] Tests: website
- [x] Coverage >= 98% on covered slice
- [x] Full-source coverage target met
- [x] GitHub Actions CI workflow
- [x] Codecov badge in README
- [x] fly.io deployment
- [x] Live demo link in README
- [x] Public GitHub repo created and pushed

## Phase 8 Planning Notes

Phase 8 still has a few open implementation decisions:

1. Should CI run inside Docker for parity, or install Poetry dependencies directly in GitHub Actions for speed?
2. When should CI switch from the current covered slice to full-source coverage enforcement?
3. Should Codecov upload be required from day one, or added after the public GitHub repo exists?
4. Do we want one workflow (`ci.yml`) or separate workflows for lint and test feedback?

## Phase 10 Planning Notes

Phase 10 should answer a few operational questions before implementation:

1. Which error-reporting tool fits the portfolio goal best without adding too much maintenance overhead?
2. How much production telemetry should be visible only to maintainers versus exposed as part of the portfolio story?
3. Do we want production-safe seed behavior on deploy, or should seeding remain a one-time manual/bootstrap step?
4. Which pages deserve caching first based on real-world traffic and query cost?
5. What should the minimum safe Fly memory be for each process group now that interactive management commands have already triggered an OOM in production?

## Phase 12: Transparency & Portfolio Depth
Status: Complete

- Shipped the first Under the Hood rollout across Dashboard, Match Detail, and Odds Board
- Added real event plumbing for HTMX, websocket, Celery, and betting lifecycle activity
- Left deeper architecture storytelling and demo-insight expansion as optional future follow-on work

## Phase 12 Planning Notes

Phase 12 is now documented in its shipped form in `docs/0012-PHASE_12.md`:

1. Dashboard, Match Detail, and Odds Board now have page-scoped Under the Hood panels
2. The panels are backed by real short-lived events from HTMX, websocket, Celery, and betting flows
3. The initial rollout is complete without introducing a SPA-style frontend layer
4. Further architecture storytelling and insight surfaces can be planned separately if desired
