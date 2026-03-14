# Phase 15: Parlay (Accumulator) Betting System

## Overview

Add a parlay system that lets users chain multiple selections across different matches into a single bet with combined odds and a larger potential payout. All legs must win for the parlay to pay out.

## Design Decisions

- **Separate models** (`Parlay` + `ParlayLeg`) rather than extending `BetSlip` — different semantics warrant different models
- **Session-based slip** — legs stored in `request.session["parlay_slip"]` until placement, avoiding premature DB writes
- **Leg limits**: min 2, max 10
- **One selection per match** — no same-match parlays
- **Void handling**: voided legs are removed and odds recalculated on remaining legs; if all legs void, refund stake
- **Incremental settlement**: each leg settles when its match finishes; parlay resolves when all legs are settled or any leg loses
- **Max payout cap**: 50,000 credits
- **Max stake**: 1,000 credits (same as single bets)

---

## Models (`betting/models.py`)

### `Parlay`

| Field | Type | Notes |
|-------|------|-------|
| user | FK → User | CASCADE, related_name="parlays" |
| stake | Decimal(10,2) | 0.50–1000.00 |
| combined_odds | Decimal(12,2) | Product of all leg odds, recalculated on void |
| status | CharField | PENDING / WON / LOST / VOID |
| payout | Decimal(12,2) | Nullable, set on settlement |
| max_payout | Decimal(12,2) | Default 50,000, locked at placement |

Inherits `id_hash`, `created_at`, `updated_at` from `BaseModel`.

### `ParlayLeg`

| Field | Type | Notes |
|-------|------|-------|
| parlay | FK → Parlay | CASCADE, related_name="legs" |
| match | FK → Match | CASCADE, related_name="parlay_legs" |
| selection | CharField | HOME_WIN / DRAW / AWAY_WIN |
| odds_at_placement | Decimal(6,2) | Frozen at placement |
| status | CharField | PENDING / WON / LOST / VOID |

Constraint: `unique_together = [("parlay", "match")]`

---

## UI Flow

### Building the Slip

1. Each odds value on the odds board gets a small "+" button
2. Clicking "+" sends `hx-post` to `AddToParlayView` with `match_id` + `selection`
3. Server adds to session, returns updated floating slip panel via OOB swap
4. Slip panel (bottom-right on desktop, bottom sheet on mobile) shows:
   - List of legs with match, selection, individual odds, remove button
   - Combined odds
   - Stake input + potential payout preview
   - "Place Parlay" button

### Placing

1. User enters stake, clicks "Place Parlay"
2. `hx-post` to `PlaceParlayView`
3. Server validates all matches still accept bets, looks up best odds, creates records atomically
4. Returns confirmation partial + balance OOB update
5. Session slip cleared

---

## Settlement Logic (`betting/tasks.py`)

Extend `settle_match_bets` to also settle parlay legs for the match:

1. **Settle legs**: Find `ParlayLeg` records for the match with `status=PENDING`. Set to WON/LOST/VOID based on match result.
2. **Evaluate parlays**: For each affected parlay, check all leg statuses:
   - Any LOST → parlay LOST, payout = 0
   - Any PENDING → parlay stays PENDING (recalc odds if voids exist)
   - All VOID → parlay VOID, refund stake
   - All settled, no losses → parlay WON, payout = min(stake × combined_odds, max_payout)

---

## Views (`betting/views.py`)

| View | Method | URL | Purpose |
|------|--------|-----|---------|
| `AddToParlayView` | POST | `parlay/add/` | Add leg to session slip |
| `RemoveFromParlayView` | POST | `parlay/remove/` | Remove leg from session slip |
| `ClearParlayView` | POST | `parlay/clear/` | Clear session slip |
| `ParlaySlipPartialView` | GET | `parlay/slip/` | Get current slip panel |
| `PlaceParlayView` | POST | `parlay/place/` | Validate + create parlay atomically |

Modify: `MyBetsView` (include parlays in activity feed + aggregates), `BailoutView` (check pending parlays).

---

## Templates

**New:**
- `betting/partials/parlay_slip.html` — floating betslip panel
- `betting/partials/parlay_leg_item.html` — single leg row
- `betting/partials/parlay_confirmation.html` — placement success

**Modified:**
- `betting/partials/odds_board_body.html` — add "+" buttons next to odds
- `betting/my_bets.html` — add parlay entries (expandable cards showing all legs)
- `website/base.html` — include parlay slip panel for authenticated users

---

## Integration Points

- **Rewards**: Fire reward check on `Parlay` creation (extract reward logic into helper, call from view)
- **Bankruptcy/Bailout**: Check `Parlay.objects.filter(status=PENDING)` in addition to `BetSlip`
- **Leaderboard**: No changes needed (driven by `UserBalance`)
- **Transparency**: Record `parlay_placed` and `parlay_settled` events
- **Admin**: Register `Parlay` with `ParlayLeg` inline

---

## Implementation Phases

### Phase A: Models & Migration
- Add `Parlay` + `ParlayLeg` to `betting/models.py`
- Generate migration
- Register in admin with inline

### Phase B: Session Slip & Views
- Add slip management views (add/remove/clear/get)
- Add URL routes
- Add `PlaceParlayForm` (stake-only)

### Phase C: Placement
- Build `PlaceParlayView` with atomic creation
- Odds lookup + combined odds calculation

### Phase D: Templates
- Create slip panel, leg item, confirmation partials
- Add "+" buttons to odds board
- Include slip panel in base template

### Phase E: Settlement
- Add `settle_parlay_legs()` + `evaluate_parlay()` to tasks
- Extend `settle_match_bets` to call parlay settlement

### Phase F: Integration
- Update My Bets page with parlay entries
- Update bailout check
- Add rewards integration
- Add transparency events

### Phase G: Tests
- Model tests (creation, constraints, odds calc)
- View tests (session slip CRUD, placement validation)
- Settlement tests (all win, any loss, void legs, all void, partial pending)
- Add `ParlayFactory` + `ParlayLegFactory`

---

## Key Files

| File | Action |
|------|--------|
| `betting/models.py` | Add `Parlay`, `ParlayLeg` |
| `betting/forms.py` | Add `PlaceParlayForm` |
| `betting/views.py` | Add 5 new views, modify `MyBetsView` + `BailoutView` |
| `betting/urls.py` | Add 5 new routes |
| `betting/tasks.py` | Add parlay settlement logic |
| `betting/admin.py` | Register with inline |
| `betting/templates/betting/partials/` | 3 new templates |
| `betting/templates/betting/my_bets.html` | Add parlay entries |
| `betting/templates/betting/partials/odds_board_body.html` | Add "+" buttons |
| `website/templates/website/base.html` | Include slip panel |
| `rewards/signals.py` | Extract helper for reuse |
| `betting/tests/` | 3 new test files + factory updates |

---

## Verification

1. Run migrations: `docker compose run --rm web python manage.py migrate`
2. Add legs to slip from odds board, verify session state
3. Place a parlay, verify DB records + balance deduction
4. Settle matches via admin, verify leg-by-leg settlement + parlay resolution
5. Test void scenario: cancel a match mid-parlay, verify odds recalculation
6. Check My Bets page shows parlays with expandable leg details
7. Run full test suite: `docker compose run --rm web pytest`
