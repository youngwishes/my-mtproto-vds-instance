# Telemt SYN limit for Docker

`telemt-syn-limit` ограничивает частоту новых TCP-подключений к опубликованному
Docker-порту Telemt `443`. Механизм снижает влияние шквала параллельных
подключений и оставляет существующие TCP-соединения без изменений.

## Текущее состояние

Механизм развёрнут как штатная часть dev- и production-конфигурации. Полные
playbooks устанавливают приложение, запускают Docker Compose и затем включают
limiter:

- `deploy/playbook-dev.yml` — группа `mtproto_dev`;
- `deploy/playbook-prod.yml` — группа `mtproto_prod`, по одному серверу за раз.

Роль `telemt_syn_limit` устанавливает и включает
`telemt-syn-limit.service`. Отдельные playbooks `telemt-syn-limit.yml` и
`telemt-syn-limit-prod.yml` позволяют обновить только limiter без перезапуска
приложения.

Рабочий профиль:

- порт: `443/tcp`;
- лимит: `54/minute` для каждого source IPv4;
- burst `5`;
- превышение отклоняется через `tcp-reset`.

## Принцип работы

Опубликованный Docker-трафик проходит через `FORWARD` и `DOCKER-USER`, а не
через host `INPUT`. Сервис создаёт цепочку `TELEMT_SYN_LIMIT` и подключает её
первым правилом `DOCKER-USER` для входящих TCP SYN на порт `443`.

Модуль iptables `hashlimit` учитывает SYN отдельно для каждого source IPv4.
Пакеты в пределах лимита получают `RETURN` и продолжают стандартную обработку
Docker. Пакеты сверх лимита получают TCP RST. Остальные TCP-пакеты и уже
установленные соединения limiter не затрагивает.

Systemd unit имеет тип `oneshot` с `RemainAfterExit=yes` и привязан к
`docker.service`. При запуске он идемпотентно пересоздаёт собственные правила,
при остановке удаляет переход из `DOCKER-USER` и цепочку
`TELEMT_SYN_LIMIT`.

## Проверка

```bash
systemctl is-enabled telemt-syn-limit
systemctl is-active telemt-syn-limit
iptables -vnL DOCKER-USER --line-numbers
iptables -vnL TELEMT_SYN_LIMIT --line-numbers
```

Ожидаемое состояние:

- сервис `enabled` и `active`;
- в `DOCKER-USER` ровно один переход в `TELEMT_SYN_LIMIT` для SYN на `443`;
- первое правило цепочки содержит `54/minute`, burst `5` и `RETURN`;
- второе правило использует `REJECT` с `tcp-reset`.

Счётчики первого правила показывают пропущенные SYN, второго — отклонённые.
Они накапливаются с момента создания цепочки и не сбрасываются при обычном
перезапуске Compose.

## Управление и rollback

Временно удалить limiter:

```bash
systemctl stop telemt-syn-limit
```

Вернуть limiter:

```bash
systemctl start telemt-syn-limit
```

Отключить limiter на production-хосте через Ansible:

```bash
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit-rollback.yml --limit <host>
```

Rollback останавливает и отключает только `telemt-syn-limit.service`. Telemt,
его конфигурация и контейнеры не изменяются.

## Ограничение CGNAT

Лимит применяется по source IPv4. Несколько клиентов мобильного оператора могут
находиться за одним carrier-grade NAT и совместно использовать `54/minute`.
Изменять rate или burst следует только после проверки времени подключения,
счётчиков RETURN/REJECT и пользовательских жалоб через мобильные сети.
