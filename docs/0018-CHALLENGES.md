# Feature: Daily/Weekly Challenges

## Overview

Time-limited challenges that give users specific objectives to aim for beyond regular betting. Completing challenges earns bonus virtual currency, badges, or leaderboard points.

## Design Decisions

- **Same for all users** — challenges are universal (community feel, simpler implementation)
- **Users can see upcoming challenges** — the /challenges/ page has an Upcoming tab
- **International breaks** — daily/weekly rotation tasks skip creation when no matches are scheduled; empty state shown in widget
- **New `challenges` Django app** — separate from betting/rewards for clean separation
- **Lazy enrollment** — UserChallenge rows created on first page visit or bet action, not upfront
- **Three models**: ChallengeTemplate (reusable blueprint), Challenge (time-bound instance), UserChallenge (per-user progress)

---

## Challenge Types

### Daily Challenges
- Rotated at 5 AM UTC daily (3 active at a time)
- Lighter objectives, quick to attempt
- 10 templates in rotation, avoiding last 7 days' repeats
- Examples:
  - "Quick Three" — Place 3 bets today (25 credits)
  - "Underdog Believer" — Bet on an underdog with odds > 3.00 (35 credits)
  - "Long Shot" — Bet with odds > 5.00 (50 credits)

### Weekly Challenges (Matchweek Challenges)
- Rotated Friday 4 AM UTC (2 active at a time)
- Tied to current EPL matchday, end next Tuesday 5 AM UTC
- 6 templates in rotation, avoiding last 21 days' repeats
- Examples:
  - "Matchweek Maven" — Bet on every match this matchweek (200 credits)
  - "Streak Chaser" — Win 4 bets in a row (250 credits)
  - "Sharp Shooter" — Correctly predict 5+ outcomes (200 credits)

### Special Event Challenges
- Activated manually via admin (templates with `challenge_type=SPECIAL`)
- Higher rewards + optional badge
- Examples:
  - Derby day predictions (500 credits + badge)
  - Big Six parlay (400 credits + badge)

---

## Rewards

| Challenge Type | Reward |
|---------------|--------|
| Daily | 25–50 bonus credits |
| Weekly | 150–250 bonus credits |
| Special Event | 250–500 credits + exclusive badge |

Credits added atomically to UserBalance on completion.

---

## Models

### ChallengeTemplate
Reusable blueprint, seeded via `seed_challenge_templates` management command.
- `slug` (unique), `title`, `description`, `icon` (emoji)
- `challenge_type` (DAILY/WEEKLY/SPECIAL)
- `criteria_type` + `criteria_params` (JSON)
- `reward_amount`, optional `badge` FK, `is_active`

### Challenge
Time-bound instance of a template (same for all users).
- `template` FK, `status` (UPCOMING/ACTIVE/EXPIRED)
- `starts_at`, `ends_at`, optional `matchday`

### UserChallenge
Per-user progress tracking.
- `user`, `challenge` (unique together)
- `progress`, `target` (denormalized), `status` (IN_PROGRESS/COMPLETED/FAILED)
- `completed_at`, `reward_credited` (prevents double-crediting)

---

## Criteria Types

| Type | Fires On | Params | Logic |
|------|----------|--------|-------|
| BET_COUNT | bet/parlay placed | `target` | +1 per bet |
| BET_ON_UNDERDOG | bet placed | `target`, `odds_min` | +1 if odds >= threshold |
| WIN_COUNT | bet/parlay settled | `target` | +1 if won |
| WIN_STREAK | bet/parlay settled | `target` | +1 if won, reset to 0 on loss |
| PARLAY_PLACED | parlay placed | `target`, `min_legs` | +1 if legs >= min |
| PARLAY_WON | parlay settled | `target` | +1 if won |
| TOTAL_STAKED | bet/parlay placed | `target` | progress = sum of stakes in window |
| BET_ALL_MATCHES | bet placed | `target` (match count) | progress = distinct matches bet on |
| CORRECT_PREDICTIONS | bet settled | `target` | +1 if won |

---

## UI

- **Dashboard widget** — sidebar panel showing up to 3 active challenges with progress bars, refreshes every 30s
- **`/challenges/` page** — three HTMX tabs: Active, Completed, Upcoming
- **Progress bars** — visual completion with percentage
- **Celebration toast** — confetti animation on completion (via WebSocket OOB swap), same pattern as reward/badge toasts
- **Navbar link** — "Challenges" link (desktop + mobile, authenticated only)

---

## Integration Points

1. **Bet placement** (`betting/views.py`) — `transaction.on_commit` calls `update_challenge_progress(user, "bet_placed", ctx)`
2. **Parlay placement** (`betting/views.py`) — same with `"parlay_placed"`
3. **Bet settlement** (`betting/stats.py`) — `transaction.on_commit` calls with `"bet_settled"` or `"parlay_settled"`
4. **WebSocket** (`rewards/consumers.py`) — `challenge_notification` handler pushes toast + balance OOB update
5. **Dashboard** (`matches/views.py`) — challenge context added to `DashboardView`

---

## Celery Beat Tasks

| Task | Schedule | Logic |
|------|----------|-------|
| `rotate_daily_challenges` | crontab(hour=5) | Expire old dailies, create 3 new (skip if no matches) |
| `rotate_weekly_challenges` | crontab(hour=4, friday) | Expire old weeklies, create 2 new tied to matchday |
| `expire_challenges` | every 15 min | Catch-all: expire overdue ACTIVE challenges |

---

## Key Files

- `challenges/models.py` — ChallengeTemplate, Challenge, UserChallenge
- `challenges/engine.py` — Evaluator dispatch, progress updates, reward crediting
- `challenges/tasks.py` — Celery rotation and expiration tasks
- `challenges/views.py` — Page, partial, and widget views
- `challenges/challenge_definitions.py` — Seed data (16 templates)
- `challenges/admin.py` — Admin registration
