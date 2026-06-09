# Remove TOML dependency from API service

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix `Is a directory (os error 21)` on fresh deploy by removing the toml file coupling between api and telemt services, and making telemt auto-create its config from example.

**Architecture:** The api service no longer reads/writes `telemt.toml` — it communicates with telemt exclusively via HTTP. The telemt container's entrypoint copies `telemt.example.toml` to `telemt.toml` if the latter doesn't exist, so fresh clones work out of the box.

**Tech Stack:** Docker Compose, FastAPI, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Move | `telemt.example.toml` → `telemt/telemt.example.toml` | Default telemt config template (tracked in git) |
| Modify | `docker-compose.yaml` | Remove api toml volume; update telemt command |
| Modify | `docker-compose.local.yaml` | Same changes as docker-compose.yaml |
| Modify | `Dockerfile` | Remove `COPY telemt.toml ./` |
| Modify | `src/app.py` | Remove `prepare_toml_file()`, simplify lifespan |
| Modify | `src/config.py` | Remove `TELEMT_TOML_FILENAME`, `TELEMT_TOML_PATH` |
| Modify | `.env.example` | Remove `TELEMT_TOML_FILENAME` |
| Modify | `.env` | Remove `TELEMT_TOML_FILENAME` |
| Modify | `src/tests/unit/conftest.py` | Remove `prepare_toml_file` fixture, simplify `http_client` |
| Delete | `src/tests/unit/utils.py` | Dead code (`get_toml_file_data` unused) |
| Delete | `telemt.toml` | Was only needed for Dockerfile COPY — no longer needed |
| Modify | `pyproject.toml` | Remove `aiofiles`, `toml` dependencies |
| Modify | `.gitignore` | Remove `telemt.test.toml` line (stale) |

---

### Task 1: Move example config into telemt/ directory

**Files:**
- Move: `telemt.example.toml` → `telemt/telemt.example.toml`

- [ ] **Step 1: Move the file**

```bash
git mv telemt.example.toml telemt/telemt.example.toml
```

- [ ] **Step 2: Verify directory now contains both files**

```bash
ls telemt/
```

Expected: `telemt.example.toml` and `telemt.toml` (the latter is your local gitignored copy).

- [ ] **Step 3: Commit**

```bash
git add telemt/telemt.example.toml
git commit -m "chore: move telemt.example.toml into telemt/ directory"
```

---

### Task 2: Update telemt service in docker-compose files

**Files:**
- Modify: `docker-compose.yaml:10` (telemt command)
- Modify: `docker-compose.local.yaml:10` (telemt command)

- [ ] **Step 1: Update docker-compose.yaml telemt command**

Replace in `docker-compose.yaml`:
```yaml
    command: /usr/local/bin/telemt /etc/telemt/telemt.toml
```
with:
```yaml
    command: >
      sh -c '[ -f /etc/telemt/telemt.toml ] ||
      cp /etc/telemt/telemt.example.toml /etc/telemt/telemt.toml &&
      exec /usr/local/bin/telemt /etc/telemt/telemt.toml'
```

- [ ] **Step 2: Apply the same change to docker-compose.local.yaml**

Replace the same `command:` line in `docker-compose.local.yaml` with the identical shell wrapper.

- [ ] **Step 3: Remove toml volume from api service in both files**

In `docker-compose.yaml`, remove this line from `api.volumes`:
```yaml
      - ./telemt/telemt.toml:/app/telemt/telemt.toml
```

In `docker-compose.local.yaml`, remove the same line.

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yaml docker-compose.local.yaml
git commit -m "fix: auto-create telemt config from example on fresh deploy"
```

---

### Task 3: Clean up Dockerfile

**Files:**
- Modify: `Dockerfile:11`

- [ ] **Step 1: Remove the COPY telemt.toml line**

Remove this line from `Dockerfile`:
```dockerfile
COPY telemt.toml ./
```

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "chore: remove unused telemt.toml COPY from Dockerfile"
```

---

### Task 4: Remove toml logic from FastAPI app

**Files:**
- Modify: `src/app.py`
- Modify: `src/config.py`

- [ ] **Step 1: Simplify src/app.py**

Replace the entire contents of `src/app.py` with:

```python
from src.api import router

from fastapi import FastAPI

app = FastAPI(title="MTProto Management API")

app.include_router(router)
```

This removes: `prepare_toml_file()`, the lifespan, and imports of `aiofiles`, `toml`, `asynccontextmanager`, `config`.

- [ ] **Step 2: Clean up src/config.py**

Remove these two lines from `src/config.py`:

```python
TELEMT_TOML_FILENAME = os.getenv("TELEMT_TOML_FILENAME", "telemt.toml")
TELEMT_TOML_PATH = os.path.join(BASE_DIR / TELEMT_TOML_FILENAME)
```

Also remove `import os` and `import pathlib` if they are only used for these lines. The remaining config should be:

```python
import os

TELEMT_API_ROOT = os.getenv("TELEMT_API_ROOT", "http://172.17.0.1:9091/v1")
TLS_DOMAIN = os.getenv("TLS_DOMAIN", "petrovich.ru")
```

- [ ] **Step 3: Run tests to verify nothing breaks**

```bash
uv run pytest src/tests/unit/ -v
```

Expected: tests should still pass (the `prepare_toml_file` fixture in conftest.py is independent from `src/app.py`'s function).

- [ ] **Step 4: Commit**

```bash
git add src/app.py src/config.py
git commit -m "refactor: remove toml file management from api service"
```

---

### Task 5: Clean up tests

**Files:**
- Modify: `src/tests/unit/conftest.py`
- Delete: `src/tests/unit/utils.py`

- [ ] **Step 1: Simplify conftest.py**

Replace the entire contents of `src/tests/unit/conftest.py` with:

```python
import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app


@pytest.fixture(autouse=True)
def _set_telemt_api_root(monkeypatch):
    monkeypatch.setattr(config, "TELEMT_API_ROOT", "http://172.17.0.1:9091/v1")


@pytest.fixture
def http_client() -> TestClient:
    return TestClient(app=app, base_url="http://127.0.0.1:8000/api")
```

This removes: `prepare_toml_file` fixture, `toml` import, `os` import.

- [ ] **Step 2: Delete utils.py**

```bash
rm src/tests/unit/utils.py
```

The function `get_toml_file_data()` is not imported anywhere in the test files.

- [ ] **Step 3: Run all unit tests**

```bash
uv run pytest src/tests/unit/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add src/tests/unit/conftest.py
git rm src/tests/unit/utils.py
git commit -m "refactor: remove toml fixtures from unit tests"
```

---

### Task 6: Remove unused dependencies

**Files:**
- Modify: `pyproject.toml:7-8,11`

- [ ] **Step 1: Remove aiofiles and toml from pyproject.toml**

In `pyproject.toml`, change the dependencies list from:
```toml
dependencies = [
    "aiofiles>=25.1.0",
    "fastapi>=0.131.0",
    "httpx>=0.28.1",
    "toml>=0.10.2",
    "uvicorn>=0.41.0",
]
```
to:
```toml
dependencies = [
    "fastapi>=0.131.0",
    "httpx>=0.28.1",
    "uvicorn>=0.41.0",
]
```

- [ ] **Step 2: Sync the lockfile**

```bash
uv sync
```

- [ ] **Step 3: Run tests to confirm nothing depends on removed packages**

```bash
uv run pytest src/tests/unit/ -v
```

Expected: all tests pass.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml uv.lock
git commit -m "chore: remove unused aiofiles and toml dependencies"
```

---

### Task 7: Clean up env files, gitignore, and stale root toml

**Files:**
- Modify: `.env`
- Modify: `.env.example`
- Modify: `.gitignore`
- Delete: `telemt.toml` (root)

- [ ] **Step 1: Remove TELEMT_TOML_FILENAME from .env**

Remove this line from `.env`:
```
TELEMT_TOML_FILENAME=./telemt/telemt.toml
```

- [ ] **Step 2: Remove TELEMT_TOML_FILENAME from .env.example**

Remove this line from `.env.example`:
```
TELEMT_TOML_FILENAME=./telemt/telemt.toml
```

- [ ] **Step 3: Clean up .gitignore**

Remove this line from `.gitignore`:
```
telemt.test.toml
```

The `telemt/telemt.toml` line stays (the runtime config remains gitignored).

- [ ] **Step 4: Delete the root telemt.toml**

```bash
rm telemt.toml
```

This file was only used by `COPY telemt.toml ./` in the Dockerfile, which was removed in Task 3.

- [ ] **Step 5: Commit**

```bash
git add .env.example .gitignore
git rm telemt.toml
git commit -m "chore: clean up stale toml references and env vars"
```

Note: `.env` is gitignored, so it doesn't need `git add`.

---

### Task 8: Update documentation

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/ARCHITECTURE.md` (if it mentions toml/lifespan)

- [ ] **Step 1: Update CLAUDE.md**

Remove `TELEMT_TOML_FILENAME` from the Environment Variables table. The table should be:

```markdown
| Variable | Purpose | Default |
|---|---|---|
| `TELEMT_API_ROOT` | Base URL for telemt HTTP API | — |
| `TLS_DOMAIN` | TLS domain returned in responses | `"petrovich.ru"` |
```

- [ ] **Step 2: Check docs/ARCHITECTURE.md for stale references**

Read the file and update any mentions of the toml lifespan, `prepare_toml_file`, or direct file access to telemt config. If none exist, skip.

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md docs/
git commit -m "docs: remove stale toml references"
```

---

### Task 9: Final verification

- [ ] **Step 1: Run full test suite**

```bash
uv run pytest -v
```

Expected: all unit tests pass, e2e tests skip (containers not running).

- [ ] **Step 2: Verify Docker build succeeds**

```bash
docker compose build api
```

Expected: build completes without errors.

- [ ] **Step 3: Verify clean state**

```bash
grep -r "TELEMT_TOML" src/
grep -r "aiofiles" src/
grep -r "import toml" src/
```

Expected: no matches for any of these.
