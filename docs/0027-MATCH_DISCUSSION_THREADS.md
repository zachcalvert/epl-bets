# Phase 27: Match Discussion Threads

## Overview

Threaded comment sections on match detail pages, giving users a place to discuss upcoming and finished matches. Built around a core insight unique to a betting context: every comment can carry a credibility signal in the form of a bet position badge ("Backing Arsenal", "Backing Draw"), surfacing who has skin in the game without requiring any extra user action.

---

## Design Decisions

- **Any authenticated user can comment** — bet position badge appears automatically when the user has a bet on that match; no gate required. Keeps discussion inclusive while still rewarding bettors with visible credibility.
- **One level of threading** — top-level comments can have replies; replies cannot be replied to. Enforced at the view layer. Keeps threads readable without infinite nesting complexity.
- **Chronological ordering** — oldest first. Discussions read like conversations.
- **Soft delete, no edit** — `is_deleted` flag preserves reply trees. Deleted comments with replies show a "[Comment deleted]" placeholder; deleted comments with no replies are hidden entirely. No editing — preserves discussion integrity and prevents retroactive hot-take revision.
- **1000 character limit** — long enough for a real point, short enough to stay focused.
- **Lazy-loaded** — the discussion section loads via `hx-trigger="load"` after the match detail page renders, keeping initial page performance unaffected.
- **New `discussions` app** — clean separation from `betting` and `matches`. Comment model, views, URLs, and templates are self-contained.

---

## Model

### `Comment` (in `discussions/models.py`)

Inherits `BaseModel` (provides `id`, `id_hash`, `created_at`, `updated_at`).

| Field | Type | Notes |
|-------|------|-------|
| `match` | FK → Match | `on_delete=CASCADE`, `related_name="comments"` |
| `user` | FK → User | `on_delete=CASCADE`, `related_name="comments"` |
| `parent` | FK → self (nullable) | `null=True`, `related_name="replies"` — top-level if null |
| `body` | TextField | `max_length=1000` |
| `is_deleted` | BooleanField | `default=False` — soft delete |

Indexes: `(match, created_at)` for the primary list query; `(parent)` for reply lookups.
Ordering: `["created_at"]` (chronological).

---

## Bet Position Badge

The distinguishing feature. After loading comments, a single efficient query maps each commenter to their most recent bet on the match:

```python
BetSlip.objects.filter(match_id=match_pk, user_id__in=user_ids)
    .order_by("user_id", "-created_at")
    .distinct("user_id")
    .values("user_id", "selection")
```

Each comment is then annotated with a `bet_position` string before being passed to the template:

| Selection | Badge text |
|-----------|-----------|
| `HOME_WIN` | "Backing {home_team.short_name}" |
| `DRAW` | "Backing Draw" |
| `AWAY_WIN` | "Backing {away_team.short_name}" |

---

## Visible Comment Definition

A top-level comment is "visible" (included in the list and counted) if:
- `is_deleted=False`, **or**
- `is_deleted=True` and it has at least one non-deleted reply

This is encapsulated in `_visible_top_level_qs(match)` using an `Exists` subquery, and used consistently across the list query, comment count, pagination, and OOB count updates.

---

## Views

All views return HTMX partials. Live in `discussions/views.py`.

| View | Method | URL | Purpose |
|------|--------|-----|---------|
| `CommentListView` | GET | `match/<match_pk>/comments/` | Load visible top-level comments + prefetched replies. Offset pagination (20/page). |
| `CreateCommentView` | POST | `match/<match_pk>/comments/create/` | Create top-level comment. Returns new comment partial + OOB count update. |
| `CreateReplyView` | POST | `match/<match_pk>/comments/<comment_pk>/reply/` | Create reply. Rejects replies-to-replies (400). |
| `DeleteCommentView` | POST | `match/<match_pk>/comments/<comment_pk>/delete/` | Soft-delete. Owner-only (403 otherwise). Returns placeholder if replies exist, else empty + OOB count update. |

---

## HTMX Interactions

| Action | Mechanism |
|--------|-----------|
| Post comment | `hx-post` → `hx-target="#comment-list"` `hx-swap="beforeend"` · form resets via `hx-on::after-request` |
| Update count | OOB swap: `<span id="comment-count" hx-swap-oob="true">` appended to create/delete responses |
| Reply | Hidden inline form toggled via `onclick` · `hx-post` → `hx-target="#replies-{id_hash}"` `hx-swap="beforeend"` · collapses on success |
| Reply error | OOB swap into `#reply-error-{id_hash}` with field error text |
| Delete | `hx-post` → `hx-target="#comment-{id_hash}"` `hx-swap="outerHTML"` |
| Load more | `hx-get` with `?offset=N` → `hx-target="#comment-list"` `hx-swap="beforeend"` · OOB swap replaces load-more button |
| Initial load | `hx-trigger="load"` on match detail page — skeleton shown during fetch |

---

## Templates

All live in `discussions/templates/discussions/partials/`.

| Template | Purpose |
|----------|---------|
| `comment_list.html` | Full section wrapper: heading with count, comment form or login CTA, comment list, load-more button |
| `comment_page.html` | Paginated continuation: comment items only + OOB load-more button update |
| `comment_single.html` | Single comment: avatar initial, display name, bet badge, timestamp, body, reply toggle, delete button, nested replies container |
| `comment_form.html` | Top-level comment form with submit button |
| `comment_count_oob.html` | OOB count span for create/delete responses |
| `login_cta.html` | "Log in to join the discussion" with `next=` pointing to match detail URL |

---

## Files Changed

| File | Change |
|------|--------|
| `discussions/` | New app (model, form, views, URLs, admin, templates, tests) |
| `config/settings.py` | Added `"discussions"` to `INSTALLED_APPS` |
| `config/urls.py` | Added `path("", include("discussions.urls"))` |
| `matches/templates/matches/match_detail.html` | Added lazy-loaded discussion section between odds comparison and Under the Hood |
| `website/templates/website/components/empty_state.html` | Added `chat` icon option |
| `pyproject.toml` | Added `discussions` to `testpaths` and `coverage.run.source` |

---

## Tests

35 tests in `discussions/tests/test_views.py`, covering:

- Empty state, comment display, reply nesting, pagination, login CTA vs. form
- Bet position badges (home/draw/away, most-recent-bet-wins)
- Comment count accuracy (only visible comments counted)
- Create: auth redirect, comment creation, OOB count update, form validation (empty, over limit)
- Reply: auth redirect, creation, one-level enforcement, form validation
- Delete: auth redirect, soft delete, empty response vs. placeholder, forbidden for non-owner, OOB count update, reply delete skips count update
