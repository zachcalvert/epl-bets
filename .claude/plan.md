# Bankruptcy & Bailout System

## Overview
When a user's balance drops below the minimum bet (0.50 cr) **and** they have no pending bets, they're considered bankrupt. A full-page overlay blocks the site until they request a bailout — a tongue-in-cheek 10-second countdown where "The EPL Bets Central Bank" reviews their application, then credits them a random amount between $1k–$3k.

## Models (`betting/models.py`)

### `Bankruptcy`
- `user` — ForeignKey to User
- `balance_at_bankruptcy` — DecimalField (snapshot of what they had)
- `created_at` — DateTimeField(auto_now_add)

### `Bailout`
- `user` — ForeignKey to User
- `bankruptcy` — OneToOneField to Bankruptcy (each bankruptcy gets exactly one bailout)
- `amount` — DecimalField (the random 1000–3000 credited)
- `created_at` — DateTimeField(auto_now_add)

## Backend

### Context processor (`betting/context_processors.py`) — new file
- For authenticated users: check `balance < 0.50` AND `pending_bets == 0`
- Adds `is_bankrupt: bool` to every template context
- Register in `settings.py` TEMPLATES context_processors list

### Bailout view (`betting/views.py`)
- `POST /betting/bailout/` — `BailoutView`
- Validates: user is authenticated, balance < 0.50, no pending bets
- In atomic transaction:
  1. Create `Bankruptcy` record (balance snapshot)
  2. Generate random amount: `random.randint(1000, 3000)`
  3. Create `Bailout` record linked to the bankruptcy
  4. Credit `UserBalance.balance += amount`
- Returns JSON `{ "success": true, "amount": 2150, "new_balance": 2150.00 }` so JS can show the result before reloading

### URL (`betting/urls.py`)
- Add `path("bailout/", BailoutView.as_view(), name="bailout")`

## Frontend

### Overlay template (`betting/templates/betting/partials/bailout_overlay.html`)
Included in `base.html` when `is_bankrupt` is true. Structure:

```
Fixed full-screen overlay (z-60, above everything)
├── Dark semi-transparent backdrop
└── Centered card
    ├── Icon (bank/vault emoji or SVG)
    ├── "You're Bankrupt!" heading
    ├── Current balance display (e.g. "0.23 cr")
    ├── Bankruptcy count ("Bankruptcy #3")
    ├── "Request Bailout" button
    │
    ├── [After click — countdown state]
    │   ├── "The EPL Bets Central Bank is reviewing your application..."
    │   ├── Countdown number (10 → 0) with animation
    │   └── Cycling flavor text messages
    │
    └── [After countdown — result state]
        ├── "Bailout Approved!"
        ├── Amount granted (e.g. "+2,150 cr")
        └── Auto-reloads page after brief delay
```

### JavaScript (`bailout.js` or inline in the partial)
- "Request Bailout" click → starts 10-second countdown
- Countdown ticks with CSS scale animation on the number
- Flavor text cycles every ~2 seconds:
  - "Reviewing your portfolio..."
  - "Consulting the board of directors..."
  - "Running credit checks..."
  - "Shredding the evidence..."
  - "Approved! Processing funds..."
- At 0: POST to `/betting/bailout/` with CSRF token
- On response: show amount, then `window.location.reload()` after 2 seconds

### CSS (`styles.css`)
- Overlay backdrop blur + dark bg
- Countdown number scale/pulse animation
- Fade transitions between states (request → countdown → result)

### `base.html` changes
- After the closing `</nav>`, add: `{% if is_bankrupt %}{% include "betting/partials/bailout_overlay.html" %}{% endif %}`
- Overlay needs bankruptcy count from context (for display)

## Data flow summary

```
Settlement → balance drops below 0.50
  → Next page load: context processor detects bankruptcy
    → Overlay renders (blocks site)
      → User clicks "Request Bailout"
        → 10s client-side countdown
          → POST /betting/bailout/
            → Server: create Bankruptcy + Bailout, credit balance
              → Client: show result, reload page
                → Context processor: balance is fine now, no overlay
```

## Files to create/modify

| File | Action |
|------|--------|
| `betting/models.py` | Add `Bankruptcy` and `Bailout` models |
| `betting/context_processors.py` | New — bankruptcy detection logic |
| `epl_bets/settings.py` | Register context processor |
| `betting/views.py` | Add `BailoutView` |
| `betting/urls.py` | Add bailout URL |
| `betting/templates/betting/partials/bailout_overlay.html` | New — the overlay template |
| `website/templates/website/base.html` | Include overlay partial |
| `website/static/website/css/styles.css` | Overlay + countdown animations |
| Migration | `makemigrations` for new models |
