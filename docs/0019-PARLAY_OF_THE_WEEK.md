# Feature: Parlay of the Week

## Overview

A weekly featured high-risk parlay that any user can opt into with a fixed stake. The community tracks how many users joined and how many hit. Creates a shared social betting experience around a curated long-shot.

## Design Decisions

- TBD

---

## How It Works

1. **Curation** — Each matchweek, a featured parlay is generated (auto or admin-curated) with 4–6 legs
2. **Opt-in** — Users join with a fixed stake (e.g., 50 credits) — one click, no customization
3. **Tracking** — A dedicated card shows the parlay legs, combined odds, number of participants, and live status as matches play out
4. **Settlement** — All participants win or lose together; results announced with community stats

---

## Parlay Selection Criteria

- 4–6 legs across different matches
- Combined odds in the 15.00–50.00 range (exciting but not impossible)
- Mix of "safe" and "spicy" picks to create tension
- At least one upset pick to keep it interesting

### Generation Options
- **Auto-generated**: Algorithm picks legs based on odds ranges and diversity rules
- **Admin-curated**: Manual selection via Django admin (preferred for quality)
- **Hybrid**: Auto-suggest, admin approves/tweaks

---

## Community Features

- Total participants count
- Live tracker showing which legs have hit/missed as matches complete
- "X users still alive" counter as legs settle
- Post-matchweek recap: "12 of 340 users hit the Parlay of the Week!"
- Historical hit rate across all weeks

---

## Models

TBD — likely:
- `FeaturedParlay` — the weekly parlay definition (matchweek, legs, combined_odds, stake_amount, status)
- `FeaturedParlayLeg` — individual legs (match, selection, odds)
- `FeaturedParlayEntry` — user opt-ins (user, featured_parlay, status, payout)

---

## UI

- Prominent card on dashboard during active matchweek
- `/parlay-of-the-week/` detail page with leg breakdown, participant count, live status
- History page showing past weeks' parlays and hit rates
- "Join" button with confirmation modal showing potential payout

---

## Open Questions

- Fixed stake amount or user-selectable within a range?
- Should there be a "Parlay of the Week" leaderboard (most weeks joined, most hits)?
- Allow users to copy the POTW legs into their own custom parlay with different stakes?
- One per matchweek, or occasionally multiple (e.g., Saturday-only vs full matchweek)?
