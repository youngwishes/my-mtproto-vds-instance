# Деплой

Репозиторий использует один production-playbook для всех актуальных серверов.
Playbook обрабатывает их последовательно:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

Playbook обрабатывает серверы по одному и останавливается при первой ошибке. На
каждом сервере он отключает парольную SSH-аутентификацию, устанавливает
зависимости, обновляет `/opt/mtproto-app` из ветки `main`, устанавливает Telemt
как systemd-сервис и запускает FastAPI через Docker Compose. Канонический swap
— `/swapfile` размером 2048 MiB, snapshot Telemt — единый
`/opt/telemt/beobachten.txt`.

Для точечного повторного деплоя можно ограничить запуск одним сервером:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds4
```

## Inventory

Скопируйте `deploy/inventory.example.ini` в `deploy/inventory.ini`, укажите
актуальные IP-адреса и путь к SSH-ключу. Настоящий inventory исключён из Git.

Все серверы находятся в одной группе `mtproto_servers`; дополнительных
окружений, групп, индивидуальных доменов и MSS-профилей нет. Все хосты используют
единый TLS-домен `beatvault.ru` из defaults роли.

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

## Telemt

Telemt единолично занимает публичный порт `443` и маскирует TLS через внешний
домен `beatvault.ru`. Caddy и self-steal в steady-state схеме не используются.

Роль скачивает официальный архив
`telemt-<arch>-linux-musl.tar.gz` версии `3.4.25` вместе с `.sha256`, проверяет
checksum и устанавливает бинарник в `/usr/local/bin/telemt`. Поддерживаются
`x86_64` и `aarch64`.

Telemt работает от системного пользователя `telemt`. Unit выдаёт только
`CAP_NET_BIND_SERVICE`, устанавливает `LimitNOFILE=65536` и запускает
существующий `/opt/mtproto/telemt/telemt.toml`. Встроенный SYN-limiter Telemt
отключён для всех listeners через `synlimit = false`; `CAP_NET_ADMIN` сервису
не выдаётся. `UMask=0027`, поэтому файлы, создаваемые Telemt, получают umask
`0027`.

Существующий `/opt/mtproto/telemt/telemt.toml` при деплое не перезаписывается.
При чистой установке он создаётся из example-конфига, где `synlimit = false`,
в `[access.users]` задан фиксированный пользователь `application` и для него
установлен лимит одного уникального IP, а `[general.links]` содержит
`show = "*"`. Владелец и права конфига поддерживаются как `telemt:telemt` и
`0640`, чтобы HTTP API мог атомарно обновлять пользователей.

На существующем сервере роль сохраняет `[access.users]` без изменений и
приводит к единому виду только управляемые параметры: API, TLS masking,
`[general.links]` и `beobachten_file`. Snapshot всегда записывается в
`/opt/telemt/beobachten.txt` и имеет владельца `telemt:telemt` и режим `0640`.
Управляемая секция `[censorship]` содержит:

```toml
tls_domain = "beatvault.ru"
unknown_sni_action = "mask"
mask = true
mask_port = 443
tls_emulation = false
```

Telemt автоматически использует `tls_domain` как mask host, поэтому fallback
направляется на `beatvault.ru:443`. Роль не удаляет старые параметры или файлы.
Если на сервере остался нестандартный state, оператор сначала очищает его
вручную.

`.env` обновляется точечно:

```env
TELEMT_API_ROOT=http://host.docker.internal:9091/v1
```

Остальные переменные сохраняются. Production Compose запускает только FastAPI
и добавляет `host.docker.internal:host-gateway`. Git checkout приложения хранится
в `/opt/mtproto-app`, отдельно от изменяемого конфига
`/opt/mtproto/telemt/telemt.toml`.

В `[server.api]` роль устанавливает Telemt API bind
`172.17.0.1:9091`. Docker whitelist — `172.16.0.0/12`; healthcheck whitelist
— host default IPv4 `/32`. Остальные параметры API, включая `enabled`
и `read_only`, сохраняются. Публичный порт `9091` не должен давать HTTP-ответ.

Если `/swapfile` отсутствует, роль создаёт его, форматирует, активирует и
добавляет одну строку `/swapfile none swap sw 0 0` в `/etc/fstab`. Существующий
`/swapfile` должен уже иметь размер 2048 MiB и swap-сигнатуру; иначе playbook
останавливается и ничего не заменяет. Любой дополнительный активный swap также
считается ошибкой и устраняется оператором вручную.

Проверить работающие сервисы:

```bash
systemctl is-active telemt
/usr/local/bin/telemt --version
/usr/local/bin/telemt healthcheck \
  /opt/mtproto/telemt/telemt.toml --mode liveness
curl --resolve "beatvault.ru:443:127.0.0.1" https://beatvault.ru/
docker compose ps
```

При ошибке playbook останавливается на текущем сервере благодаря `serial: 1` и
`any_errors_fatal: true`. Автоматический rollback не выполняется.

## Возврат версии

История старых сценариев хранится в Git. Для возврата создайте revert нужного
изменения либо восстановите проверенную ревизию в `main`, отправьте её в remote
и снова запустите `deploy/playbook.yml`.

Не выводите в логи `telemt.toml`, пользовательские ключи и полные proxy-ссылки.
