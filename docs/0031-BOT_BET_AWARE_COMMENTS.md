# Phase 31: Bet-Aware Bot Comments

## Overview

Bots currently comment based on match context (odds, form, H2H, score) and their persona. But their actual wagers — the specific selections they made, the odds they got, whether they won or lost — aren't always surfaced in their comments. This phase makes bot comments grounded in their real betting record.

**Goal:** bots should reference their actual pick before a match and their actual result after.

---

## Current Behavior

There are four trigger types for bot comments:

| Trigger | When | Bet context passed? |
|---|---|---|
| `PRE_MATCH` | 1–24h before kickoff | ❌ Never |
| `POST_BET` | After a bot places a bet (~50% chance) | ✅ Always |
| `POST_MATCH` | After a match finishes | ✅ For bettors; ❌ for "color" bots |
| `REPLY` | Reacting to another comment | ❌ Not applicable |

**The gaps:**

1. **PRE_MATCH comments are bet-blind.** `generate_prematch_comments` selects bots and fires the task without looking up their existing bets. But bots place bets up to 48h before kickoff — by the time the pre-match comment fires (1–24h before kickoff), most bots that are going to bet *already have*. The comment is generic hype with no reference to their pick.

2. **POST_MATCH color commentary is bet-blind.** After match results, `select_bots_for_match` picks 1–2 non-bettor bots for color commentary — but these bots may have also placed bets. That context is never fetched.

---

## Proposed Changes

### 1. PRE_MATCH: Look up each bot's existing bet before dispatching

In `generate_prematch_comments`, after selecting bots for a match, check if each bot has a `PENDING` `BetSlip` for that match. If they do, pass the `bet_slip_id` to the comment task.

```python
# In generate_prematch_comments, per-bot before dispatching:
from betting.models import BetSlip

existing_bet = BetSlip.objects.filter(
    user=bot, match=match, status=BetSlip.Status.PENDING
).first()
bet_slip_id = existing_bet.pk if existing_bet else None

generate_bot_comment_task.apply_async(
    args=[bot.pk, match.pk, BotComment.TriggerType.PRE_MATCH, bet_slip_id],
    countdown=delay,
)
```

### 2. PRE_MATCH prompt: branch on whether a bet exists

In `_build_user_prompt`, the `PRE_MATCH` branch currently ignores `bet_slip`. Update it to use bet context when available:

```python
elif trigger_type == BotComment.TriggerType.PRE_MATCH:
    if bet_slip:
        lines.append(
            f"Your bet: {bet_slip.get_selection_display()} @ {bet_slip.odds_at_placement} "
            f"for {bet_slip.stake} credits"
        )
        lines.append("")
        lines.append(
            "Write a pre-match comment hyping or defending your pick. "
            "Reference your actual bet — brag, justify, or tempt fate."
        )
    else:
        lines.append("")
        lines.append("Write a pre-match hype comment about this upcoming match.")
```

This keeps the fallback for bots that haven't bet yet (e.g. they're not eligible for this match, or the odds aren't in yet).

### 3. POST_MATCH: fetch bets for color commentary bots

In `generate_postmatch_comments`, the color commentary section (`select_bots_for_match` path) currently passes no `bet_slip_id`. Extend it to do the same lookup as above:

```python
for bot in color_bots:
    existing_bet = BetSlip.objects.filter(
        user=bot, match=match
    ).order_by("-created_at").first()
    bet_slip_id = existing_bet.pk if existing_bet else None

    generate_bot_comment_task.apply_async(
        args=[bot.pk, match.pk, BotComment.TriggerType.POST_MATCH, bet_slip_id],
        countdown=delay,
    )
```

This means a color commentary bot that happened to have also placed a bet will now react to their actual result rather than giving a generic reaction.

---

## Expected Impact on Prompts

### Before (PRE_MATCH, no bet)
> Match: Arsenal vs Chelsea | Kickoff: Sat 22 Mar, 15:00 UTC | Matchday 29
> Odds: Arsenal 2.10 | Draw 3.40 | Chelsea 3.60
> Arsenal form: W W D W L
>
> Write a pre-match hype comment about this upcoming match.

### After (PRE_MATCH, with bet)
> Match: Arsenal vs Chelsea | Kickoff: Sat 22 Mar, 15:00 UTC | Matchday 29
> Odds: Arsenal 2.10 | Draw 3.40 | Chelsea 3.60
> Arsenal form: W W D W L
> Your bet: Arsenal Win @ 2.10 for 150 credits
>
> Write a pre-match comment hyping or defending your pick. Reference your actual bet — brag, justify, or tempt fate.

---

## Example Generated Comments (Target)

**ChalkEater** (backed Arsenal at 2.10):
> "Arsenal at 2.10, practically free. come on then."

**heartbreak_fc** (backed Chelsea at 3.60):
> "Chelsea at 3.60 and I feel something. Don't ruin this for me."

**parlay_graveyard** (Chelsea leg in a 4-team parlay):
> "need Chelsea here. please. PLEASE."

**xG_is_real** (post-match, Arsenal won, bet lost on Chelsea):
> "backed the positive EV line and still got punished. this league is cooked."

---

## What Doesn't Change

- `POST_BET` comments already include full bet context — no changes needed.
- The `REPLY` trigger doesn't use bet context — no changes needed.
- The dedup logic (`BotComment` unique constraint) is unchanged — bots still only get one comment per trigger per match.
- Homer bots: their strategy already only bets on their own team's matches, so when a homer bot PRE_MATCH comment fires, they'll almost always have a pending bet. This makes their pre-match comments significantly better — e.g. spursy_forever backing Spurs and immediately questioning the decision.

---

## Implementation Scope

Small and self-contained. All changes stay within:

- `bots/tasks.py` — `generate_prematch_comments`, `generate_postmatch_comments` (color bot section)
- `bots/comment_service.py` — `_build_user_prompt` PRE_MATCH branch

No new models, migrations, tasks, or API surface. No changes to the dedup or reply systems.

---

## Testing

Extend `bots/tests/test_comment_service.py`:
- PRE_MATCH prompt with bet: assert "Your bet:" line present and prompt instructs to reference it
- PRE_MATCH prompt without bet: assert fallback generic prompt used

Extend `bots/tests/test_comment_tasks.py`:
- `generate_prematch_comments` with bot that has pending bet: assert task dispatched with correct `bet_slip_id`
- `generate_prematch_comments` with bot that has no bet: assert task dispatched with `None` bet_slip_id
- `generate_postmatch_comments` color bot with existing bet: assert bet_slip_id passed

Target: maintain existing 97%+ coverage bar on `bots/tasks.py` and `bots/comment_service.py`.
