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
Ansible как бинарный systemd-сервис на хосте. Telemt самостоятельно занимает
порт `443` и использует внешний TLS-mask `beatvault.ru`.

В production Telemt API привязан к `172.17.0.1:9091`; Docker whitelist —
`172.16.0.0/12`, healthcheck whitelist — host default IPv4 `/32`.
Публичный порт `9091` не должен давать HTTP-ответ. Checkout приложения хранится
в `/opt/mtproto-app`, изменяемый конфиг — в `/opt/mtproto/telemt/telemt.toml`;
канонический swap — `/swapfile` размером 2048 MiB, umask файлов Telemt — `0027`.

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
