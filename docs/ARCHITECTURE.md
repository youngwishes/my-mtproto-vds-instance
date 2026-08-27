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
- **Ansible** — установка Telemt и последовательное обновление серверов

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
telemt.service 172.17.0.1:9091 ──► MTProto :443 ── fallback ──► beatvault.ru:443
```

Публичный порт `443` принадлежит Telemt. Единственный TLS-домен —
`beatvault.ru`; Telemt использует его же как неявный внешний `mask_host`.
Telemt API привязан к `172.17.0.1:9091`: Docker whitelist — `172.16.0.0/12`,
healthcheck whitelist — host default IPv4 `/32`. Публичный порт
`9091` не должен давать HTTP-ответ.

Docker Compose добавляет `host.docker.internal` через `host-gateway`. Для
локальных e2e-тестов отдельный `docker-compose.local.yaml` по-прежнему запускает
оба сервиса в контейнерах. Контейнер Telemt использует обычный production target
без netfilter-пакетов и без `NET_ADMIN`; встроенный SYN-limiter отключён тем же
example-конфигом, что используется при чистой установке на сервер. Одноразовый
setup-контейнер также точечно мигрирует уже существующий локальный
`telemt.toml`.

Роль хранит checkout приложения в `/opt/mtproto-app`, а изменяемый конфиг — в
`/opt/mtproto/telemt/telemt.toml`. Канонический swap — `/swapfile` размером
2048 MiB. Unit Telemt задаёт umask `0027` для файлов, создаваемых Telemt.
