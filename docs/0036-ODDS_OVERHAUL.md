# Odds System Overhaul: Replace External API with Generated Odds

## Summary

Replace The Odds API (paid, external) with an algorithmic odds generator that produces
a single "house line" per match based on league standings, form, and home advantage.
The football-data.org API (free tier) is kept for standings, fixtures, and scores.

---

## Design: The Odds Algorithm

The generator lives in `betting/odds_engine.py` — a pure-logic module with no side effects.

### Inputs (per match)

| Input | Source | Purpose |
|-------|--------|---------|
| `home_position` / `away_position` | `Standing` model | Table strength |
| `home_points` / `away_points` | `Standing` model | Points-per-game proxy |
| `home_played` / `away_played` | `Standing` model | Normalize PPG |
| `home_gd` / `away_gd` | `Standing` model | Goal difference signal |
| `home_won` / `home_drawn` / `home_lost` | `Standing` model | Win rate signal |
| `away_won` / `away_drawn` / `away_lost` | `Standing` model | Win rate signal |

### Algorithm Steps

1. **Points-per-game (PPG)** — `ppg = points / max(played, 1)`. Normalizes for teams
   with fewer games played.

2. **Strength rating** — Blend of PPG (weighted 60%) and position-based rating (40%).
   Position rating: `(21 - position) / 20` gives a 0.05–1.0 scale.

3. **Home advantage factor** — Apply a flat multiplier (~1.25) to the home team's
   strength rating. This is well-established in EPL data (~46% home wins historically).

4. **Raw probabilities** — Convert strength ratings to win/draw/away probabilities:
   - `p_home = home_strength / (home_strength + away_strength)`
   - `p_away = away_strength / (home_strength + away_strength)`
   - Extract draw probability from the gap: closer teams → higher draw chance.
     Use a draw baseline (~27%, EPL average) scaled by how close the teams are.
   - Redistribute: `p_home = p_home * (1 - p_draw)`, `p_away = p_away * (1 - p_draw)`

5. **Convert to decimal odds** — `odds = 1 / probability`

6. **Apply margin (overround)** — Real bookmakers build in a ~5-8% margin.
   We apply a ~5% margin so the house has a slight edge (realistic feel):
   `adjusted_odds = raw_odds * (1 / (1 + margin))`

7. **Clamp & round** — Floor at 1.05, cap at 25.00, round to 2 decimal places.

### Example Output

| Match | Home | Draw | Away |
|-------|------|------|------|
| Arsenal (2nd) vs Ipswich (19th) | 1.28 | 5.80 | 11.50 |
| Wolves (16th) vs Man City (4th) | 4.20 | 3.60 | 1.82 |
| Everton (14th) vs Fulham (12th) | 2.45 | 3.25 | 3.10 |

---

## Implementation Steps

### Step 1: Create `betting/odds_engine.py`

New module with two public functions:

```python
def generate_match_odds(home_standing, away_standing) -> dict:
    """Return {"home_win": Decimal, "draw": Decimal, "away_win": Decimal}."""

def generate_all_upcoming_odds(season: str) -> list[dict]:
    """Generate odds for all SCHEDULED/TIMED matches. Returns list of
    {"match": Match, "home_win": Decimal, "draw": Decimal, "away_win": Decimal}."""
```

Pure functions, easy to unit test. No DB writes — just computation.

### Step 2: Create `betting/tasks.py` — Replace `fetch_odds` task

Replace the `fetch_odds` Celery task body:

```python
@shared_task(bind=True, max_retries=3)
def generate_odds(self):
    """Generate house odds for all upcoming matches based on current standings."""
    from betting.odds_engine import generate_all_upcoming_odds
    results = generate_all_upcoming_odds(settings.CURRENT_SEASON)
    created = updated = 0
    now = timezone.now()
    for r in results:
        _, was_created = Odds.objects.update_or_create(
            match=r["match"],
            bookmaker="House",
            defaults={
                "home_win": r["home_win"],
                "draw": r["draw"],
                "away_win": r["away_win"],
                "fetched_at": now,
            },
        )
        if was_created:
            created += 1
        else:
            updated += 1
    # ... activity event, logging
```

- The `bookmaker` field is set to `"House"` for all records.
- The `Odds` model itself is unchanged — no migration needed.
- The `fetched_at` field still tracks freshness (now means "generated at").

### Step 3: Update Celery Beat schedule

Replace:
```python
"fetch-odds-4x-thu-mon": {
    "task": "betting.tasks.fetch_odds",
    "schedule": crontab(hour="6,12,17,22", minute=0, day_of_week="thu,fri,sat,sun,mon"),
},
```

With:
```python
"generate-odds-10m": {
    "task": "betting.tasks.generate_odds",
    "schedule": timedelta(minutes=10),
},
```

Runs every 10 minutes. Since odds generation is pure local computation (no external API),
the overhead is negligible. The task skips unchanged lines via a bulk upsert pattern,
so DB writes are minimal when standings haven't changed.

### Step 4: Remove external API code

Delete from `betting/services.py`:
- `TEAM_NAME_ALIASES` dict
- `OddsApiClient` class
- `sync_odds()` function
- `_build_team_lookup()`, `_resolve_team()`, `_normalize_name()` helpers

Delete from `config/settings.py`:
- `ODDS_API_KEY` setting

Delete from `.env` / `.env.example`:
- `ODDS_API_KEY` variable

### Step 5: Update views — simplify "best odds" logic

Since there's now only one bookmaker ("House"), the `Min()` aggregation across
bookmakers is technically unnecessary but still correct. We can simplify:

**`OddsBoardView`** — The `Min()` aggregation still works with a single bookmaker,
so no functional change needed. Optionally simplify to direct field access.

**`PlaceBetView`** / **`QuickBetFormView`** / **`PlaceParlayView`** — Same: `Min()`
on a single record returns the value directly. No change required.

### Step 6: Update templates — remove multi-bookmaker UI

**`matches/partials/odds_table_body.html`** — Currently shows a comparison table
with bookmaker column and "N bookmakers tracked" count. Replace with a simpler
single-line display or remove the comparison section entirely. Just show the
house line directly on the match detail page (it already shows "best odds" prominently).

**`betting/partials/odds_row.html`** — Can be deleted or simplified (no longer
iterating multiple bookmakers).

**`odds_board_body.html`** — Update "Market freshness" / "bookmaker prices" copy
to say "Odds generated" instead of "Odds synced". Remove "N bookmakers tracked".

### Step 7: Clean up management command (if applicable)

Check if `seed_epl` or any management command calls `sync_odds()` — if so, replace
with `generate_odds` or the engine function directly.

### Step 8: Update tests

- **Delete:** `test_odds_api_client_*`, `test_sync_odds_*` tests in `test_services.py`
- **Add:** Tests for `odds_engine.py`:
  - Top team at home vs bottom team → home odds < 1.50, away odds > 8.00
  - Even teams → odds close to each other, draw ~3.2-3.5
  - Home advantage visible (same teams swap home/away → home line tightens)
  - Edge cases: teams with 0 games played, identical standings
  - Margin/overround: sum of implied probabilities > 100%
- **Update:** `test_fetch_odds_*` → `test_generate_odds_*` in `test_tasks.py`
- **Keep:** All settlement tests unchanged (they use `odds_at_placement` snapshot)

### Step 9: Data migration — clean up existing odds

Write a one-time data migration or management command to:
- Delete all existing `Odds` records (they reference real bookmakers)
- Run the generator to create fresh "House" odds for all upcoming matches

---

## What Doesn't Change

| Component | Why |
|-----------|-----|
| `Odds` model | Same fields — `bookmaker` just becomes `"House"` |
| `BetSlip` model | `odds_at_placement` snapshot is independent of source |
| Settlement logic | Uses `odds_at_placement`, doesn't care where odds came from |
| Parlay system | Same odds lookup pattern (`Min()` on single record = same value) |
| Bot strategies | They read from `Odds` model, same interface |
| Activity events | Still fire on odds generation |
| HTMX polling | Still works (30s refresh of odds board partial) |
| `football-data.org` API | Kept for standings, fixtures, scores |

---

## Files Modified

| File | Action |
|------|--------|
| `betting/odds_engine.py` | **NEW** — algorithm module |
| `betting/services.py` | Delete `OddsApiClient`, `sync_odds`, aliases |
| `betting/tasks.py` | Replace `fetch_odds` → `generate_odds` |
| `config/settings.py` | Update Beat schedule, remove `ODDS_API_KEY` |
| `matches/partials/odds_table_body.html` | Simplify (remove bookmaker comparison) |
| `betting/partials/odds_row.html` | Delete or simplify |
| `betting/partials/odds_board_body.html` | Update copy ("generated" vs "synced") |
| `betting/tests/test_services.py` | Remove API client tests |
| `betting/tests/test_odds_engine.py` | **NEW** — algorithm tests |
| `betting/tests/test_tasks.py` | Update fetch_odds → generate_odds |
| `.env.example` | Remove `ODDS_API_KEY` |
