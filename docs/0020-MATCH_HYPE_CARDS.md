# Phase 20: Match Hype Cards

## Overview

Pre-match cards that build excitement by surfacing form, head-to-head records, key stats, and community betting sentiment. Rendered on the match detail page (above the odds table) for `SCHEDULED` and `TIMED` matches.

## Design Decisions

- **`MatchStats` model for caching** — H2H and form data fetched from football-data.org and cached for 24 hours; community sentiment is computed live from `BetSlip` on every request (cheap aggregation, always fresh)
- **Pre-match only** — hype card renders when `match.status` is `SCHEDULED` or `TIMED`; once a match is in-play or finished the card is hidden (no longer relevant)
- **H2H capped at last 5 meetings** — enough narrative context without cluttering the UI
- **Form = last 5 finished matches per team** — fetched via separate team-filtered API calls and stored in `home_form_json` / `away_form_json`
- **Sentiment visible to all users** — this is a demo/social feature; hiding it until after bet placement adds friction without meaningful benefit in a fake-money context
- **No shareable OG image** — social sharing card is a stretch goal, deferred
- **Graceful degradation** — card renders with whatever data is available; individual sections are hidden if data is missing (e.g., API rate-limited on first load)
- **Celery pre-warm task** — a periodic task pre-fetches hype data for matches kicking off in the next 48 hours so match detail pages feel instant

---

## Card Content

### Form Guide
- Last 5 finished matches for each team (W/D/L from that team's perspective)
- Displayed as colored badge pills: green W, amber D, red L (left = most recent)

### Head-to-Head Record
- Last 5 meetings between the two teams (date, score)
- Aggregate summary: "Arsenal 3 wins · 1 draw · Chelsea 1 win"

### Key Stats
- League position and points (sourced from existing `Standing` model — no extra API call)
- Goals scored / conceded this season
- Home record (for home team) and away record (for away team) from Standing

### Community Sentiment
- Horizontal bar showing % of bets on Home / Draw / Away
- Total bets placed on this match
- "Most popular bet" callout label
- Only rendered when at least 1 bet exists for the match; otherwise hidden entirely

---

## Data Sources

| Section | Source | Freshness |
|---------|--------|-----------|
| Form (last 5) | football-data.org `/v4/matches?team={id}&status=FINISHED` | Cached 24h in `MatchStats` |
| H2H (last 5) | football-data.org `/v4/matches/{match_id}/head2head?limit=5` | Cached 24h in `MatchStats` |
| Key stats (position, goals) | `Standing` model | Already kept current by `sync_standings` Celery task |
| Community sentiment | `BetSlip` aggregation query | Live on every request |

---

## Models

### `MatchStats` (add to `matches/models.py`)

| Field | Type | Notes |
|-------|------|-------|
| match | OneToOneField → Match | CASCADE, related_name="hype_stats" |
| h2h_json | JSONField | List of last 5 H2H match dicts (date, home, away, score) |
| h2h_summary_json | JSONField | Aggregated wins/draws/losses from each side's perspective |
| home_form_json | JSONField | List of last 5 result dicts for home team |
| away_form_json | JSONField | List of last 5 result dicts for away team |
| fetched_at | DateTimeField | null=True; used to determine staleness |

Result dict shape (same structure for H2H entries and form entries):
```python
{
    "date": "2025-01-11",
    "home_team": "Arsenal",
    "away_team": "Chelsea",
    "home_score": 2,
    "away_score": 1,
}
```
Form entries additionally include a `"result"` key (`"W"`, `"D"`, or `"L"` from the team's perspective).

`MatchStats.is_stale()` — returns `True` if `fetched_at` is null or older than 24 hours.

---

## New Service Function

Add `fetch_match_hype_data(match)` to `matches/services.py`:

1. Check `MatchStats.is_stale()` — return cached data if fresh
2. Call football-data.org for H2H: `GET /v4/matches/{match.external_id}/head2head?limit=5`
3. Call football-data.org for home team form: `GET /v4/matches?team={home_team.external_id}&status=FINISHED&limit=5`
4. Call football-data.org for away team form: `GET /v4/matches?team={away_team.external_id}&status=FINISHED&limit=5`
5. Normalize and upsert `MatchStats`; set `fetched_at = now()`
6. Return the `MatchStats` instance (caller gets it whether from cache or fresh fetch)
7. On any API error: log warning, return existing (possibly stale) `MatchStats` or `None` — never raise to the view

---

## New Celery Task

Add `prefetch_upcoming_hype_data` to `matches/tasks.py`:

- Runs every 6 hours via Celery Beat
- Finds all `SCHEDULED`/`TIMED` matches with kickoff within the next 48 hours
- Calls `fetch_match_hype_data(match)` for each (skips if data is already fresh)
- Spreads calls with a short sleep between teams to respect the 10 req/min rate limit

Register in `CELERY_BEAT_SCHEDULE` in settings.

---

## View Changes

### `MatchDetailView` (in `matches/views.py`)

Add to `get_context_data()`:
1. Only run for pre-match statuses — skip entirely if `match.status` is not `SCHEDULED` or `TIMED`
2. Call `fetch_match_hype_data(match)` → `match_stats`
3. Compute community sentiment:
   ```python
   from django.db.models import Count
   sentiment = (
       BetSlip.objects
       .filter(match=match)
       .values("selection")
       .annotate(count=Count("id"))
   )
   ```
4. Compute percentages and "most popular" label from sentiment queryset
5. Fetch home and away `Standing` objects for key stats (filter by current season)
6. Pass `match_stats`, `sentiment_data`, `home_standing`, `away_standing` to context

---

## UI / Templates

### New partial: `matches/templates/matches/partials/hype_card.html`

A self-contained include rendered in `match_detail.html` above the odds table:

```
{% include "matches/partials/hype_card.html" with match=match match_stats=match_stats ... %}
```

Card layout:
```
+--------------------------------------------------+
|  MATCH PREVIEW                                   |
+--------------------------------------------------+
|  FORM (Last 5)                                   |
|  Arsenal:  [W][W][D][W][L]  10 pts  GF 9 GA 4   |
|  Chelsea:  [L][W][W][D][W]   8 pts  GF 7 GA 6   |
+--------------------------------------------------+
|  HEAD TO HEAD (Last 5 meetings)                  |
|  Arsenal 3 wins · 1 draw · Chelsea 1 win         |
|  ----------------------------------------        |
|  12 Jan 2025  Arsenal 2–1 Chelsea                |
|  05 Nov 2024  Chelsea 0–0 Arsenal                |
|  ...                                             |
+--------------------------------------------------+
|  KEY STATS                                       |
|  Arsenal  1st · 52 pts  |  Chelsea  4th · 41 pts |
|  Home: W8 D2 L2         |  Away: W5 D3 L4        |
|  GF 45  GA 22           |  GF 38  GA 30          |
+--------------------------------------------------+
|  COMMUNITY SENTIMENT        234 bets placed      |
|  [====Home 52%====][=Draw 18%=][==Away 30%==]    |
|  Most popular: Home Win                          |
+--------------------------------------------------+
```

Sections are individually wrapped in `{% if %}` guards:
- Form section: only if `match_stats` and `match_stats.home_form_json`
- H2H section: only if `match_stats` and `match_stats.h2h_json`
- Key stats: only if `home_standing` or `away_standing`
- Sentiment: only if `sentiment_data.total > 0`

### Changes to `match_detail.html`

- Add `{% if match.status == "SCHEDULED" or match.status == "TIMED" %}...{% endif %}` block above the odds table
- Include `hype_card.html` partial inside that block

---

## Migration

```
python manage.py makemigrations matches --name add_match_stats
python manage.py migrate
```

---

## Implementation Steps

1. **Model** — Add `MatchStats` to `matches/models.py`; run migration
2. **Service** — Add `fetch_match_hype_data(match)` to `matches/services.py` (API calls, cache upsert, error handling)
3. **Celery task** — Add `prefetch_upcoming_hype_data` to `matches/tasks.py`; register in Beat schedule
4. **View** — Update `MatchDetailView.get_context_data()` to fetch hype data and sentiment; pass to template
5. **Partial template** — Create `matches/templates/matches/partials/hype_card.html` with all four sections and guards
6. **Match detail** — Include hype card partial in `match_detail.html`
7. **Admin** — Register `MatchStats` in `matches/admin.py` with `fetched_at` and JSON field display

---

## Open Questions

- **H2H depth**: Last 5 meetings is the plan; expose a "show more" toggle? (Probably over-engineered — defer.)
- **Rate limit budget**: 3 API calls per match × N matches pre-warmed. At 10 req/min free tier, limit pre-warm to matches within 24h (not 48h) if rate pressure becomes an issue.
- **Sentiment herding**: Showing community sentiment before a user bets could influence their pick. Acceptable for a demo app, but worth noting.
- **Expected lineups**: football-data.org lineups are only available after announcement (~1h before kickoff). Could add a fifth "Lineups" section as a follow-up when data is present.
