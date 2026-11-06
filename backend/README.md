# Librarium backend

FastAPI + PostgreSQL backend of the Little Dragon library. Full documentation (setup, auth model,
reservation rules, API list, troubleshooting) is in the [root README](../README.md).

Quick reference (run from the repository root):

```bash
docker compose up -d --build
```

```bash
docker compose --profile dev run --rm backend-dev pytest
```

```bash
docker compose --profile dev run --rm backend-dev sh -c "ruff format --check . && ruff check . && mypy"
```

```bash
docker compose --profile dev run --rm backend-dev alembic upgrade head
```

```bash
docker compose run --rm -e SEED_ADMIN_PASSWORD='choose-a-long-password' backend python -m app.cli seed --demo-books
```

```bash
docker compose --profile dev run --rm --no-deps backend-dev python -m app.cli export-openapi openapi.json
```
