# Feature: Bot Members

## Overview

Six automated user accounts that place bets in distinctive styles to populate leaderboards and make the app feel alive from day one. Bots bet real virtual currency, win and lose, and appear alongside human users on all leaderboards.

---

## Design Decisions

- **Real User accounts** — bots are standard `User` rows with `is_bot=True`. No separate model. They appear naturally on leaderboards, match sentiment bars, and bet history.
- **Unusable passwords + non-routable email domain** — `@bots.eplbets.local` emails can't receive mail; `set_unusable_password()` blocks login. Bots can never be logged into.
- **Staggered timing** — `run_bot_strategies` (every 35 min) dispatches per-bot tasks with a random 1-10 minute countdown each, so bets trickle in naturally rather than appearing all at once.
- **Duplicate prevention** — each bot only sees matches it has no pending bet on, so it never double-bets a fixture.
- **Auto-bailout** — when a bot's balance drops below 50 credits with no pending bets, it receives an automatic bailout (1000-3000 credits) using the existing `Bankruptcy`/`Bailout` models.
- **Settlement is free** — bots' bets settle via the existing `settle_match_bets` Celery task, exactly like human bets. Stats, badges, and streaks all update normally.

---

## The Bots

### The Frontrunner (`frontrunner@bots.eplbets.local`)
Bets on the match favorite — the outcome with the lowest odds. Skips fixtures where no outcome has odds below **1.80** (no clear favorite). Stake: 5-15% of balance, capped at 100.

### Underdog United (`underdog@bots.eplbets.local`)
Bets on the underdog — the outcome with the highest odds. Only bets when the longest-shot odds are **≥ 3.00**. Conservative stakes to survive the inevitable losing runs: 2-5% of balance, capped at 50.

### Parlay Pete (`parlaypete@bots.eplbets.local`)
Places one parlay per run, selecting 3-5 legs where the best available odds fall in the **1.40-2.50** range (value territory, not coinflips). Never places single bets. Stake: 3-8% of balance, capped at 30.

### The Draw Doctor (`drawdoctor@bots.eplbets.local`)
Specialist draw bettor. Only bets on `DRAW`, and only when draw odds sit between **2.80-3.80** — the "sweet spot" where draws are priced fairly but not as moonshots. Stake: 5-10% of balance, capped at 75.

### Value Victor (`valuehunter@bots.eplbets.local`)
Looks for bookmaker disagreement. For each match, computes the spread between the highest and lowest bookmaker odds for each outcome. Bets the outcome with the largest spread when it exceeds **0.30** — a signal that the market is uncertain. Stake: 8-12% of balance, capped at 80.

### Chaos Charlie (`chaoscharlie@bots.eplbets.local`)
Randomly decides whether to bet on each available match (50% chance). Random selection, random stake (5-100). Purely chaotic — fun on the leaderboard.

---

## Architecture

```
bots/
    strategies.py       # BotStrategy ABC + 6 concrete implementations
    registry.py         # Maps bot emails to strategy classes
    services.py         # place_bot_bet(), place_bot_parlay(), odds helpers, maybe_topup_bot()
    tasks.py            # run_bot_strategies (periodic), execute_bot_strategy (per-bot)
    management/
        commands/
            seed_bots.py
```

### Strategy Interface

```python
class BotStrategy(ABC):
    def pick_bets(self, available_matches, odds_map, balance) -> list[BetPick]: ...
    def pick_parlays(self, available_matches, odds_map, balance) -> list[ParlayPick]: ...
```

`odds_map` is `{match_id: {"home_win": D, "draw": D, "away_win": D}}` — best odds across all bookmakers, consistent with the odds board views. ValueHunter additionally receives `odds_map["_full"]` with per-bookmaker rows for spread analysis.

### Celery Schedule

The bot task runs every **35 minutes** — offset from the 30-minute odds sync so bots always have fresh odds. Each bot is then dispatched individually with a random 1-10 minute delay.

---

## Setup

```bash
# Create bot accounts (idempotent)
docker compose run --rm web python manage.py seed_bots

# Run migrations (adds is_bot field to users)
docker compose run --rm web python manage.py migrate
```

---

## Adding a New Bot

1. Add a strategy class to `bots/strategies.py` extending `BotStrategy`
2. Add the bot profile to `BOT_PROFILES` in `bots/registry.py`
3. Re-run `seed_bots` to create the account
