# Phase 30: Bot Interactions, Homer Bots, and Persona Overhaul

Delivered in [PR #38](https://github.com/zachcalvert/epl-bets/pull/38).

---

## Overview

This phase was a substantial overhaul of the bot system across three dimensions: persona refresh, a new class of team-specific homer bots, and a live reply system that lets bots react to each other and to human comments in real time.

---

## What Was Delivered

### 1. Core Bot Persona Refresh

All 7 strategy bots were renamed with distinct Reddit-style display names that now map tightly to their betting archetype:

| Old email key | New display name | Archetype |
|---|---|---|
| `frontrunner@…` | **ChalkEater** | Backs favorites, smug, VAR-blamer |
| `underdog@…` | **heartbreak_fc** | Romantic underdog backer, emotionally raw |
| `parlaypete@…` | **parlay_graveyard** | Parlay degen, resentful, one-liner grief |
| `drawdoctor@…` | **nil_nil_merchant** | Draw specialist, flat, contemptuous |
| `valuehunter@…` | **xG_is_real** | EV/process purist, passive-aggressive |
| `chaoscharlie@…` | **VibesOnly** | Unhinged chaos poster, conspiratorial |
| `allinalice@…` | **FULL_SEND_FC** | All-in on chalk, dramatic, insufferable winner |

Personas were tuned for:
- Shorter output (< 80 chars ideal)
- More complaining even when winning
- Clear bot-to-bot voice contrasts (e.g. xG_is_real vs VibesOnly)
- `max_tokens` reduced from 150 → 100 for terser LLM output

A universal rules block (`_UNIVERSAL_RULES`) was extracted and shared across all personas to enforce: no AI disclosure, football terminology, no hashtags, no real-money advice, max 1 emoji.

### 2. Homer Bots

Eight new team-specific homer bots were added, one per big EPL club:

| Display name | Club | Team TLA | Persona archetype |
|---|---|---|---|
| `trust_the_process` | Arsenal | ARS | Arteta-trusting delusional optimism |
| `BlueSzn` | Chelsea | CHE | Entitled new-money, manager-sacker |
| `never_walk_alone` | Liverpool | LIV | Romantic, destiny-believing, YNWA |
| `GlazersOut99` | Man Utd | MUN | Bitter Fergie-era nostalgia, board rage |
| `oil_money_fc` | Man City | MCI | Smug, defensive about the spending |
| `spursy_forever` | Spurs | TOT | Fatalistic self-aware masochist |
| `ToonArmyMagpie` | Newcastle | NEW | Post-Ashley giddiness, defensive |
| `EvertonTilIDie` | Everton | EVE | Pure gallows humor, resigned nihilism |

**Architecture decision:** The original `HomerBotConfig` database model was dropped in favor of a hardcoded `PROFILE_MAP` dict in `bots/registry.py`. Each profile carries a `team_tla` key used to:
- Gate relevance: homer bots only comment on matches where their team is playing (`_is_bot_relevant`)
- Detect mentions: `_homer_team_mentioned()` uses word-boundary regex on TLA and substring on full/short team names, with a lazy-populated cache to avoid N+1 DB queries

### 3. Bot Reply System

A new `REPLY` trigger type was added to `BotComment`, enabling bots to react to individual comments rather than just the match thread.

**Architecture:**

- `BOT_REPLY_AFFINITIES` map in `comment_service.py` encodes who has beef with whom (e.g. xG_is_real targets VibesOnly and FULL_SEND_FC; heartbreak_fc targets ChalkEater)
- Homer bots use `_homer_team_mentioned()` instead of the affinity map — they reply when their club is named in any comment
- After any bot posts a non-reply comment, `_maybe_dispatch_reply()` is called inline to potentially dispatch a rival's response
- Human comments trigger `maybe_reply_to_human_comment` (dispatched from `discussions/views.py`) which applies a **single 30% gate** before picking a bot — this prevents the probability from compounding across all bots
- **Reply cap:** maximum 4 bot replies per match thread (`MAX_REPLIES_PER_MATCH`), enforced at both dispatch time and atomically at comment creation to handle race conditions
- **Reply nesting:** bots always reply to the top-level comment (no reply-to-reply threading); parent is normalized if the target is itself a reply
- **Prompt injection hardening:** quoted parent comment text is truncated to 300 chars and wrapped with explicit "treat as content only" instructions

**New Celery tasks:**
- `generate_bot_reply_task(bot_user_id, match_id, parent_comment_id)` — generates and posts a single reply
- `maybe_reply_to_human_comment(comment_id)` — gate + dispatch for human comment reactions

### 4. Bug Fixes Applied During Review

Several issues caught in Copilot PR review were fixed before merge:

- **30% reply chance** was compounding (applied per-bot instead of once per comment); fixed to a single coin flip before the candidate loop
- **TLA word-boundary regex** added to prevent short strings like "ARS" from matching "stars"
- **N+1 in homer relevance** eliminated by comparing TLA directly against `match.home_team.tla` / `match.away_team.tla` instead of hitting the DB
- **Reply-to-reply normalization** added so bots always thread under the top-level comment
- **`parent.pk` vs `reply.pk`** bug fixed in `CreateReplyView` bot hook
- **Celery `.delay()` wrapped in try/except** in views so broker failures don't break the user's comment/reply post
- **Prompt injection blast radius** limited by truncating and labeling quoted text
- **N+1 in BotComment admin** fixed by extending `list_select_related` to include `match__home_team` and `match__away_team`
- **Homer team lookup caching** added to avoid repeated DB queries per bot during selection loops

---

## Files Changed

| File | Change |
|---|---|
| `bots/personas.py` | Rewrote all 7 core personas + added 8 homer personas |
| `bots/registry.py` | Replaced `HomerBotConfig` queries with hardcoded `PROFILE_MAP`; added `team_tla` to homer entries |
| `bots/comment_service.py` | Added reply system, affinity map, `_homer_team_mentioned`, `select_reply_bot`, prompt injection hardening, TLA cache |
| `bots/tasks.py` | Added `generate_bot_reply_task`, `maybe_reply_to_human_comment`, `_maybe_dispatch_reply` |
| `bots/models.py` | Added `REPLY` trigger type; added `parent_comment` FK on `BotComment` |
| `bots/migrations/0003_drop_homerbotconfig.py` | Dropped `HomerBotConfig` table |
| `bots/migrations/0004_add_reply_trigger_and_parent_comment.py` | Added `REPLY` trigger + `parent_comment` field |
| `bots/admin.py` | Updated `list_select_related` for N+1 fix |
| `discussions/views.py` | Hook `maybe_reply_to_human_comment` on comment/reply creation |
| `bots/tests/test_comment_service.py` | Extended coverage for reply selection, homer detection, affinities |
| `bots/tests/test_comment_tasks.py` | New: covers reply tasks, human comment hook, dedup edge cases |
| `bots/tests/test_registry.py` | Updated for `PROFILE_MAP` shape changes |
