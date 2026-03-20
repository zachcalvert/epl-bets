# Phase 34: Bot Profile Admin

## Overview

Move bot persona prompts from hardcoded Python (`bots/personas.py`) into a database-backed `BotProfile` model editable through the Django admin. This lets us tweak bot personalities, voice, and style without code changes or redeployments.

Strategy implementations (bet-sizing logic, odds filters, etc.) remain in code — only the LLM persona prompts and cosmetic metadata become admin-editable.

---

## Data Model

### `BotProfile` (in `bots/models.py`)

Inherits `BaseModel`. One-to-one relationship with the User model (only for `is_bot=True` users).

| Field | Type | Notes |
|-------|------|-------|
| `user` | OneToOneField(User) | `limit_choices_to={"is_bot": True}`, `related_name="bot_profile"` |
| `strategy_type` | CharField(max_length=30, choices) | Maps to strategy class in `registry.py`. Choices: `frontrunner`, `underdog`, `parlay`, `draw_specialist`, `value_hunter`, `chaos_agent`, `all_in_alice`, `homer` |
| `team_tla` | CharField(max_length=5, blank) | Only used when `strategy_type=homer`. References `matches.Team.tla` |
| `persona_prompt` | TextField | The full system prompt sent to Claude. Seeded from `personas.py` defaults |
| `avatar_icon` | CharField(max_length=30) | Lucide icon name |
| `avatar_bg` | CharField(max_length=10) | Hex color for avatar background |
| `is_active` | BooleanField(default=True) | Soft-disable a bot without deleting |

---

## Admin Interface

`BotProfileAdmin` registered with:

- **list_display**: user display_name, strategy_type, team_tla, is_active
- **list_filter**: strategy_type, is_active
- **readonly_fields**: user (prevent reassignment after creation)
- **fieldsets**: Identity (user, strategy_type, team_tla, is_active), Appearance (avatar_icon, avatar_bg), Persona (persona_prompt as full-width textarea)

---

## Migration Path

### `seed_bots` command changes

1. Create/update the User record (unchanged)
2. Create `BotProfile` via `get_or_create` — only set `persona_prompt` on initial creation, never overwrite existing admin edits on re-seed
3. Always sync non-prompt fields (strategy_type, avatar, team_tla) from registry defaults

### Factory defaults

`bots/personas.py` and `bots/registry.py` remain as the canonical defaults. They are used only by `seed_bots` for initial creation. Runtime code reads from the database.

---

## Consumer Changes

### `bots/comment_service.py`

- `generate_bot_comment()`: Read `bot_user.bot_profile.persona_prompt` instead of `BOT_PERSONA_PROMPTS[email]`
- `select_bots_for_match()`: Check `hasattr(bot, 'bot_profile')` or use `BotProfile.objects.filter(user=bot).exists()` instead of `email in BOT_PERSONA_PROMPTS`
- `select_reply_bot()`: Same pattern
- `_is_bot_relevant()`: Read `bot.bot_profile.strategy_type` and `bot.bot_profile.team_tla` instead of email-based switch/case
- `_homer_team_mentioned()`: Read `bot.bot_profile.team_tla` instead of `PROFILE_MAP`

### `board/tasks.py`

- `_select_bot()`: Query `BotProfile` for eligible bots by strategy_type instead of hardcoded email lists
- `_generate_board_post()`: Read `bot_user.bot_profile.persona_prompt` instead of `BOT_PERSONA_PROMPTS[email]`
- Pool constants (`HOMER_BOT_EMAILS`, `STRATEGY_BOT_EMAILS`, `POST_TYPE_BOT_POOLS`) become queryset-based lookups

### `bots/registry.py`

- `get_strategy_for_bot()`: Read `bot_profile.strategy_type` and `bot_profile.team_tla` from DB instead of `PROFILE_MAP`

---

## What Does NOT Change

- **Strategy classes** (`bots/strategies.py`): Algorithmic logic stays in code
- **`_UNIVERSAL_RULES`**: Stays in `personas.py` as a reference template for seeding, but the full prompt (including rules) is stored in the DB field
- **`BOT_REPLY_AFFINITIES`**: Stays in `comment_service.py` — these are structural relationships, not personality text
- **User model**: `is_bot` flag remains; no changes to User schema
- **BotComment model**: Unchanged

---

## Files Changed

| File | Change |
|------|--------|
| `bots/models.py` | Add `BotProfile` model |
| `bots/admin.py` | Register `BotProfileAdmin` |
| `bots/management/commands/seed_bots.py` | Create `BotProfile` records on seed |
| `bots/comment_service.py` | Read prompts and metadata from `BotProfile` |
| `bots/registry.py` | `get_strategy_for_bot()` reads from DB |
| `board/tasks.py` | Read prompts and bot pools from `BotProfile` |
| `bots/migrations/` | New migration for `BotProfile` |
