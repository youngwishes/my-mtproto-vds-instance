# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI service for managing MTProto proxy (telemt) users. Exposes two API versions — v1 manipulates a local TOML config file directly, v2 delegates to the telemt HTTP management API.

## Common Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run locally
uvicorn src.app:app --host 0.0.0.0 --port 8000

# Run all tests
pytest

# Run tests for a specific version
pytest src/tests/v1/
pytest src/tests/v2/

# Run a single test file
pytest src/tests/v2/test_add_user_view.py

# Lint (ruff is used, cache present)
ruff check src/

# Build and run with Docker
docker-compose up
docker-compose -f docker-compose.local.yaml up  # local dev variant
```

## Architecture

### Two API versions with different backends

**V1** (`src/api/routes/v1/`, `src/services/v1/`) — Reads/writes the telemt TOML config file on disk via `aiofiles`. Changes take effect after the proxy service reloads the file.

**V2** (`src/api/routes/v2/`, `src/services/v2/`) — Makes async HTTP calls to the telemt management API (base URL set via `TELEMT_API_ROOT` env var). Handles 409 conflicts (user already exists) by deleting and recreating the user.

### Service layer pattern

All services are **frozen dataclasses** (`@dataclass(frozen=True, kw_only=True, slots=True)`) with a `__call__` method. They are instantiated inline in route handlers, not via FastAPI dependency injection.

### Startup / lifespan (`src/app.py`)

On startup the app reads `telemt.toml` (path from `TELEMT_TOML_PATH` env var) and seeds missing top-level keys with defaults before any request is served.

### Response schema

Both versions return `AddNewUserResponse` (defined in `src/api/schemas/add_new_user_schema.py`):
```python
key: str        # the generated secret/password
tls_domain: str # from TLS_DOMAIN env var
node_number: str # from NODE_NUMBER env var
```

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `TELEMT_TOML_FILENAME` | Filename of the telemt config | — |
| `TELEMT_API_ROOT` | Base URL for telemt HTTP API (v2) | — |
| `NODE_NUMBER` | Node identifier returned in responses | — |
| `TLS_DOMAIN` | TLS domain returned in responses | `"petrovich.ru"` |

## Testing Notes

- V1 tests use a real temporary TOML file prepared in `conftest.py` fixtures.
- V2 tests mock outbound HTTP with `pytest-httpx` (`httpx.AsyncClient` is patched).
- The test client is created with `AsyncClient(transport=ASGITransport(app=app), base_url="http://test")`.
