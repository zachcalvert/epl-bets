# Feature: Leaderboards

## Overview

All-time rankings that let users compete on balance, profit, win rate, and streak length. Public profiles surface each user's betting stats and history.

Time-windowed leaderboards (weekly/monthly) are deferred to a follow-up.

## Design Decisions

- **Denormalized `UserStats` model** — stats updated incrementally on bet settlement, not computed on read
- **All-time only** — time windows deferred to keep scope focused
- **Win rate minimum** — 10+ settled bets required to appear on win rate leaderboard
- **Singles + parlays combined** — no separate tracks

---

## Leaderboard Types

### Balance Leaderboard (default)
- Current credit balance, descending
- Ties broken by user ID

### Profit Leaderboard
- Net profit (total payout minus total staked) across all settled bets
- Ties broken by user ID
- Excludes users with zero settled bets

### Win Rate Leaderboard
- Percentage of winning bets out of settled bets
- Minimum 10 settled bets to qualify
- Ties broken by more total bets, then user ID

### Streak Leaderboard
- Best all-time win streak
- Ties broken by current streak, then user ID
- Excludes users with zero settled bets

---

## Public Profiles

Each user gets a `/profile/<user_pk>/` page showing:
- Display name or masked email
- Overall record (W/L), win rate, net profit
- Current balance and leaderboard rank
- Current streak + best streak
- Recent bet history (last 20 settled bets)
- Recent parlays (last 10 settled parlays)

---

## Models

### `UserStats` (in `betting/models.py`)

| Field | Type | Notes |
|-------|------|-------|
| user | OneToOne → User | CASCADE, related_name="stats" |
| total_bets | PositiveIntegerField | Settled singles + parlays |
| total_wins | PositiveIntegerField | |
| total_losses | PositiveIntegerField | |
| total_staked | Decimal(10,2) | |
| total_payout | Decimal(10,2) | |
| net_profit | Decimal(10,2) | total_payout - total_staked |
| current_streak | IntegerField | Positive = win, negative = loss |
| best_streak | PositiveIntegerField | All-time best win streak |

Win rate is a computed `@property` on the model: `total_wins / total_bets * 100`.

---

## UI / Pages

- `/leaderboard/` — main page with tab bar (Balance | Profit | Win Rate | Streaks)
- Tabs switch via HTMX `hx-get` with `?type=...` param, swapping the table partial
- `/profile/<user_pk>/` — public profile page with stats cards and bet history
- Dashboard sidebar widget — top 5 by balance + current user's rank (unchanged)

---

## Real-Time

- `UserStats` updated automatically on bet settlement via `record_bet_result()` in `betting/stats.py`
- Dashboard leaderboard widget refreshes via HTMX polling (every 30s, unchanged)

---

## Backfill

Run `python manage.py backfill_stats` to populate `UserStats` from existing bet history.

---

## Open Questions

- Should leaderboards be opt-in or opt-out?
- How to handle users who game the system (e.g., many tiny bets)?
- Time-windowed leaderboards (weekly/monthly) — future enhancement
