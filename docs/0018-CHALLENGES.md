# Feature: Daily/Weekly Challenges

## Overview

Time-limited challenges that give users specific objectives to aim for beyond regular betting. Completing challenges earns bonus virtual currency, badges, or leaderboard points.

## Design Decisions

- TBD

---

## Challenge Types

### Daily Challenges
- Refresh every 24 hours (or at first kickoff of the day)
- Lighter objectives, quick to attempt
- Examples:
  - "Place a bet on today's featured match"
  - "Bet on an underdog (odds > 3.00)"
  - "Place 3 bets today"

### Weekly Challenges (Matchweek Challenges)
- Tied to each EPL matchweek (runs Fri–Mon typically)
- More ambitious, require sustained engagement
- Examples:
  - "Bet on 3 different underdogs this matchweek"
  - "Correctly predict 5+ match outcomes"
  - "Place a parlay with 3+ legs"
  - "Win 4 bets in a row"
  - "Bet on every match in the matchweek"

### Special Event Challenges
- Derby days, cup weekends, final matchday
- Higher rewards, unique badges
- Examples:
  - "Correctly predict the result of the North London Derby"
  - "Build a parlay using only Big Six matches"

---

## Rewards

| Challenge Type | Reward |
|---------------|--------|
| Daily | 25–50 bonus credits |
| Weekly | 100–250 bonus credits |
| Special Event | 250–500 credits + exclusive badge |

---

## Models

TBD — likely:
- `Challenge` — definition (title, description, type, criteria_json, reward_amount, start/end dates)
- `UserChallenge` — tracking (user, challenge, progress, status, completed_at)

---

## UI

- Challenge widget on dashboard (today's daily + active weekly)
- Progress bars showing completion status
- `/challenges/` page with active, upcoming, and completed challenges
- Celebration animation on completion

---

## Challenge Engine

- Criteria stored as structured JSON (e.g., `{"type": "bet_count", "min": 3, "odds_min": 3.0}`)
- Progress updated on bet placement and/or settlement depending on criteria
- Celery beat task to rotate daily/weekly challenges
- Challenge templates seeded from a curated list, rotated to avoid repetition

---

## Open Questions

- Should challenges be the same for all users or personalized?
- Can users see upcoming challenges before they start?
- How to handle challenges during international breaks (no EPL matches)?
