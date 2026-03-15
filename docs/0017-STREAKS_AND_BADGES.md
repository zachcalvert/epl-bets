# Feature: Streaks & Badges

## Overview

A gamification layer that tracks win/loss streaks and awards badges for notable achievements. Gives users goals beyond individual bets and encourages engagement across multiple matchweeks.

## Design Decisions

- TBD

---

## Streaks

### Win Streak
- Consecutive winning bets (singles and parlays tracked separately)
- Displayed on profile and leaderboard
- Visual "fire" indicator when on a hot streak (5+)

### Loss Streak
- Tracked but displayed more subtly (empathy over shame)
- Could trigger a "bounce back" challenge

### Matchweek Streak
- Consecutive matchweeks with at least one winning bet

---

## Badges

### Achievement Badges

| Badge | Criteria | Rarity |
|-------|----------|--------|
| First Blood | Place your first bet | Common |
| Called the Upset | Win a bet on a team with odds > 4.00 | Uncommon |
| Perfect Matchweek | Win every bet placed in a single matchweek | Rare |
| Parlay King | Hit a 5+ leg parlay | Epic |
| Underdog Hunter | Win 10+ upset bets in a season | Rare |
| Streak Master | Achieve a 10+ win streak | Epic |
| High Roller | Place a max-stake bet and win | Uncommon |
| Consistency | Place at least one bet every matchweek for a month | Uncommon |
| Sharp Eye | Maintain 60%+ win rate over 50+ bets | Rare |
| Century | Place 100 bets | Common |

### Badge Display
- Badges shown on public profile in a grid
- Unearned badges shown as locked/greyed out silhouettes
- Toast notification + animation when a badge is earned
- Most recent badge shown next to username in leaderboards

---

## Models

TBD — likely:
- `Badge` — definition table (name, description, icon, criteria, rarity)
- `UserBadge` — M2M through table (user, badge, earned_at)
- Streak fields on `UserProfile` (current_win_streak, best_win_streak, etc.)

---

## Implementation Notes

- Badge checks run as part of the bet settlement Celery task
- Streak updates are atomic — increment or reset on each settlement
- Badge criteria should be defined in code (not DB) for easy auditing

---

## Open Questions

- Should badges be revocable (e.g., win rate drops below threshold)?
- Seasonal vs permanent badges?
- Should badge rarity be based on % of users who have it (dynamic) or fixed?
