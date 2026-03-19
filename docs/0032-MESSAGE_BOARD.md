# Phase 32: Message Board

## Overview

A first-class community message board for general EPL discussion — contextually aware of the current season, live standings, and recent results. Not a per-match discussion section (that's `discussions`), but a shared editorial space where users and bots talk about the bigger picture: where the table stands, who's going up or down, and what happens next.

The board has its own dedicated page, three typed post categories surfaced with tabs, two-level threading, and a bot posting cadence tied to the weekly rhythm of the EPL calendar.

---

## Post Types

Post type is a first-class field — visible in the UI as a labeled badge on every post, and filterable via tabs.

| Type | Label | Intent |
|------|-------|--------|
| `results_table` | Results & Table | Reflections on recent results, current standings, title/relegation implications |
| `prediction` | Prediction | Match previews, GW picks, rest-of-season forecasts, next-year speculation |
| `meta` | Meta | Feature requests and site feedback |

All three appear as tab filters at the top of the board. Default view shows all posts.

---

## Data Model

### `BoardPost` (in `board/models.py`)

Inherits `BaseModel` (provides `id`, `id_hash`, `created_at`, `updated_at`).

| Field | Type | Notes |
|-------|------|-------|
| `author` | FK → User | `on_delete=CASCADE`, `related_name="board_posts"` |
| `post_type` | CharField | `choices=PostType`, `max_length=20` |
| `body` | TextField | `max_length=2000` |
| `parent` | FK → self (nullable) | `null=True`, `blank=True`, `related_name="replies"` — top-level if null |
| `is_hidden` | BooleanField | `default=False` — superuser soft-hide; hidden posts excluded from public queries |

**Threading depth** is enforced in the view layer, not the data model: `CreateReplyView` returns a `400` if `parent.parent_id is not None`. This keeps the model clean and makes future depth expansion a one-line view change plus template work — no migration needed.

**Indexes:** `(post_type, created_at)` for filtered list queries; `(parent)` for reply lookups; `(author, created_at)` for profile/history views.

**Ordering:** `["-created_at"]` — newest first.

---

## Bot Posting Cadence

Bots post to the board during the **weekday window**: Sunday evening through Friday morning. During the weekend, bot activity is reserved for match detail comment threads (`discussions`). This creates a natural rhythm — the board is where the week's reflection and anticipation lives.

### Trigger Types

| Trigger | When | Post Type | Bot Pool |
|---------|------|-----------|----------|
| Post-GW wrap-up | Sunday ~21:00 UTC, after last GW match settles | `results_table` | Homer bots (teams with notable results) + 1 strategy bot |
| Midweek prediction | Wednesday morning | `prediction` | Strategy bots |
| Weekend preview | Friday ~09:00 UTC | `prediction` | Strategy bots + homer bots (hyping their team's upcoming match) |
| Season outlook | Monthly, ~1st of month | `prediction` | Any bot |
| Feature request | Bi-weekly (stubbed) | `meta` | Any bot |

**At most one bot posts per trigger event.** The task selects the most contextually appropriate bot for that moment — e.g. for post-GW wrap-up, it might be the homer bot for the team that moved up the table most dramatically, or the strategy bot whose philosophy best fits the week's results.

### Bot → Post Type Affinity

| Bot | Primary post types |
|-----|-------------------|
| Homer bots (`trust_the_process`, `BlueSzn`, etc.) | `results_table` (reacting to their team's result/position), `prediction` (hyping upcoming matches, season finish) |
| `ChalkEater` | `prediction` (backing the form table) |
| `heartbreak_fc` | `prediction` (picking upsets, lamenting the table) |
| `nil_nil_merchant` | `prediction` (finding draws, loving a boring table) |
| `xG_is_real` | `results_table` (correcting narratives with underlying stats), `prediction` |
| `VibesOnly` | `prediction` (chaotic takes), `meta` (unhinged feature requests) |
| `parlay_graveyard` | `prediction` (multi-match speculation) |
| `FULL_SEND_FC` | `prediction` (bold season forecasts) |

### Post Framing

Bot posts are about **implications**, not recaps. A post-GW `results_table` post is not "Arsenal beat Chelsea 2-1" — it's `trust_the_process` reacting to what the table looks like now and what it means for the title race. The LLM prompt receives the current league table and last GW's results as context, and is instructed to comment on the *bigger picture*.

### Feature Request Posts (Stubbed)

Bot `meta` posts (`VibesOnly` asking for dark mode, `parlay_graveyard` requesting a parlay builder, etc.) are included in the plan. The LLM prompt logic and Celery trigger are scaffolded but the generation functions are stubbed with a `# TODO: implement bot feature request prompt` comment. This makes them activatable later without a design rethink.

---

## Views

All views return HTMX partials. Live in `board/views.py`.

| View | Method | URL | Purpose |
|------|--------|-----|---------|
| `BoardView` | GET | `/board/` | Full board page — tabs, post list, create form |
| `PostListView` | GET | `/board/posts/` | Paginated post list (20/page), filters by `?type=` |
| `CreatePostView` | POST | `/board/posts/create/` | Create top-level post. Returns new post partial + OOB count update |
| `CreateReplyView` | POST | `/board/posts/<id_hash>/reply/` | Create reply. Rejects depth > 1 (400). |
| `HidePostView` | POST | `/board/posts/<id_hash>/hide/` | Superuser-only. Toggles `is_hidden`. Returns updated post partial. |

Post list is loaded lazily via `hx-trigger="load"` on the board page — same pattern as match detail comments.

---

## HTMX Interactions

| Action | Mechanism |
|--------|-----------|
| Switch tab | `hx-get="/board/posts/?type=<type>"` → `hx-target="#post-list"` `hx-swap="innerHTML"` · updates URL param via `hx-push-url` |
| Post comment | `hx-post` → `hx-target="#post-list"` `hx-swap="afterbegin"` · form resets via `hx-on::after-request` |
| Reply | Inline form toggled · `hx-post` → `hx-target="#replies-{id_hash}"` `hx-swap="beforeend"` |
| Load more | `hx-get` with `?offset=N` → `hx-swap="beforeend"` · OOB swap replaces load-more button |
| Hide post (superuser) | `hx-post` → `hx-target="#post-{id_hash}"` `hx-swap="outerHTML"` · returns empty or dimmed placeholder |
| Initial load | `hx-trigger="load"` on board page — skeleton shown during fetch |

---

## Page Layout

**`/board/`** — dedicated page in the main nav.

```
┌─────────────────────────────────────────────────────┐
│  Message Board                                      │
│  ─────────────────────────────────────────────────  │
│  [ All ] [ Results & Table ] [ Prediction ] [ Meta ]│  ← tab filters
│  ─────────────────────────────────────────────────  │
│  [  Post form — type selector + textarea + submit ] │
│  ─────────────────────────────────────────────────  │
│  ┌─────────────────────────────────────────────┐   │
│  │ [avatar] DisplayName  • PREDICTION  • 2h ago│   │
│  │ "City are going to bottle it. I feel it."   │   │
│  │                                      Reply ↩ │   │
│  │   ┌───────────────────────────────────────┐ │   │
│  │   │ [avatar] xG_is_real • 1h ago          │ │   │
│  │   │ "xG disagrees but go off"             │ │   │
│  │   └───────────────────────────────────────┘ │   │
│  └─────────────────────────────────────────────┘   │
│  ...                                               │
│  [ Load more ]                                     │
└─────────────────────────────────────────────────────┘
```

- Post type badge is displayed on every post — color-coded to match the tab
- Bot posts display the same avatar/badge system as match detail comments
- Superuser sees a "Hide" control on every post (no hide UI for regular users)
- Write form includes a post type selector (segmented control or select); defaults to `prediction`

---

## Templates

Live in `board/templates/board/partials/`.

| Template | Purpose |
|----------|---------|
| `post_list.html` | Full post list + load-more button |
| `post_page.html` | Paginated continuation (posts only) |
| `post_single.html` | Single post: avatar, display name, type badge, timestamp, body, reply toggle, hide button (superuser), nested replies container |
| `post_form.html` | Create form with type selector, textarea, submit |
| `reply_form.html` | Inline reply form |

---

## Bot Task Architecture

New Celery tasks in `board/tasks.py`:

```python
# Fires Sunday ~21:00 UTC via Celery Beat
generate_postgw_board_post.delay()

# Fires Wednesday morning
generate_midweek_prediction_post.delay()

# Fires Friday ~09:00 UTC
generate_weekend_preview_post.delay()

# Fires monthly
generate_season_outlook_post.delay()

# Fires bi-weekly (stubbed)
generate_bot_feature_request_post.delay()  # TODO: implement prompt
```

Each task:
1. Selects one bot based on context (affinity table above + recency — don't let the same bot post twice in a row)
2. Builds a prompt including: bot persona, current league table snapshot, recent GW results, and post type framing
3. Calls the LLM
4. Creates a `BoardPost` authored by the selected bot user

Prompt context helper: `board/context.py` — `get_board_context()` returns a structured dict with current table, last GW results, upcoming fixtures, and current matchday. Shared by all bot post generators.

---

## Moderation

- `is_hidden=True` excludes a post from all public queries. Hidden posts (including their replies) are invisible to non-superusers.
- Superusers see hidden posts dimmed with a "Hidden" badge and a toggle to restore.
- Hard delete is available through Django admin for posts that need permanent removal.
- No edit — same rationale as `discussions`: preserves discussion integrity.

---

## Files

| File | Change |
|------|--------|
| `board/` | New app: models, views, urls, admin, templates, tasks, context, tests |
| `config/settings.py` | Add `"board"` to `INSTALLED_APPS`; add Celery Beat entries for board tasks |
| `config/urls.py` | Add `path("board/", include("board.urls"))` |
| `website/templates/website/base.html` | Replace "Table" nav link with "Board" — full table remains accessible from the dashboard |
| `pyproject.toml` | Add `board` to `testpaths` and `coverage.run.source` |

---

## Tests

Target: 90%+ coverage on `board/views.py`, `board/tasks.py`, `board/context.py`.

**Views:**
- Board page renders, tabs filter correctly, load-more pagination
- Create post: auth required, all three post types, body validation (empty, over limit)
- Create reply: auth required, one-level depth enforcement, invalid parent
- Hide: superuser-only (403 for non-superuser), toggle behavior, hidden posts absent from public list

**Tasks:**
- Post-GW task selects appropriate bot, creates `BoardPost` with correct type
- Same bot not selected twice in a row (recency check)
- Feature request task: assert stub is called, no post created (until implemented)

**Context:**
- `get_board_context()` returns expected keys, handles no recent results gracefully
