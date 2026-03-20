# Phase 35: Match Notes

## Overview

Add admin-authored match notes — free-form observations from watching a match (key moments, goalscorers, red cards, drama) — that get injected into bot comment prompts. This gives all bots shared, match-specific color commentary without having to embed it in individual persona prompts.

Previously, match-specific context had to be manually added to a single bot's persona prompt (e.g. the ManU Homer bot). Match notes make this context available to every bot commenting on that match, and provide a dedicated form for quick input while watching.

---

## Data Model

### `MatchNotes` (in `matches/models.py`)

Inherits `BaseModel`. One-to-one relationship with the Match model.

| Field | Type | Notes |
|-------|------|-------|
| `match` | OneToOneField(Match) | `related_name="notes"` |
| `body` | TextField | Free-form match observations |

---

## Admin Interface

### Inline panel on match detail page

A collapsible panel appears above the two-column layout on the match detail page, visible only to superusers. Features:

- HTMX-powered form — saves via POST to `/match/<id>/notes/` without page reload
- Success banner confirms save with context about how notes are used
- Pre-populated textarea when notes already exist, with "last saved" timestamp
- Placeholder text guides input: "Key moments, goalscorers, drama, red cards, VAR incidents..."

### Django admin

`MatchNotesAdmin` registered as a fallback with list display showing match, created_at, and updated_at.

---

## Bot Prompt Injection

### Where: `bots/comment_service.py` — `_build_user_prompt()`

Notes are injected into the **user prompt** (not the system/persona prompt) for two trigger types:

| Trigger | Injected? | Rationale |
|---------|-----------|-----------|
| `POST_MATCH` | Yes | Bots react to what happened — notes add color |
| `REPLY` | Yes | Bots replying to comments benefit from match context |
| `PRE_MATCH` | No | Match hasn't happened yet |
| `POST_BET` | No | Bet reaction doesn't need play-by-play detail |

### Prompt format

Notes appear after H2H/form stats, before the trigger-specific instruction:

```
Match: Arsenal vs Chelsea
Kickoff: Sat 15 Mar, 15:00 UTC | Matchday 28
...
H2H (last 10): Arsenal 4W - 3D - Chelsea 3W

Match notes (from a real viewer):
- Bruno Fernandes scored a screamer from 30 yards
- Red card to Maguire in the 80th minute
- 9 minutes of stoppage time

Final score: Arsenal 2 - 1 Chelsea
Your bet: Home Win @ 2.10 — WON
...
```

Empty or whitespace-only notes are silently skipped.

---

## URL Routes

| URL | View | Method | Auth |
|-----|------|--------|------|
| `/match/<id>/notes/` | `MatchNotesView` | POST | Superuser only |

---

## Files Changed

| File | Change |
|------|--------|
| `matches/models.py` | Add `MatchNotes` model |
| `matches/forms.py` | New file — `MatchNotesForm` (ModelForm) |
| `matches/views.py` | Add `MatchNotesView`, add notes form to `MatchDetailView` context |
| `matches/urls.py` | Add `/match/<id>/notes/` route |
| `matches/admin.py` | Register `MatchNotesAdmin` |
| `matches/templates/matches/match_detail.html` | Include notes panel for superusers |
| `matches/templates/matches/partials/match_notes_panel.html` | New partial — HTMX form |
| `bots/comment_service.py` | Inject notes into `_build_user_prompt()` for POST_MATCH and REPLY |
| `matches/migrations/0004_match_notes.py` | Migration for `MatchNotes` |
| `matches/tests/factories.py` | Add `MatchNotesFactory` |
| `matches/tests/test_match_notes.py` | 18 tests — model, views, prompt injection |

---

## Tests

18 tests covering:

- **Model**: str representation, OneToOne constraint, reverse relation
- **Detail view access**: superuser sees form, regular user and anonymous do not, existing notes pre-populate
- **Save view**: create, update, regular user 403, anonymous redirect, success message in response
- **Prompt injection**: POST_MATCH includes notes, REPLY includes notes, PRE_MATCH excludes, POST_BET excludes, no notes = no section, empty body excluded
