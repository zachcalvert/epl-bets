# Phase 29: Remove Under the Hood Panels

## Overview

Removed the "Under the Hood" transparency panels from the dashboard, match detail, and odds board pages, along with the entire `website/transparency.py` event-recording infrastructure that backed them.

---

## Decision

The Under the Hood panels were originally added when the app was a pure demo, intended to expose real-time machinery (WebSocket events, HTMX polling, Celery tasks) to anyone evaluating the tech stack. As the app grew into a fully-featured betting platform with real users in mind, those panels became clutter — the real-time behavior is now self-evident through actual product use, and the panels served no purpose for a genuine user.

This was a deliberate shift in the app's identity: from demo to product.

---

## What Was Removed

- `website/transparency.py` — event recording/retrieval module (`record_event`, `get_events`, scope helpers)
- Three `<details>` Under the Hood blocks from `dashboard.html`, `match_detail.html`, and `odds_board.html`
- Three partial templates: `dashboard_under_the_hood.html`, `match_under_the_hood.html`, `odds_board_under_the_hood.html`
- Three partial views and URL routes: `dashboard_under_the_hood`, `match_under_the_hood`, `odds_under_the_hood`
- All `record_event()` call sites in views and Celery tasks
- `website/tests/test_transparency.py` and related test assertions across view/task test files
