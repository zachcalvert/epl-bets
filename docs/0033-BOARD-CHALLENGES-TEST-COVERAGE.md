# Phase 33: Test Coverage — Board & Challenges

## Status: Planned

**Depends on:** Phase 32 (Message Board) — complete

## Overview

The `board` and `challenges` apps are tracked in `coverage.source` but excluded from `testpaths`,
meaning they currently drag overall coverage well below the 96% threshold. This phase closes
that gap by writing a full pytest suite for both apps.

## Scope

### `board` app
- `test_models.py` — Post, Reply, vote logic, moderation flags
- `test_views.py` — CRUD views, threaded replies, superuser hide/restore
- `test_tasks.py` — Bot auto-posting Celery tasks
- `test_consumers.py` (if applicable) — Any WS consumers

### `challenges` app
- `test_models.py` — ChallengeTemplate, Challenge, UserChallenge state machine
- `test_engine.py` — Criteria evaluation logic (bet count, streak, etc.)
- `test_views.py` — Challenge list, progress, claim views
- `test_tasks.py` — Celery tasks (evaluate challenges, award rewards)

## Steps

1. Add `board` and `challenges` to `testpaths` in `pyproject.toml`
2. Write factories for both apps
3. Write test files per scope above
4. Target ≥ 96% combined coverage (matching project threshold)
5. Confirm full `pytest --cov` run passes the threshold

## Notes

- `challenges/engine.py` is currently at 23% — highest-value target
- `challenges/tasks.py` and `challenges/views.py` are at 0% / 34%
- Board had 30 view tests written during Phase 32 — check if any still exist
  and can be ported rather than rewritten
