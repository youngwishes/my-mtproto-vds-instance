# MTProto VDS Instance

FastAPI-сервис для управления пользователями MTProto-прокси на базе [telemt](https://github.com/telemt/telemt). Принимает запросы от Django-бэкенда и транслирует их в telemt API — создание, ротация секретов и удаление ключей.

## Быстрый старт

```bash
# Зависимости
uv sync

# Запуск
uv run uvicorn src.app:app --host 0.0.0.0 --port 8080

# Локальный стек FastAPI + Telemt 3.4.25
docker compose -f docker-compose.local.yaml up --build
```

В production FastAPI работает в Docker, а Telemt `3.4.25` устанавливается
Ansible как бинарный systemd-сервис на хосте. Обязательный Caddy предоставляет
локальный HTTPS endpoint для self-steal-маскировки Telemt.

## API

| Метод    | Путь                    | Описание                          |
|----------|-------------------------|-----------------------------------|
| `POST`   | `/api/users`            | Создать пользователя              |
| `GET`    | `/api/users/{username}` | Проверить наличие пользователя    |
| `PATCH`  | `/api/users`            | Перевыпустить секрет              |
| `DELETE` | `/api/users`            | Удалить пользователей             |

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
- [Деплой](docs/DEPLOY.md) — автоматизированный деплой через Ansible
