# Phase 24: Variable Currency Display Settings

## Overview

Replaced the hardcoded "credits" / "cr" currency label with user-configurable currency display. Users can choose between GBP, USD, and EUR from their Profile & Settings page. This is a purely visual change — all underlying values remain the same, with no exchange rate conversions.

GBP (£) is the default for all users, matching the EPL theme.

## Warning: Currency Display Changes Are Not Trivial

Currency formatting touches **every surface that displays a monetary value** — navbar, mobile nav, leaderboard (sidebar + full page), my bets, bet forms, confirmation modals, parlay slips, profile pages, challenge cards, reward toasts, bailout overlay, match recap cards, and WebSocket-pushed OOB updates.

**Before making changes to currency display:**

1. Grep for all usages of the `|currency` filter, `{% currency_symbol %}` tag, and the `format_currency()` Python helper
2. Check JavaScript files and inline scripts that format amounts — they read `data-currency-symbol` from DOM elements
3. WebSocket consumers (`rewards/consumers.py`) render templates without `request` context — they must explicitly pass `user` in the template context
4. The `payout-preview.js` script does NOT append currency — it only sets the number. The symbol comes from the template wrapping the `<span data-payout-value>` element. Don't duplicate the symbol in JS.
5. Run `python manage.py check` and visually verify all pages after any currency-related change

## Architecture

### Model

`users.models.Currency` (TextChoices): `USD`, `GBP`, `EUR`

`User.currency` — CharField, max_length=3, default=GBP

### Template Tags (`website/templatetags/currency_tags.py`)

| Tool | Usage | Example Output |
|------|-------|----------------|
| `{{ value\|currency:user }}` | Filter: formats value with user's symbol | `£1,000.00` |
| `{% currency_symbol user %}` | Tag: returns just the symbol | `£` |
| `format_currency(value, code)` | Python helper (importable) | `£1,000.00` |

Config map is a simple dict — `USD` → `$`, `GBP` → `£`, `EUR` → `€`. All currencies use a prefix symbol.

### Settings UI

- `CurrencyForm` (ModelForm) in `betting/forms.py`
- `CurrencyUpdateView` at `/account/currency/` — HTMX partial swap, same pattern as display name card
- `website/templates/website/partials/currency_settings_card.html`

### JavaScript Handling

Monetary JS lives in two places:
- `website/static/website/js/payout-preview.js` — bet form payout preview (symbol comes from template, JS only sets the number)
- Inline `<script>` in `parlay_slip.html` — reads `data-currency-symbol` from the form element
- Inline `<script>` in `bailout_overlay.html` — reads `data-currency-symbol` from the overlay element

### WebSocket Consumers

`rewards/consumers.py` renders `balance_oob.html`, `reward_toast_oob.html`, and `challenge_toast_oob.html` via `render_to_string`. These templates use the `|currency:user` filter, so the consumer must pass `{"user": user}` in the context (there is no `request` object in WS consumers).

## Files Modified

### New Files
- `website/templatetags/__init__.py`
- `website/templatetags/currency_tags.py`
- `website/templates/website/partials/currency_settings_card.html`
- `users/migrations/0003_alter_user_options_user_currency.py`

### Models & Forms
- `users/models.py` — added `Currency` choices + `currency` field
- `betting/forms.py` — added `CurrencyForm`
- `betting/models.py` — removed "credits" from `UserBalance.__str__`
- `challenges/models.py` — updated choice label

### Views & URLs
- `website/views.py` — added `CurrencyUpdateView`, updated `AccountView` context
- `website/urls.py` — added `currency_update` path
- `betting/views.py` — uses `format_currency()` in error/detail strings, passes raw balance (not pre-formatted)

### Templates (currency display updates)
- `website/templates/website/components/navbar.html`
- `website/templates/website/components/balance_oob.html`
- `website/templates/website/account.html`
- `website/templates/website/signup.html`
- `matches/templates/matches/partials/leaderboard.html`
- `matches/templates/matches/partials/leaderboard_table.html`
- `matches/templates/matches/partials/recap_card.html`
- `betting/templates/betting/my_bets.html`
- `betting/templates/betting/profile.html`
- `betting/templates/betting/partials/bet_form.html`
- `betting/templates/betting/partials/bet_confirmation.html`
- `betting/templates/betting/partials/quick_bet_form.html`
- `betting/templates/betting/partials/parlay_slip.html`
- `betting/templates/betting/partials/parlay_confirmation.html`
- `betting/templates/betting/partials/bailout_overlay.html`
- `challenges/templates/challenges/challenges_page.html`
- `challenges/templates/challenges/partials/challenge_card.html`
- `challenges/templates/challenges/partials/challenge_list.html`
- `challenges/templates/challenges/partials/challenge_toast.html`
- `rewards/templates/rewards/partials/reward_toast.html`

### Consumers
- `rewards/consumers.py` — passes `user` in all `render_to_string` calls

### Data
- `challenges/challenge_definitions.py` — updated description text
