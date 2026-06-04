# MTProto VDS Instance

FastAPI-сервис для управления пользователями MTProto-прокси на базе [telemt](https://github.com/nickvnlk/telemt). Принимает запросы от Django-бэкенда и транслирует их в telemt API — создание, ротация секретов и удаление ключей.

## Быстрый старт

```bash
# Зависимости
uv sync

# Запуск
uv run uvicorn src.app:app --host 0.0.0.0 --port 8000

# Docker
docker-compose up --build
```

## API

| Метод    | Путь         | Описание                   |
|----------|--------------|----------------------------|
| `POST`   | `/api/users` | Создать пользователя       |
| `PATCH`  | `/api/users` | Перевыпустить секрет       |
| `DELETE` | `/api/users` | Удалить пользователей      |

## Тесты

```bash
uv run pytest                    # все тесты
uv run pytest src/tests/unit/    # unit (мокированный telemt API)
uv run pytest src/tests/e2e/     # e2e (требуются запущенные контейнеры)
```

## Документация

- [Бизнес-цель](docs/BUSINESS.md) — что продаём, сценарии использования
- [Архитектура](docs/ARCHITECTURE.md) — место в системе, стек, структура проекта
- [Контракты API](docs/CONTRACTS.md) — эндпоинты, запросы, ответы
- [Telemt](docs/TELEMT.md) — описание прокси-сервера и его API
