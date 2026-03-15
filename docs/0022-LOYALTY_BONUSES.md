# Feature: Loyalty Bonuses

## Overview

Small balance top-ups rewarding consistent engagement — consecutive daily logins, bet volume milestones, and sustained activity. Keeps users coming back and softens losing streaks.

## Design Decisions

- TBD

---

## Bonus Types

### Daily Login Streak
- Reward for consecutive days of visiting the site
- Escalating rewards encourage longer streaks

| Streak Length | Daily Bonus |
|--------------|-------------|
| 1–2 days | 10 credits |
| 3–6 days | 25 credits |
| 7–13 days | 50 credits |
| 14–29 days | 75 credits |
| 30+ days | 100 credits |

- Streak resets after 1 missed day
- Grace period: streak preserved if user logs in within 36 hours (allows for timezone flexibility)

### Bet Volume Milestones
- One-time bonuses for cumulative bets placed

| Milestone | Bonus |
|-----------|-------|
| 10 bets placed | 50 credits |
| 50 bets placed | 200 credits |
| 100 bets placed | 500 credits |
| 250 bets placed | 1,000 credits |
| 500 bets placed | 2,500 credits |

### Weekly Activity Bonus
- Place at least one bet every day of a matchweek → bonus
- Reward: 100 credits
- Encourages daily engagement around match schedules

### Comeback Bonus
- If a user hasn't visited in 7+ days, welcome them back with a small bonus (50 credits)
- Only triggers once per 30-day period to prevent abuse

---

## Anti-Abuse

- Minimum stake requirement for bets to count toward milestones (e.g., 10+ credits)
- Login streak requires actual site visit (page load), not just session existence
- Daily bonus claimed once per calendar day (UTC)
- Rate limiting on bonus claims

---

## Models

TBD — likely:
- `LoyaltyTracker` — per-user state (login_streak, last_login_date, total_bets_placed, last_comeback_bonus)
- `BonusClaim` — audit log (user, bonus_type, amount, claimed_at)

---

## UI

- Daily bonus toast/modal on first visit each day ("Day 7 streak! +50 credits")
- Streak counter in the navbar or user dropdown
- Milestone progress bar on profile page
- Bonus history section on profile

---

## Implementation Notes

- Login streak checked/updated via Django middleware on authenticated requests
- Milestone checks run after bet placement (in the bet creation view or signal)
- All bonus credits added via the existing balance management system
- Celery beat task for streak expiry checks (mark broken streaks for users who missed a day)

---

## Open Questions

- Should there be a max daily bonus cap?
- Matchweek-aligned bonuses or pure calendar days?
- Should bonuses count toward leaderboard profit calculations? (Probably not)
- Display upcoming milestone to motivate ("7 more bets until your next bonus!")?
