# Деплой

Репозиторий использует один production-playbook для всех актуальных серверов:

```bash
ansible-playbook -i deploy/inventory.ini deploy/playbook.yml
```

Playbook обрабатывает серверы по одному и останавливается при первой ошибке. На
каждом сервере он отключает парольную SSH-аутентификацию, устанавливает
зависимости, обновляет `/opt/mtproto` из ветки `main` и запускает Docker Compose.

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
ANSIBLE_LOCAL_TEMP=/tmp/ansible-local \
  ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --syntax-check
git diff --check
```

Роль деплоя получает код из удалённой ветки `main`. Поэтому локальные изменения
нужно закоммитить и отправить в remote до запуска playbook.

## Telemt и SYN-LIMITER

Основной `docker-compose.yaml` собирает Telemt `3.4.25` из официального target
`prod-netfilter` и выдаёт контейнеру `NET_ADMIN`. Новый `telemt.toml` создаётся
из `telemt/telemt.example.toml`, где встроенный `synlimit = "iptables"` включён
для IPv4- и IPv6-listener'ов.

Существующий `/opt/mtproto/telemt/telemt.toml` при деплое не перезаписывается.

Проверить работающий контейнер:

```bash
docker exec telemt /app/telemt --version
docker exec telemt /app/telemt \
  healthcheck /etc/telemt/telemt.toml --mode liveness
docker compose ps
```

## Возврат версии

История старых сценариев хранится в Git. Для возврата создайте revert нужного
изменения либо восстановите проверенную ревизию в `main`, отправьте её в remote
и снова запустите `deploy/playbook.yml`.

Не выводите в логи `telemt.toml`, пользовательские ключи и полные proxy-ссылки.
