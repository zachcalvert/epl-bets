# Phase 23: Match Status Cards (Live + Recap)

## Overview

Status-specific cards on the match detail page for IN_PLAY/PAUSED and FINISHED matches, complementing the existing hype card (Phase 20) which only renders for SCHEDULED/TIMED matches. No new models or external API calls — all data comes from existing `MatchStats`, `Standing`, and `BetSlip` models.

## Design Decisions

- **Three separate partials** — `hype_card.html`, `live_card.html`, `recap_card.html` — each controls its own header, section order, and unique sections. Shared sections extracted into four `_section_*.html` sub-partials for DRY reuse.
- **Dynamic include** — view sets `status_card_template` context variable; `match_detail.html` uses `{% include status_card_template %}` instead of hardcoded partial paths.
- **MatchStats fetched for all card states** — `fetch_match_hype_data(match)` now runs for IN_PLAY, PAUSED, and FINISHED too. The function handles staleness and errors gracefully.
- **Recap-only sections** — result context (headline + upset detection), betting outcome (aggregate stats), sentiment vs reality (pre-match prediction vs actual result).

---

## Card Designs

### Hype Card (SCHEDULED / TIMED) — existing, unchanged
- Header: "MATCH PREVIEW" in accent
- Sections: Form Guide → H2H → Key Stats → Sentiment

### Live Match Card (IN_PLAY / PAUSED) — new
- Header: "MATCH CENTRE" with pulsing green dot (IN_PLAY) or HT badge (PAUSED)
- Accent border (`border-accent/30`) for live feel
- Sections reordered for live context: Sentiment → Key Stats → Form Guide → H2H

### Match Recap Card (FINISHED) — new
- Header: "MATCH RECAP" in white
- Unique sections:
  1. **Result Context** — one-liner headline ("Arsenal beat Chelsea (2-1)") with upset badge if applicable
  2. **Betting Outcome** — total bets, % who got it right, credits won
  3. **Sentiment vs Reality** — pre-match sentiment bar with actual result overlay and "Community got it right/wrong" callout
- Shared sections: Key Stats → Form Guide → H2H

---

## Sub-Partials

Extracted from `hype_card.html` into reusable includes:

| Sub-partial | Context needed |
|---|---|
| `_section_form_guide.html` | `match`, `match_stats` |
| `_section_h2h.html` | `match`, `match_stats` |
| `_section_key_stats.html` | `match`, `home_standing`, `away_standing` |
| `_section_sentiment.html` | `sentiment` |

Each includes its own `{% if %}` guard, so parent cards can include any subset without empty dividers.

---

## View Changes

### `_get_recap_context(match, home_standing, away_standing)`

New helper in `matches/views.py` that computes:

- **`result_context`** — headline string and `is_upset` flag (winner's league position worse than loser's)
- **`betting_outcome`** — aggregate BetSlip query: total bets, winners count, win %, total payout
- **`actual_result`** — `"HOME_WIN"`, `"DRAW"`, or `"AWAY_WIN"`
- **`actual_result_label`** — display label for template comparison with `sentiment.most_popular`

### `MatchDetailView.get_context_data()`

- Status check expanded from `(SCHEDULED, TIMED)` to include `(IN_PLAY, PAUSED, FINISHED)`
- Sets `status_card_template` to the correct partial path
- Calls `_get_recap_context()` only for FINISHED matches

---

## Files Changed

| File | Change |
|---|---|
| `matches/views.py` | Expand status check, add `_get_recap_context()`, set `status_card_template` |
| `matches/templates/matches/match_detail.html` | Dynamic `{% include status_card_template %}` |
| `matches/templates/matches/partials/hype_card.html` | Refactored to use sub-partial includes |
| `matches/templates/matches/partials/live_card.html` | New |
| `matches/templates/matches/partials/recap_card.html` | New |
| `matches/templates/matches/partials/_section_form_guide.html` | New (extracted) |
| `matches/templates/matches/partials/_section_h2h.html` | New (extracted) |
| `matches/templates/matches/partials/_section_key_stats.html` | New (extracted) |
| `matches/templates/matches/partials/_section_sentiment.html` | New (extracted) |
| `matches/tests/test_views.py` | Tests for live and finished card rendering |
| `docs/0023-MATCH_STATUS_CARDS.md` | This document |