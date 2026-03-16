# Phase 26: Homer Bot

A configurable bot strategy where each instance blindly backs a single EPL team.
Multiple Homer bots can coexist, each supporting a different club.
Instances are created and configured entirely through the Django admin — no seeding command needed.

---

## Behaviour

### When their team is playing

**Home match** — bet `HOME_WIN`, full confidence:
- Stake: 15–25% of balance, max 150

**Away match, team is NOT a big underdog** (away_win odds < `draw_underdog_threshold`) — bet `AWAY_WIN`:
- Stake: 10–20% of balance, max 150

**Away match, team IS a big underdog** (away_win odds ≥ `draw_underdog_threshold`) — bet `DRAW`:
- A homer reluctantly accepts a point when the odds say a win is unlikely
- Same stake range: 10–20% of balance, max 150
- `draw_underdog_threshold` defaults to `3.50` and is configurable per bot instance

### When their team is not playing

Skip entirely. Homer does not care about other clubs.

### Odds ceiling

None. Blind loyalty doesn't do expected-value calculations.

---

## New components

### `bots/models.py` (new file)

```python
class HomerBotConfig(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="homer_config",
        limit_choices_to={"is_bot": True},
    )
    team = models.ForeignKey(
        Team,
        on_delete=models.CASCADE,
        related_name="homer_bots",
    )
    draw_underdog_threshold = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("3.50"),
        help_text="Away-win odds at or above this value trigger a DRAW bet instead of AWAY_WIN.",
    )

    def __str__(self):
        return f"{self.user.display_name} → {self.team.name}"
```

### `bots/strategies.py` — new `HomerBotStrategy` class

```python
class HomerBotStrategy(BotStrategy):
    """Bets exclusively on one team, every match they play.

    - Home: always HOME_WIN, 15–25% of balance, max 150.
    - Away (not a big underdog): AWAY_WIN, 10–20% of balance, max 150.
    - Away (big underdog, odds >= draw_underdog_threshold): DRAW, 10–20% of balance, max 150.
    - Skips all matches where the team is not involved.
    """

    HOME_PCT = (0.15, 0.25)
    AWAY_PCT = (0.10, 0.20)
    MAX_STAKE = Decimal("150")

    def __init__(self, team_id: int, draw_underdog_threshold: Decimal = Decimal("3.50")):
        self.team_id = team_id
        self.draw_underdog_threshold = draw_underdog_threshold

    def pick_bets(self, available_matches, odds_map, balance):
        picks = []
        for match in available_matches:
            odds = odds_map.get(match.pk)
            if not odds:
                continue

            is_home = match.home_team_id == self.team_id
            is_away = match.away_team_id == self.team_id

            if not (is_home or is_away):
                continue

            if is_home:
                selection = "HOME_WIN"
                pct = Decimal(str(random.uniform(*self.HOME_PCT)))
            else:
                if odds["away_win"] >= self.draw_underdog_threshold:
                    selection = "DRAW"
                else:
                    selection = "AWAY_WIN"
                pct = Decimal(str(random.uniform(*self.AWAY_PCT)))

            stake = _clamp_stake(
                (balance * pct).quantize(Decimal("0.01")),
                ceiling=self.MAX_STAKE,
            )
            picks.append(BetPick(match_id=match.pk, selection=selection, stake=stake))

        return picks
```

### `bots/registry.py` — update `get_strategy_for_bot()`

Check for a `HomerBotConfig` before falling back to the static `STRATEGY_MAP`:

```python
def get_strategy_for_bot(user):
    """Return an instantiated strategy for the given bot user, or None."""
    # Homer bots are configured via HomerBotConfig, not the static map
    from bots.models import HomerBotConfig  # local import avoids circular at module level

    try:
        config = user.homer_config
        return HomerBotStrategy(
            team_id=config.team_id,
            draw_underdog_threshold=config.draw_underdog_threshold,
        )
    except HomerBotConfig.DoesNotExist:
        pass

    cls = STRATEGY_MAP.get(user.email)
    return cls() if cls else None
```

### `bots/admin.py` (new file)

```python
from django.contrib import admin
from bots.models import HomerBotConfig


@admin.register(HomerBotConfig)
class HomerBotConfigAdmin(admin.ModelAdmin):
    list_display = ("user", "team", "draw_underdog_threshold")
    list_select_related = ("user", "team")
    autocomplete_fields = ("user", "team")
```

`Team` and `User` already have admin registrations with `search_fields`, so `autocomplete_fields` will work out of the box.

### Migration

Standard `makemigrations bots` — adds the `HomerBotConfig` table.

---

## Creating a Homer bot instance (admin workflow)

1. Go to **Users → Add user**, set:
   - Email: e.g. `arsenal-homer@bots.eplbets.local`
   - Display name: e.g. `Gooner Gary`
   - `is_bot = True`, `is_active = True`
   - Set unusable password
2. Go to **Bots → Homer bot configs → Add**, select the user and their team.
3. The next `run_bot_strategies` Celery beat cycle will pick them up automatically — no code change needed.

---

## Tests to write

| File | What to cover |
|------|---------------|
| `bots/tests/test_strategies.py` | Home match → `HOME_WIN`; away match below threshold → `AWAY_WIN`; away match at/above threshold → `DRAW`; non-team match → skipped; no odds → skipped |
| `bots/tests/test_registry.py` | `get_strategy_for_bot()` returns `HomerBotStrategy` for a user with `HomerBotConfig`; still returns static strategy for a normal bot user |

---

## Files changed / created

| File | Action |
|------|--------|
| `bots/models.py` | Create |
| `bots/migrations/XXXX_add_homer_bot_config.py` | Create (via makemigrations) |
| `bots/strategies.py` | Add `HomerBotStrategy` |
| `bots/registry.py` | Update `get_strategy_for_bot()`, add `HomerBotStrategy` import |
| `bots/admin.py` | Create |
