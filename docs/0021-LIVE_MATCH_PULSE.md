# Feature: Live Match Pulse

## Overview

A real-time win probability visualization that shifts during live matches based on goals, cards, and time elapsed. Makes watching matches more intense even without cash-out functionality.

## Design Decisions

- TBD

---

## Core Concept

A dynamic probability bar/chart on the match detail page that shows each team's estimated chance of winning (and draw probability) updating in real-time as match events occur.

```
[===== Arsenal 62% =====][= Draw 18% =][== Chelsea 20% ==]
```

After a Chelsea goal:
```
[=== Arsenal 35% ===][= Draw 22% =][===== Chelsea 43% =====]
```

---

## Probability Model

### Input Signals
- **Pre-match odds** — baseline probabilities derived from bookmaker odds
- **Current score** — biggest factor in live probability
- **Time elapsed** — a 1-0 lead at 85' is very different from 1-0 at 15'
- **Red cards** — significant probability shift
- **Home/away** — slight modifier

### Calculation Approach
- Start with implied probabilities from pre-match odds
- Adjust using a simplified model based on:
  - Goal difference × time remaining weight
  - Red card modifier (team down a man loses ~15% win probability)
  - Historical base rates for comebacks from given scorelines at given minutes
- No need for a sophisticated model — directionally correct is enough for engagement

### Fallback
- If no live data available, show pre-match probabilities as static display

---

## UI Components

### Probability Bar
- Horizontal stacked bar (Home / Draw / Away) with percentages
- Smooth CSS transitions on probability changes
- Color-coded by team colors

### Event Timeline
- Vertical timeline of match events (goals, cards, subs)
- Each event shows the probability shift it caused
- "Momentum swings" highlighted

### Pulse Graph (Stretch Goal)
- Line chart showing win probability over time (x-axis: 0'–90')
- Similar to ESPN's win probability graphs
- Updates in real-time via WebSocket

---

## Data Flow

1. Match events received via existing WebSocket consumer
2. Backend recalculates probabilities on each event
3. Updated probabilities pushed to connected clients
4. HTMX swaps update the probability bar and timeline

---

## Models

TBD — likely lightweight:
- `MatchProbability` — cached current state (match, home_prob, draw_prob, away_prob, updated_at)
- Or simply computed on-the-fly and pushed via WebSocket without persistence

---

## Implementation Notes

- Probability calculation as a pure Python utility function (easy to test)
- Historical comeback rates can be a simple lookup table (no ML needed)
- WebSocket updates piggyback on existing match update consumer
- Graceful degradation: if live data stops, freeze at last known state

---

## Open Questions

- Should users see how their bet is doing relative to the probability shifts?
- Include xG (expected goals) if available from API?
- Show probability shifts for substitutions or just goals/cards?
- How to handle extra time / penalties?
