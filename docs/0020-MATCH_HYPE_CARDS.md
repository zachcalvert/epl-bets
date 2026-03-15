# Feature: Match Hype Cards

## Overview

Pre-match cards that build excitement by surfacing form, head-to-head records, key stats, and community betting sentiment. Shown on match detail pages and as shareable preview cards.

## Design Decisions

- TBD

---

## Card Content

### Form Guide
- Last 5 results for each team (W/D/L indicators)
- Points per game over last 5
- Goals scored/conceded trend

### Head-to-Head Record
- Last 5 meetings between the two teams
- Scores, dates, and venue
- Overall H2H record (wins/draws/losses for each side)

### Key Stats
- League position and points
- Goals scored/conceded this season
- Home/away form specifically
- Clean sheets, BTTS (both teams to score) rate

### Community Sentiment
- Pie/bar chart showing % of users betting Home / Draw / Away
- Total number of bets placed on this match
- "Most popular bet" callout
- Average odds users are getting

---

## Data Sources

- **Form / H2H / Stats**: football-data.org API (matches endpoint with filters)
- **Community sentiment**: Aggregated from internal `BetSlip` data

---

## UI

- Card component on match detail page (above odds table)
- Compact version on fixture list (expandable)
- Shareable format (og:image-style rendering for social sharing — stretch goal)

### Layout
```
+--------------------------------------------------+
|  [Team A Logo]  vs  [Team B Logo]                |
|  Sat 15 Mar · 15:00 · Emirates Stadium           |
+--------------------------------------------------+
|  FORM (Last 5)                                   |
|  Arsenal:  W W D W L  │  Chelsea:  L W W D W    |
+--------------------------------------------------+
|  HEAD TO HEAD (Last 5 meetings)                  |
|  Arsenal 3 wins · 1 draw · Chelsea 1 win         |
+--------------------------------------------------+
|  COMMUNITY SENTIMENT        234 bets placed      |
|  [====Home 52%====][=Draw 18%=][==Away 30%==]    |
+--------------------------------------------------+
```

---

## Models

TBD — may not need new models if stats are fetched/cached from API. Possibly:
- `MatchStats` — cached stats snapshot (h2h_json, form_json, fetched_at)
- Community sentiment is computed on-the-fly from existing `BetSlip` model

---

## Implementation Notes

- H2H and form data fetched on first match detail view, cached for 24 hours
- Community sentiment is live (computed from BetSlip aggregation query)
- Progressive enhancement: card renders with available data, sections hidden if data missing

---

## Open Questions

- How far back should H2H go (last 5? last 10? all-time)?
- Should sentiment be visible before or only after placing a bet (to avoid herding)?
- Include expected lineups if available from API?
