# Contributing

## Local Setup

This project is developed with Docker Compose. Python and service commands
should run inside the `web` container.

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Add your API keys to `.env`.

3. Build and start the stack:

```bash
docker compose up -d --build
```

4. Run database setup:

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web python manage.py seed_epl
```

## Development Commands

Run Django management commands through Docker:

```bash
docker compose run --rm web python manage.py <command>
```

Run the test suite:

```bash
docker compose run --rm web pytest
docker compose run --rm web pytest --cov --cov-report=term-missing
```

Run the linter:

```bash
docker compose run --rm web ruff check .
```

If dependencies change, rebuild the image before rerunning commands:

```bash
docker compose build web
```

## Pull Requests

- Keep changes scoped to one concern.
- Add or update tests for behavior changes.
- Run `ruff check .` and the relevant pytest commands before opening a PR.
- Document new environment variables, commands, or operational steps.

## Reporting Issues

When reporting a bug, include the expected behavior, the actual behavior,
reproduction steps, and any relevant logs or screenshots.
