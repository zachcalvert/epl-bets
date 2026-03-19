# Bot Interactions, Homer Bots & Rename Plan

## Overview

Three interconnected changes to the bot system:

1. **Bot reply system** — Bots reply to each other's (and humans') comments, creating natural thread arguments
2. **Hardcoded homer bots** — 8 team-specific homer bots added to the registry, replacing the `HomerBotConfig` admin model
3. **Fresh-start renames** — All 7 core bots get new display names with mixed vibes
4. **Persona tuning** — Shorter comments, more complaining across all personas

Total bots after this work: **15** (7 core + 8 homer) out of 50-user cap.

---

## Part 1: Renames (all core bots)

Mixed vibes — some reddit-handle, some gamertag, some real-ish.

| Current | New Name | Email (unchanged) | Rationale |
|---------|----------|-------------------|-----------|
| The Frontrunner | ChalkEater | frontrunner@ | Gamertag. "Chalk" is slang for favorite. Eats chalk for breakfast. |
| Underdog United | heartbreak_fc | underdog@ | Reddit handle. The hopeless romantic of the comment section. |
| Parlay Pete | parlay_graveyard | parlaypete@ | Reddit handle. Where parlays go to die. Self-aware suffering. |
| The Draw Doctor | nil_nil_merchant | drawdoctor@ | Reddit handle. Sells 0-0s to the masses. Proudly boring. |
| Value Victor | xG_is_real | valuehunter@ | Reddit handle. The insufferable process guy. |
| Chaos Charlie | VibesOnly | chaoscharlie@ | Gamertag. No stats, no logic, just vibes. |
| All In Alice | FULL_SEND_FC | allinalice@ | Reddit handle / gamertag hybrid. All caps energy. |

> **Note:** Emails stay the same so no migration is needed — only `display_name` changes in `BOT_PROFILES` and persona prompt text.

---

## Part 2: Homer Bots (8 hardcoded)

### Teams & Names

| Team | Display Name | Email | Avatar Icon | Color |
|------|-------------|-------|-------------|-------|
| Arsenal | trust_the_process | arsenal-homer@bots.eplbets.local | shield | #EF0107 |
| Chelsea | BlueSzn | chelsea-homer@bots.eplbets.local | gem | #034694 |
| Liverpool | never_walk_alone | liverpool-homer@bots.eplbets.local | heart | #C8102E |
| Manchester United | GlazersOut99 | manutd-homer@bots.eplbets.local | fire | #DA291C |
| Manchester City | oil_money_fc | mancity-homer@bots.eplbets.local | trophy | #6CABDD |
| Tottenham | spursy_forever | spurs-homer@bots.eplbets.local | target | #132257 |
| Newcastle | ToonArmyMagpie | newcastle-homer@bots.eplbets.local | bird | #241F20 |
| Everton | EvertonTilIDie | everton-homer@bots.eplbets.local | anchor | #003399 |

### Implementation

**a) Add homer profiles to `BOT_PROFILES` in registry.py:**

Each homer gets a new entry with a `team_tla` field (e.g. `"ARS"`, `"CHE"`) that `seed_bots` will use to look up the Team FK. The `strategy` field will be `HomerBotStrategy` — but since it needs a `team_id` at runtime, `get_strategy_for_bot()` will resolve the team from the profile's `team_tla`.

```python
# New entries in BOT_PROFILES:
{
    "email": "arsenal-homer@bots.eplbets.local",
    "display_name": "trust_the_process",
    "strategy": HomerBotStrategy,
    "team_tla": "ARS",
    "avatar_icon": "shield",
    "avatar_bg": "#EF0107",
},
# ... 7 more
```

**b) Refactor `get_strategy_for_bot()`:**

Instead of checking `HomerBotConfig` first, check for `team_tla` in the bot's profile entry. Look up the team by TLA and instantiate `HomerBotStrategy(team_id=team.pk)`. This replaces the `HomerBotConfig` DB lookup entirely.

```python
def get_strategy_for_bot(user):
    profile = PROFILE_MAP.get(user.email)  # new dict keyed by email
    if not profile:
        return None
    cls = profile["strategy"]
    if cls is HomerBotStrategy:
        team = Team.objects.filter(tla=profile["team_tla"]).first()
        if not team:
            return None
        return HomerBotStrategy(team_id=team.pk)
    return cls()
```

**c) Refactor `_is_bot_relevant()` in comment_service.py:**

Replace the homer `try/except` block with a lookup against the profile's `team_tla`:

```python
# In the else branch:
profile = PROFILE_MAP.get(email)
if profile and profile.get("team_tla"):
    from matches.models import Team
    team = Team.objects.filter(tla=profile["team_tla"]).first()
    if team:
        return match.home_team_id == team.pk or match.away_team_id == team.pk
return False
```

**d) Update `seed_bots` command:**

Already loops `BOT_PROFILES` — homer bots will be seeded automatically. No changes needed beyond the profiles being added.

**e) Homer persona prompts in personas.py:**

Each homer gets a system prompt. They share a common homer template but with team-specific flavor:

- **Universal homer trait:** Blind loyalty. Team is always the best, losses are always someone else's fault. Short, emotional, one-eyed.
- **Team-specific flavor:** Arsenal = "trust the process" delusion. Chelsea = entitled new-money energy. Liverpool = emotional, romantic, believes in destiny. Man Utd = bitter about the fall, "we're still massive." Man City = defensive about spending, smug when winning. Spurs = self-deprecating masochist, expects collapse. Newcastle = giddy new-money excitement meets old-school passion. Everton = pure gallows humor, accepts nothing good will ever happen.

**f) Remove `HomerBotConfig` model:**

- Delete `HomerBotConfig` from `bots/models.py`
- Delete from `bots/admin.py`
- Create a migration to drop the table
- Remove references from `get_strategy_for_bot()`, `_is_bot_relevant()`, tests

---

## Part 3: Bot Reply System

### New Trigger Type

Add `REPLY` to `BotComment.TriggerType`:

```python
REPLY = "REPLY", _("Reply to comment")
```

This requires a migration to add the new choice (though Django TextChoices don't need schema changes — just the constraint update).

### Reply Flow

**When do replies happen?**

After any bot comment is successfully posted (PRE_MATCH, POST_BET, or POST_MATCH), there's a chance to trigger reply generation. Implemented as a follow-up dispatch at the end of `generate_bot_comment()`:

```python
# At the end of generate_bot_comment(), after successful post:
if trigger_type != BotComment.TriggerType.REPLY:
    _maybe_dispatch_replies(match, comment, bot_user)
```

**`_maybe_dispatch_replies(match, comment, author)`:**

1. Check the current reply count for this match — if already at cap (4), skip
2. Pick 0-1 bots who would have "beef" with the comment (see affinity system below)
3. Dispatch `generate_bot_reply_task` with 2-8 minute stagger

**Reply to human comments:**

After a human posts a comment, we also dispatch a potential reply. This hooks into the existing `CreateCommentView` or `CreateReplyView` in discussions — after a successful comment creation by a non-bot user, dispatch a task to maybe generate a reply.

```python
# In discussions/views.py, after comment creation:
if not request.user.is_bot:
    from bots.tasks import maybe_reply_to_comment
    maybe_reply_to_comment.delay(comment.pk)
```

### Affinity / Beef System

A lightweight mapping of which bots are likely to reply to which. Not hard rules — just weighted preferences.

```python
# In comment_service.py
BOT_REPLY_AFFINITIES = {
    # email -> list of emails they're likely to reply to (weighted)
    "valuehunter@bots.eplbets.local": [
        "chaoscharlie@bots.eplbets.local",   # process vs vibes
        "allinalice@bots.eplbets.local",      # EV vs YOLO
    ],
    "frontrunner@bots.eplbets.local": [
        "underdog@bots.eplbets.local",        # chalk vs heart
    ],
    "underdog@bots.eplbets.local": [
        "frontrunner@bots.eplbets.local",     # mutual disdain
        "allinalice@bots.eplbets.local",      # "wow you backed City"
    ],
    "parlaypete@bots.eplbets.local": [
        "allinalice@bots.eplbets.local",      # single bet resentment
        "frontrunner@bots.eplbets.local",     # "congrats on your boring bet"
    ],
    "chaoscharlie@bots.eplbets.local": [
        "valuehunter@bots.eplbets.local",     # suspicious of the stats guy
    ],
    # Homer bots: likely to reply to anyone talking about their team
    # (handled dynamically, not in this static map)
}
```

For homer bots: any comment mentioning their team's name makes them eligible to reply.

For human comments: any relevant bot (per `_is_bot_relevant`) has a small chance (30%) of replying.

### Reply Prompt

Extend `_build_user_prompt()` to handle `REPLY` trigger:

```python
elif trigger_type == BotComment.TriggerType.REPLY:
    lines.append(f"\nAnother user ({parent_comment.user.display_name}) wrote:")
    lines.append(f'"{parent_comment.body}"')
    lines.append("")
    lines.append("Write a short reply to this comment. Agree, disagree, or dunk on it — stay in character.")
```

### Dedup for Replies

The existing unique constraint is `(user, match, trigger_type)`. With REPLY, a bot could only reply once per match. That's actually fine for v1 — keeps threads from getting spammy. One reply per bot per match.

### BotComment Model Changes

Add a nullable `parent_comment` FK to `BotComment` to track which comment triggered the reply:

```python
parent_comment = models.ForeignKey(
    "discussions.Comment",
    on_delete=models.SET_NULL,
    null=True,
    blank=True,
    related_name="bot_replies",
    verbose_name=_("replied to"),
)
```

### Reply Cap

Track reply count per match to enforce the 2-4 cap:

```python
reply_count = BotComment.objects.filter(
    match=match, trigger_type=BotComment.TriggerType.REPLY
).count()
if reply_count >= 4:
    return  # enough drama for this thread
```

---

## Part 4: Persona Tuning

### Shorter Comments

Update `_UNIVERSAL_RULES` to emphasize brevity even more:

```
- Keep it SHORT. A few words. A sentence if you must. Under 80 characters is ideal.
  Typing takes energy. The less you say, the less they can use against you.
```

Reduce `max_tokens` from 150 → 100 in the API call.

### More Complaining

Add to `_UNIVERSAL_RULES`:

```
- You are a sore loser. When things go wrong, complain. Blame refs, VAR, the pitch,
  the weather, the bookmaker, the universe. Never blame yourself.
- Even when you win, find something to grumble about. The payout should've been bigger.
  The match was ugly. The odds were disrespectful.
```

Update each individual persona to lean into their specific complaint style (see Part 2 homer personas for examples of tone).

---

## Part 5: Cleanup

- Remove `HomerBotConfig` model, migration, admin registration
- Remove `HomerBotConfig` import from `registry.py` and `comment_service.py`
- Update all tests to reflect new bot names, homer profiles, and reply trigger
- Add new tests for reply generation, affinity matching, reply cap, human-comment reply hook

---

## File Change Summary

| File | Changes |
|------|---------|
| `bots/registry.py` | Add 8 homer profiles to `BOT_PROFILES`, add `PROFILE_MAP`, refactor `get_strategy_for_bot()` |
| `bots/personas.py` | Rename core bot prompts, add 8 homer prompts, tune `_UNIVERSAL_RULES` |
| `bots/models.py` | Remove `HomerBotConfig`, add `REPLY` trigger type, add `parent_comment` FK to `BotComment` |
| `bots/comment_service.py` | Add reply generation logic, affinity map, reply cap, refactor homer relevance check |
| `bots/tasks.py` | Add `generate_bot_reply_task`, `maybe_reply_to_comment` task |
| `bots/admin.py` | Remove `HomerBotConfigAdmin` |
| `discussions/views.py` | Add post-comment hook to trigger bot replies to human comments |
| `bots/management/commands/seed_bots.py` | No changes needed (already iterates `BOT_PROFILES`) |
| `bots/migrations/XXXX_*.py` | Drop `HomerBotConfig` table, add `REPLY` choice + `parent_comment` FK |
| `bots/tests/*` | Update for renames, new bots, reply system |

---

## Implementation Order

1. **Renames + persona tuning** — Low risk, immediate impact. Change display names and prompt text.
2. **Homer bots** — Add profiles, personas, refactor strategy resolution, drop HomerBotConfig.
3. **Reply system** — New trigger type, affinity map, reply generation, tasks, view hook.
4. **Tests** — Update existing tests for renames, add new tests for homers + replies.
5. **Seed + verify** — Run `seed_bots`, verify all 15 bots appear, test comment generation.
