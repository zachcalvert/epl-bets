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
Status: In Progress

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
- [ ] Codecov badge in README
- [ ] fly.io deployment
- [ ] Live demo link in README
- [ ] Public GitHub repo created and pushed

## Phase 8 Planning Notes

Phase 8 still has a few open implementation decisions:

1. Should CI run inside Docker for parity, or install Poetry dependencies directly in GitHub Actions for speed?
2. When should CI switch from the current covered slice to full-source coverage enforcement?
3. Should Codecov upload be required from day one, or added after the public GitHub repo exists?
4. Do we want one workflow (`ci.yml`) or separate workflows for lint and test feedback?
