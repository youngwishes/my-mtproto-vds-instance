# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

FastAPI-сервис для управления пользователями MTProto-прокси (telemt). Является конечным звеном в цепочке: Telegram Bot → Django Backend → **этот сервис** → telemt API.

## Common Commands

```bash
# Install dependencies
uv sync

# Run locally
uv run uvicorn src.app:app --host 0.0.0.0 --port 8080

# Run all tests
uv run pytest

# Run unit tests
uv run pytest src/tests/unit/

# Run e2e tests (requires running containers)
uv run pytest src/tests/e2e/

# Lint
ruff check src/

# Build and run with Docker
docker-compose up --build                                   # продакшн
docker-compose -f docker-compose.local.yaml up --build     # локально
```

## Architecture

Подробная документация — в `docs/` (BUSINESS.md, ARCHITECTURE.md, CONTRACTS.md, TELEMT.md). Точка входа — `src/app.py`.

### API

RESTful API с единственным ресурсом `/api/users`:
- **POST** — создание пользователя
- **GET** `/api/users/{username}` — проверка наличия пользователя в конфиге telemt (200/404)
- **PATCH** — ротация секрета (перевыпуск ссылки)
- **DELETE** — массовое удаление пользователей

Роуты: `src/api/routes/users.py`. Схема ответа: `src/api/schemas/add_new_user_schema.py`.

### Service layer

Сервисы — frozen dataclasses с `__call__`. Делают async HTTP-запросы к telemt API через `httpx.AsyncClient`. Инстанцируются inline в хендлерах.

- `AddUserService` — регистрация пользователя (лимит 3 IP)
- `GetUserService` — проверка наличия пользователя в конфиге telemt (возвращает username + tg://-ссылку)
- `RotateSecretService` — перевыпуск секрета при компрометации ссылки
- `RemoveUserService` — массовая очистка протухших ключей (celery-задача, ежедневно)

## Project Structure

```
deploy/               # Ansible для деплоя на VDS
├── playbook.yml
├── inventory.ini
└── ansible.cfg
telemt/               # Конфиг telemt-процесса (из telemt.example.toml)
└── telemt.toml
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
│   ├── get_user_service.py
│   ├── rotate_secret_service.py
│   └── remove_user_service.py
└── tests/
    ├── unit/          # мокированный telemt API (pytest-httpx)
    └── e2e/           # реальные запросы к контейнерам, skip если не подняты
```

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `TELEMT_API_ROOT` | Base URL for telemt HTTP API | `"http://telemt:9091/v1"` |
| `TLS_DOMAIN` | TLS domain returned in responses | `"petrovich.ru"` |
| `E2E_BASE_URL` | Base URL for e2e tests | `"http://127.0.0.1:8080/api"` |

## Rules

1. **Документация** — после любых изменений в коде обновляй соответствующие файлы в `docs/`, `CLAUDE.md` и `README.md`, если изменения затрагивают описанное в них.
2. **Тесты** — всегда прогоняй и unit, и e2e тесты (`uv run pytest`). Если e2e тесты скипаются — подними контейнеры сам (`docker-compose -f docker-compose.local.yaml up --build -d`), дождись их готовности и прогони e2e перед тем как считать задачу завершённой. Спрашивать разрешение на подъём контейнеров не нужно.
3. **Git** — можно делать `git commit` самостоятельно. `git push` — только по явной просьбе пользователя.

## Local Testing

Для ручного тестирования и e2e-тестов нужны запущенные контейнеры.

```bash
# Поднять локально (telemt + api)
docker-compose -f docker-compose.local.yaml up --build -d

# Остановить
docker-compose -f docker-compose.local.yaml down

# Проверить список пользователей telemt напрямую
curl -s http://127.0.0.1:9091/v1/users | python3 -m json.tool

# POST — создать пользователя
curl -s -X POST http://127.0.0.1:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"username":"test-user","secret":"aaaabbbbccccddddaaaabbbbccccdddd"}'

# GET — проверить наличие пользователя (200/404)
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8080/api/users/test-user

# PATCH — ротация секрета
curl -s -X PATCH http://127.0.0.1:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"username":"test-user","secret":"11112222333344441111222233334444"}'

# DELETE — массовое удаление
curl -s -X DELETE http://127.0.0.1:8080/api/users \
  -H "Content-Type: application/json" \
  -d '{"usernames":["test-user"]}'
```

## Testing Notes

- Unit-тесты мокируют исходящий HTTP через `pytest-httpx`.
- E2e-тесты отправляют реальные запросы на `http://127.0.0.1:8080`, скипаются если контейнеры не подняты.
- Пакетный менеджер — `uv`, lockfile — `uv.lock`.
