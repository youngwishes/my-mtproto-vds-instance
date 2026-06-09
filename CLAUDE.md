# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-сервис для управления пользователями MTProto-прокси (telemt). Является конечным звеном в цепочке: Telegram Bot → Django Backend → **этот сервис** → telemt API.

## Common Commands

```bash
# Install dependencies
uv sync

# Run locally
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000

# Run all tests
uv run pytest

# Run unit tests
uv run pytest src/tests/unit/

# Run e2e tests (requires running containers)
uv run pytest src/tests/e2e/

# Lint
ruff check src/

# Build and run with Docker
docker-compose up --build
```

## Architecture

Подробная документация — в `docs/` (BUSINESS.md, ARCHITECTURE.md, CONTRACTS.md, TELEMT.md). Точка входа — `src/app.py`.

### API

RESTful API с единственным ресурсом `/api/users`:
- **POST** — создание пользователя
- **PATCH** — ротация секрета (перевыпуск ссылки)
- **DELETE** — массовое удаление пользователей

Роуты: `src/api/routes/users.py`. Схема ответа: `src/api/schemas/add_new_user_schema.py`.

### Service layer

Сервисы — frozen dataclasses с `__call__`. Делают async HTTP-запросы к telemt API через `httpx.AsyncClient`. Инстанцируются inline в хендлерах.

- `AddUserService` — регистрация пользователя (лимит 3 IP)
- `RotateSecretService` — перевыпуск секрета при компрометации ссылки
- `RemoveUserService` — массовая очистка протухших ключей (celery-задача, ежедневно)

## Project Structure

```
src/
├── app.py
├── config.py
├── api/
│   ├── routes/
│   │   └── users.py
│   └── schemas/
│       └── add_new_user_schema.py
├── services/
│   ├── add_user_service.py
│   ├── rotate_secret_service.py
│   └── remove_user_service.py
└── tests/
    ├── unit/          # мокированный telemt API (pytest-httpx)
    └── e2e/           # реальные запросы к контейнерам, skip если не подняты
```

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `TELEMT_API_ROOT` | Base URL for telemt HTTP API | — |
| `TLS_DOMAIN` | TLS domain returned in responses | `"petrovich.ru"` |

## Rules

1. **Документация** — после любых изменений в коде обновляй соответствующие файлы в `docs/`, `CLAUDE.md` и `README.md`, если изменения затрагивают описанное в них.
2. **Тесты** — всегда прогоняй и unit, и e2e тесты (`uv run pytest`). Если e2e тесты скипаются — попроси пользователя поднять контейнеры (`docker-compose up --build`) и дождись подтверждения перед тем как считать задачу завершённой.
3. **Git** — никогда не делай `git commit` и `git push`. Коммиты и пуши выполняет только пользователь.

## Testing Notes

- Unit-тесты мокируют исходящий HTTP через `pytest-httpx`.
- E2e-тесты отправляют реальные запросы на `http://127.0.0.1:8000`, скипаются если контейнеры не подняты.
- Пакетный менеджер — `uv`, lockfile — `uv.lock`.
