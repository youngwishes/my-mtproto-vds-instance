# Деплой

Репозиторий использует один production-playbook для всех актуальных серверов.
Playbook обрабатывает их последовательно:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

Playbook обрабатывает серверы по одному и останавливается при первой ошибке. На
каждом сервере он отключает парольную SSH-аутентификацию, устанавливает
зависимости, обновляет `/opt/mtproto` из ветки `main`, устанавливает Caddy и
Telemt как systemd-сервисы и запускает FastAPI через Docker Compose.

Для точечного повторного деплоя можно ограничить запуск одним сервером:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds4
```

## Inventory

Скопируйте `deploy/inventory.example.ini` в `deploy/inventory.ini`, укажите
актуальные IP-адреса и путь к SSH-ключу. Настоящий inventory исключён из Git.

Все серверы находятся в одной группе `mtproto_servers`; дополнительных
окружений и групп нет. Собственные домены серверов задаются переменной
`mtproto_domain` в `deploy/host_vars/vdsN.yml`. Перед изменением хоста убедитесь,
что A-запись домена совпадает с `ansible_host`: playbook проверяет это до
установки Caddy.

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

## Caddy и Telemt

Роль устанавливает Caddy из официального stable-репозитория и управляет его
конфигурацией. Caddy принимает HTTP на публичном порту `80` для ACME challenge,
а HTTPS слушает только на `127.0.0.1:8443`. Telemt безусловно зависит от
`caddy.service` через systemd и продолжает единолично занимать публичный порт
`443`.

Роль скачивает официальный архив
`telemt-<arch>-linux-musl.tar.gz` версии `3.4.25` вместе с `.sha256`, проверяет
checksum и устанавливает бинарник в `/usr/local/bin/telemt`. Поддерживаются
`x86_64` и `aarch64`.

Telemt работает от системного пользователя `telemt`. Unit выдаёт только
`CAP_NET_BIND_SERVICE`, устанавливает `LimitNOFILE=65536` и запускает
существующий `/opt/mtproto/telemt/telemt.toml`. Встроенный SYN-limiter Telemt
отключён для всех listeners через `synlimit = false`; `CAP_NET_ADMIN` сервису
не выдаётся.

Существующий `/opt/mtproto/telemt/telemt.toml` при деплое не перезаписывается.
При чистой установке он создаётся из example-конфига, где `synlimit = false` и
нет `client_mss`. Владелец и права поддерживаются как `telemt:telemt` и `0640`,
чтобы HTTP API мог атомарно обновлять пользователей.

Миграция точечно переводит секцию `[censorship]` на self-steal, сохраняя
пользователей и остальные параметры:

```toml
tls_domain = "<собственный домен сервера>"
tls_domains = ["mtprotokeys.com", "beatvault.ru", "<собственный домен сервера>"]
unknown_sni_action = "mask"
mask_host = "127.0.0.1"
mask_port = 8443
tls_emulation = false
```

`.env` обновляется точечно:

```env
TELEMT_API_ROOT=http://host.docker.internal:9091/v1
```

Остальные переменные сохраняются. Production Compose запускает только FastAPI
и добавляет `host.docker.internal:host-gateway`.

Проверить работающие сервисы:

```bash
systemctl is-active telemt
systemctl is-active caddy
/usr/local/bin/telemt --version
/usr/local/bin/telemt healthcheck \
  /opt/mtproto/telemt/telemt.toml --mode liveness
curl --resolve "${MTPROTO_DOMAIN}:443:127.0.0.1" \
  "https://${MTPROTO_DOMAIN}/"
docker compose ps
```

При ошибке playbook останавливается на текущем сервере благодаря `serial: 1` и
`any_errors_fatal: true`. Автоматический rollback не выполняется.

## Возврат версии

История старых сценариев хранится в Git. Для возврата создайте revert нужного
изменения либо восстановите проверенную ревизию в `main`, отправьте её в remote
и снова запустите `deploy/playbook.yml`.

Не выводите в логи `telemt.toml`, пользовательские ключи и полные proxy-ссылки.
