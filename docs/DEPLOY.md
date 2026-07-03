# Деплой

В репозитории есть два разных контура Ansible:

- `deploy/playbook.yml` — первоначальное развёртывание нового пустого VDS;
- отдельные playbooks `telemt-syn-limit*.yml` — установка и rollback SYN limiter
  на уже работающих хостах.

Не запускайте `deploy/playbook.yml` для обновления Telemt или SYN limiter на
существующем production. Полный playbook обновляет репозиторий, собирает образы
и запускает Compose, поэтому его область изменений существенно шире limiter.

## Inventory и окружения

В `deploy/inventory.ini` определены группы:

- `mtproto_dev` — только `vds6`;
- `mtproto_prod` — только `vds1`–`vds5`;
- `mtproto_servers` — все хосты, используется bootstrap-playbook.

Все команды ниже запускаются из корня репозитория. Для локальных временных
файлов Ansible используется каталог `/tmp`:

```bash
export ANSIBLE_LOCAL_TEMP=/tmp/ansible-local
```

Перед работой проверьте состояние репозитория и связь с нужным хостом:

```bash
git status --short
ansible -i deploy/inventory.ini vds6 -m ping
```

Не выводите `telemt.toml`, пользовательские ключи и полные proxy-ссылки.

## Локальная проверка SYN limiter

Перед любым применением:

```bash
uv run pytest deploy/tests/test_telemt_syn_limit.py -q
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit.yml --syntax-check
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit-prod.yml --syntax-check
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit-rollback.yml --syntax-check
bash -n deploy/roles/telemt_syn_limit/files/telemt-syn-limit
git diff --check
```

## Установка limiter на dev

Dev-playbook должен запускаться только с явным ограничением `vds6`:

```bash
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit.yml --limit vds6
```

Проверка на сервере:

```bash
systemctl is-enabled telemt-syn-limit
systemctl is-active telemt-syn-limit
iptables -vnL DOCKER-USER --line-numbers
iptables -vnL TELEMT_SYN_LIMIT --line-numbers
```

Должен присутствовать ровно один переход из `DOCKER-USER`. Проверенный профиль:
порт `443`, rate `54/minute`, burst `5`, превышение отклоняется TCP RST.

## Read-only аудит production

Перед каждым production rollout для `vds1`–`vds5` зафиксируйте без изменения
хостов:

- образ, версию, status и `StartedAt` Telemt;
- `StartedAt` FastAPI-контейнера;
- default IPv4 interface и наличие `DOCKER-USER`;
- состояние `telemt-syn-limit.service`;
- SHA-256 файла `telemt.toml`.

Остановитесь, если хотя бы один хост недоступен, Telemt не запущен или цепочка
`DOCKER-USER` отсутствует.

## Миграция Telemt на 3.4.22

Миграция выполняется сначала только на canary `vds1`. Нельзя менять
`telemt.toml`, TLS-домен, DNS, пользовательские ключи или FastAPI-контейнер.

1. Создайте backup `telemt.toml` с mode `0600` и зафиксируйте исходный SHA-256.
2. Создайте отдельные Compose override-файлы для `3.4.22` и rollback `3.4.6`.
3. Выполните `docker compose ... config --images` для обоих вариантов.
4. Сначала загрузите `ghcr.io/telemt/telemt:3.4.22`.
5. Пересоздайте только сервис `telemt`:

```bash
cd /opt/mtproto
docker compose -f docker-compose.yaml \
  -f /root/telemt-3.4.22.override.yml \
  up -d --no-deps --force-recreate telemt
```

После запуска проверьте version/health, неизменность checksum и `StartedAt`
FastAPI. Контракт FastAPI проверяется временным пользователем по полному циклу:
create, read, rotate, read, delete, затем `404`. Значения ключей и ссылок не
должны попадать в вывод. После проверки восстановите точную backup-копию
`telemt.toml`, поскольку Telemt может канонически переписать TOML даже после
удаления временного пользователя.

При ошибке health или контракта немедленно пересоздайте только Telemt через
override `3.4.6` и проверьте исходный checksum.

## Production canary limiter

После успешной проверки Telemt `3.4.22` установите limiter только на `vds1`:

```bash
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit-prod.yml --limit vds1
```

После применения подтвердите:

- service enabled/active;
- ровно один переход в limiter-chain;
- rate `54/minute`, burst `5` и TCP RST;
- неизменные Telemt config checksum и FastAPI `StartedAt`;
- Telemt `3.4.22` healthy.

## Observation gate

После canary действует минимум 24-часовой observation gate. В этот период
контролируются подключения, RETURN/REJECT, handshake/SNI-ошибки, health,
uptime, операции с ключами и жалобы пользователей за CGNAT.

Не раскатывайте изменения на `vds2–vds5` до завершения gate и отдельного
подтверждения владельца системы.

## Rollback canary

Отключить limiter только на `vds1`:

```bash
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit-rollback.yml --limit vds1
```

После rollback проверьте удаление limiter-chain и неизменность Telemt/API.
Rollback limiter не меняет версию Telemt.

## Fleet rollout

Этот шаг разрешён только после успешного observation gate и отдельного
подтверждения. Playbook выполняется serially:

```bash
ansible-playbook -i deploy/inventory.ini \
  deploy/telemt-syn-limit-prod.yml --limit 'vds2:vds3:vds4:vds5'
```

После каждого хоста проверяйте service, единственный jump, счётчики, Telemt
version/health/uptime и config checksum. При первом расхождении остановите
rollout и выполните rollback только на затронутом хосте.

## Bootstrap нового VDS

`deploy/playbook.yml` допустим только для согласованного первоначального
развёртывания нового пустого сервера. Он устанавливает системные зависимости,
клонирует репозиторий и запускает весь Compose stack.

```bash
ansible-playbook -i deploy/inventory.ini \
  deploy/playbook.yml --limit <new-host>
```

Никогда не запускайте bootstrap без `--limit`.
