# Feature: Leaderboards

## Overview

Weekly, monthly, and season-long rankings that let users compete on profit, win rate, and streak length. Public profiles surface each user's betting stats and history.

## Design Decisions

- TBD

---

## Leaderboard Types

### Profit Leaderboard
- Net profit (winnings minus stakes) over a given time window
- Windows: **This Week**, **This Month**, **All-Time (Season)**
- Ties broken by fewer total bets (rewarding efficiency)

### Win Rate Leaderboard
- Minimum bet threshold to qualify (e.g., 10+ bets in the period)
- Percentage of winning bets out of settled bets
- Separate tracks for singles vs parlays

### Streak Leaderboard
- Longest active win streak
- All-time best streak record
- "Hot streak" badge for 5+ consecutive wins

---

## Public Profiles

Each user gets a `/profile/<username>/` page showing:
- Overall record (W/L), win rate, net profit
- Current streak
- Badges earned
- Recent bet history (last 20 settled bets)
- Favorite team to bet on (most bets placed)
- Best single win (highest payout)

---

## Models

TBD — likely a `LeaderboardSnapshot` model for caching periodic rankings, plus profile stats fields on the User model or a `UserProfile` model.

---

## UI / Pages

- `/leaderboard/` — main leaderboard page with tab switcher (profit / win rate / streak) and time window toggle
- `/profile/<username>/` — public profile page
- Leaderboard widget on dashboard sidebar showing top 5 + current user's rank

---

## Real-Time

- Leaderboard updates after each bet settlement via Celery task
- Dashboard widget refreshes via HTMX polling or WebSocket

---

## Open Questions

- Should leaderboards be opt-in or opt-out?
- How to handle users who game the system (e.g., many tiny bets)?
- Minimum bet count threshold per time window?
