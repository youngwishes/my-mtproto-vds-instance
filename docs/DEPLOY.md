# Деплой

Репозиторий использует один production-playbook для всех актуальных серверов.
Первую бинарную миграцию Telemt выполняйте только на canary `vds4`
(`148.135.209.179`):

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds4
```

Playbook обрабатывает серверы по одному и останавливается при первой ошибке. На
каждом сервере он отключает парольную SSH-аутентификацию, устанавливает
зависимости, обновляет `/opt/mtproto` из ветки `main`, устанавливает Telemt как
systemd-сервис и запускает FastAPI через Docker Compose.

Команду без `--limit` используйте только после отдельной проверки canary:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

## Inventory

Скопируйте `deploy/inventory.example.ini` в `deploy/inventory.ini`, укажите
актуальные IP-адреса и путь к SSH-ключу. Настоящий inventory исключён из Git.

Все серверы находятся в одной группе `mtproto_servers`; дополнительных
окружений и групп нет.

Проверить соединение:

```bash
ansible -i deploy/inventory.ini mtproto_servers -m ping
```

## Проверка перед деплоем

Команды выполняются из корня репозитория:

```bash
uv run pytest
docker compose config --quiet
docker compose -f docker-compose.local.yaml config --quiet
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --syntax-check
git diff --check
```

Роль деплоя получает код из удалённой ветки `main`. Поэтому локальные изменения
нужно закоммитить и отправить в remote до запуска playbook.

## Telemt и SYN-LIMITER

Роль скачивает официальный архив
`telemt-<arch>-linux-musl.tar.gz` версии `3.4.25` вместе с `.sha256`, проверяет
checksum и устанавливает бинарник в `/usr/local/bin/telemt`. Поддерживаются
`x86_64` и `aarch64`.

Telemt работает от системного пользователя `telemt`. Unit выдаёт только
`CAP_NET_BIND_SERVICE` и `CAP_NET_ADMIN`, устанавливает `LimitNOFILE=65536` и
запускает существующий `/opt/mtproto/telemt/telemt.toml`. Пакеты `iptables`,
`nftables` и `conntrack` обеспечивают встроенный `synlimit = "iptables"`.

Существующий `/opt/mtproto/telemt/telemt.toml` при деплое не перезаписывается.
После остановки старого контейнера роль запоминает SHA-256 файла и проверяет,
что запуск systemd и read-only connectivity probe его не изменили. Владелец и
права меняются на `telemt:telemt` и `0640`, чтобы HTTP API мог атомарно обновлять
пользователей.

`.env` обновляется точечно:

```env
TELEMT_API_ROOT=http://host.docker.internal:9091/v1
```

Остальные переменные сохраняются. Production Compose запускает только FastAPI
и добавляет `host.docker.internal:host-gateway`.

Проверить работающие сервисы:

```bash
systemctl is-active telemt
/usr/local/bin/telemt --version
/usr/local/bin/telemt healthcheck \
  /opt/mtproto/telemt/telemt.toml --mode liveness
iptables-save | grep 'TMT_SYN_[0-9a-f]\{12\}'
docker compose ps
```

Первичная миграция удаляет старый контейнер Telemt перед запуском systemd и не
выполняет автоматический rollback. При ошибке playbook останавливается на
текущем сервере благодаря `serial: 1` и `any_errors_fatal: true`.

## Возврат версии

История старых сценариев хранится в Git. Для возврата создайте revert нужного
изменения либо восстановите проверенную ревизию в `main`, отправьте её в remote
и снова запустите `deploy/playbook.yml`.

Не выводите в логи `telemt.toml`, пользовательские ключи и полные proxy-ссылки.
