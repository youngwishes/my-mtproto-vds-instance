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

**telemt** — MTProto-прокси сервер. Запускается рядом в Docker, предоставляет HTTP API для управления пользователями.

## Стек

- **FastAPI** — HTTP-сервер
- **httpx** — асинхронный HTTP-клиент для запросов к telemt API
- **Docker Compose** — оркестрация: этот сервис + telemt в одной сети

## Структура проекта

```
src/
├── app.py                 # FastAPI-приложение, lifespan, подключение роутера
├── config.py              # Переменные окружения
├── api/
│   ├── routes/
│   │   └── users.py       # Эндпоинты /api/users
│   └── schemas/
│       └── add_new_user_schema.py  # Pydantic-модель ответа
├── services/
│   ├── add_user_service.py
│   ├── rotate_secret_service.py
│   └── remove_user_service.py
└── tests/
    ├── unit/              # Тесты с мокированным telemt API
    └── e2e/               # Тесты с реальными контейнерами
```

## Деплой

Сервис деплоится на VDS как пара Docker-контейнеров. Каждый VDS-инстанс — самостоятельная нода с собственным `NODE_NUMBER`.

```yaml
services:
  api:     # этот сервис (порт 8000)
  telemt:  # MTProto-прокси (порт 443)
```
