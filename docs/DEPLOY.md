# Деплой

Репозиторий использует один production-playbook для всех актуальных серверов.
Playbook обрабатывает их последовательно:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

Playbook обрабатывает серверы по одному и останавливается при первой ошибке. На
каждом сервере он отключает парольную SSH-аутентификацию, устанавливает
зависимости, обновляет `/opt/mtproto` из ветки `main`, устанавливает Telemt как
systemd-сервис и запускает FastAPI через Docker Compose.

Для точечного повторного деплоя можно ограничить запуск одним сервером:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds4
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

## Telemt и Zapret2 V4

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

Роль скачивает официальный архив Zapret2 `v1.0.3` и проверяет SHA-256
`5220d9253b1fc858c7a1e0a6340f2d87f2e30ed24f71c5cee19dfc458734e6a5`.
`nfqws2` и upstream Lua-библиотеки устанавливаются в `/opt/zapret2`, MTProto-
конфигурация — в `/etc/zapret2/mtproto.conf`. Сервис `mtpr-zapret2.service`
создаёт отдельную таблицу `ip MTProto` и направляет входящий и исходящий TCP-
трафик порта 443 в NFQUEUE 200 с флагом `bypass`.

При первой установке роль проверяет, что таблица `ip MTProto` и очередь 200 не
заняты сторонним сервисом. При конфликте playbook останавливается до установки
новых правил. При последующих запусках Zapret2 и Telemt перезапускаются только
при изменении их файлов. Systemd readiness probe требует регистрацию NFQUEUE и
оба правила для входящего и исходящего трафика. Параметр inventory
`telemt_caddy_dependency=true` добавляет Caddy в `After`/`Wants` Telemt, но не
устанавливает и не настраивает сам Caddy.

Lua-стратегия является неофициальной Ansible-адаптацией V4 из
[MTproxy-reanimation](https://github.com/Mekotofeuka/MTproxy-reanimation).
Условия исходной лицензии и описание изменений сохранены в
[`docs/third-party/MTPROTO_FIX_By_MEKO-LICENSE.txt`](third-party/MTPROTO_FIX_By_MEKO-LICENSE.txt)
и [`docs/third-party/MTPROTO_FIX_By_MEKO-NOTICE.md`](third-party/MTPROTO_FIX_By_MEKO-NOTICE.md).

`.env` обновляется точечно:

```env
TELEMT_API_ROOT=http://host.docker.internal:9091/v1
```

Остальные переменные сохраняются. Production Compose запускает только FastAPI
и добавляет `host.docker.internal:host-gateway`.

Проверить работающие сервисы:

```bash
systemctl is-active telemt
systemctl is-active mtpr-zapret2
/usr/local/bin/telemt --version
/opt/zapret2/bin/nfqws2 --version
/usr/local/bin/telemt healthcheck \
  /opt/mtproto/telemt/telemt.toml --mode liveness
/usr/sbin/nft list table ip MTProto
awk '$1 == 200 { found=1 } END { exit !found }' \
  /proc/net/netfilter/nfnetlink_queue
docker compose ps
```

При ошибке playbook останавливается на текущем сервере благодаря `serial: 1` и
`any_errors_fatal: true`. Автоматический rollback не выполняется.

## Возврат версии

История старых сценариев хранится в Git. Для возврата создайте revert нужного
изменения либо восстановите проверенную ревизию в `main`, отправьте её в remote
и снова запустите `deploy/playbook.yml`.

Не выводите в логи `telemt.toml`, пользовательские ключи и полные proxy-ссылки.
