# Launch Plan

Prepare the codebase for public release as a transparent, portfolio-quality open source project.

---

## Phase 7: Community & Testing

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
- Run full suite with coverage: `pytest --cov --cov-report=xml`
- Verify coverage > 90%
- Fill gaps if needed

---

## Phase 8: CI/CD

### 8A — GitHub Actions
- `.github/workflows/ci.yml`:
  - Trigger: push to main, pull requests
  - Services: PostgreSQL, Redis
  - Steps: install deps, ruff lint, pytest with coverage, upload to Codecov
- Add Codecov badge to README

---

## Phase 9: Deploy & Publish

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

## Checklist

- [ ] CODE_OF_CONDUCT.md
- [ ] CONTRIBUTING.md
- [ ] LICENSE
- [ ] pytest scaffold + shared fixtures
- [ ] codecov.yml
- [ ] Tests: users
- [ ] Tests: matches
- [ ] Tests: betting
- [ ] Tests: website
- [ ] Coverage > 90%
- [ ] GitHub Actions CI workflow
- [ ] Codecov badge in README
- [ ] fly.io deployment
- [ ] Live demo link in README
- [ ] Public GitHub repo created and pushed
