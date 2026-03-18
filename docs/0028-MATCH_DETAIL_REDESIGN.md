# Phase 28: Match Detail Page Redesign

## Overview

A layout and content overhaul of the match detail page, focused on improving the desktop experience and surfacing the discussion thread as a first-class feature. The changes prune informational clutter from the pre-match panel, add contextual standing data to the match header, and restructure the page into a purposeful two-column grid.

---

## Design Decisions

### Two-column desktop layout

The page now uses a `grid-cols-[26rem_minmax(0,1fr)]` layout on `lg+` screens:

- **Left column (26rem, sticky):** Bet form only. The bet form doesn't need horizontal space — it's three pick buttons, a stake input, and a submit button. Keeping it narrow and sticky means it's always reachable without scrolling.
- **Right column (flexible):** Status card (Match Preview / Match Centre / Match Recap) stacked above the discussion thread. Both benefit from width: the form guide needs room for badge rows, and discussion comments read better in a wider column.

On mobile, columns collapse to a single stack: bet form first (the primary action), then status card, then discussion.

### Discussion thread in the main column

Previously the discussion thread shared a column with the bet form. Moving it alongside the status card was the key insight of this redesign — these two pieces of content are complementary. The Match Preview gives you the analytical context; the discussion thread is where that context gets debated. Grouping them makes the right column feel like a coherent "match narrative" space.

### Hype panel pruning

The pre-match (hype) card previously included:

- Form (Last 5) ✓ kept
- Community Sentiment ✓ kept
- Head to Head ✗ removed
- Key Stats ✗ removed

Head to Head and Key Stats were detailed but added significant vertical length to a sidebar that already had to compete with the main column for attention. With the discussion thread now a primary feature, compactness in the status card matters more. The same pruning was applied to the live and recap cards.

### League position in the match header

To compensate for removing Key Stats, each team's current league position and points total are now displayed in the match header directly under the HOME / AWAY label:

```
Bournemouth
HOME
10th · 41 pts
```

This keeps the most useful single-figure context — where each team sits in the table right now — in the most prominent location on the page, without requiring a dedicated panel.

### Form guide: single-row layout

The Form (Last 5) display was previously two vertically stacked rows. It now renders both teams on a single horizontal row: home team label + badges left-aligned, away badges + team label right-aligned, with `justify-between` providing natural spacing. This mirrors the aesthetic of the match header (home left, away right) and makes the form comparison more scannable.

---

## Layout diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     Match Header (full width)                   │
│  [Crest] Bournemouth      VS        Man United [Crest]          │
│          HOME                           AWAY                    │
│          10th · 41 pts                  3rd · 54 pts            │
│          Friday, 20 March 2026 — 13:00 · Vitality Stadium       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐  ┌───────────────────────────────────────────┐
│  Place a Bet    │  │  MATCH PREVIEW                            │
│  (26rem sticky) │  │  Form (Last 5)                            │
│                 │  │  BOU D D D D W    W L W W D MUN           │
│  Your pick      │  │  Community Sentiment                      │
│  [BOU][Draw]    │  │  ████████████░░░░░░░░░░░░░░░░░░           │
│  [Man United]   │  │  Home 20% · Draw 80% · Away 0%            │
│                 │  ├───────────────────────────────────────────┤
│  Stake (£)      │  │  Discussion (0)                           │
│  [         ]    │  │  Join the discussion...              [Send]│
│                 │  │                                           │
│  [Place Bet]    │  │  (comments...)                            │
└─────────────────┘  └───────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│ > Odds Comparison (full width, collapsed)                       │
│ > Under the Hood  (full width, collapsed)                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## Template structure

| Template | Role |
|----------|------|
| `matches/templates/matches/match_detail.html` | Main page: header, two-column grid, odds, under the hood |
| `matches/templates/matches/partials/hype_card.html` | Pre-match status card: form guide + community sentiment |
| `matches/templates/matches/partials/live_card.html` | In-play status card: sentiment + form guide |
| `matches/templates/matches/partials/recap_card.html` | Post-match status card: result context + betting outcome + sentiment vs reality + form guide |
| `matches/templates/matches/partials/_section_form_guide.html` | Shared form guide partial (single-row layout) |

Deleted:

| Template | Reason |
|----------|--------|
| `_section_h2h.html` | Pruned from all status cards |
| `_section_key_stats.html` | Pruned; key data (position/pts) moved to match header |

---

## Files changed

| File | Change |
|------|--------|
| `matches/templates/matches/match_detail.html` | Two-column grid; league position in header; discussion moved to right column |
| `matches/templates/matches/partials/_section_form_guide.html` | Single-row layout with home left / away right |
| `matches/templates/matches/partials/hype_card.html` | Removed H2H and Key Stats includes; removed `mb-6` (spacing now owned by grid) |
| `matches/templates/matches/partials/live_card.html` | Same pruning |
| `matches/templates/matches/partials/recap_card.html` | Same pruning |
| `matches/templates/matches/partials/_section_h2h.html` | Deleted |
| `matches/templates/matches/partials/_section_key_stats.html` | Deleted |
| `matches/templatetags/match_tags.py` | Added `ordinal` filter (1 → "1st", 2 → "2nd", etc.) |
| `matches/views.py` | `MatchDetailView` now fetches standings for both teams and passes to context |

---

## Principles to carry forward

These decisions reflect a broader design philosophy worth applying to future page reworks:

1. **Content earns its space.** Every panel should justify its vertical real estate. If data can be expressed in one line in a more prominent location, a dedicated section is probably not worth it.

2. **Match the column width to the content's natural width.** Forms don't need to stretch. Text and data visualisations do. A narrow sticky sidebar for forms, a wide flexible column for content, is a good default.

3. **Group content by relationship, not type.** Discussion and the match preview live in the same column not because they're the same kind of thing, but because they serve the same moment — a user forming an opinion about a match.

4. **Mirror the header's visual grammar.** Home left, away right is established in the match header. Repeating that convention in the form guide (BOU ████ ████ MUN) makes the page feel coherent without any explanation.

5. **Mobile: primary action first.** The bet form is the primary action on the page. On mobile it comes first in source order, before the status card and discussion.
