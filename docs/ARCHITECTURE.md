# Архитектура

## Место в системе

Этот репозиторий — **конечное звено** в цепочке обработки запросов. Он управляет пользователями на конкретном VDS-инстансе MTProto-прокси.

```
Пользователь
    │
    ▼
Telegram Bot ─── (my-mtproto-backend)
    │
    ▼
Django Backend ── (my-mtproto-backend)
    │
    ▼
FastAPI сервис ── (этот репозиторий)  ◄── celery-задача очистки
    │
    ▼
telemt (MTProto-прокси)
```

**my-mtproto-backend** — Django-приложение с Telegram-ботом и бизнес-логикой (биллинг, управление подписками, формирование ссылок). Живёт в отдельном репозитории.

**Этот сервис** — тонкая прослойка между бэкендом и telemt. Принимает команды (добавить/обновить/удалить пользователя) и транслирует их в HTTP API telemt.

**telemt** — MTProto-прокси сервер. Запускается на том же VDS как бинарный
systemd-сервис и предоставляет HTTP API для управления пользователями.

## Стек

- **FastAPI** — HTTP-сервер
- **httpx** — асинхронный HTTP-клиент для запросов к telemt API
- **Docker Compose** — запуск FastAPI-контейнера
- **systemd** — запуск бинарника Telemt 3.4.25 на хосте
- **Ansible** — установка и последовательное обновление обоих сервисов

## Структура проекта

```
src/
├── app.py                 # FastAPI-приложение, подключение роутера
├── config.py              # Переменные окружения
├── api/
│   ├── routes/
│   │   └── users.py       # Эндпоинты /api/users
│   └── schemas/
│       └── add_new_user_schema.py  # Pydantic-модель ответа
├── services/
│   ├── add_user_service.py
│   ├── get_user_service.py
│   ├── rotate_secret_service.py
│   └── remove_user_service.py
└── tests/
    ├── unit/              # Тесты с мокированным telemt API
    └── e2e/               # Тесты с реальными контейнерами
```

## Деплой

FastAPI деплоится в Docker, а Telemt запускается непосредственно на хосте:

```text
FastAPI container :8080
    │ http://host.docker.internal:9091/v1
    ▼
telemt.service :9091 ──► MTProto :443
```

Docker Compose добавляет `host.docker.internal` через `host-gateway`. Для
локальных e2e-тестов отдельный `docker-compose.local.yaml` по-прежнему запускает
оба сервиса в контейнерах.
