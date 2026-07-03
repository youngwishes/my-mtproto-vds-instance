# Telemt SYN limit for Docker

Российские мобильные сети могут временно блокировать MTProxy после шквала
параллельных TCP-подключений. На `vds6` подтверждено: ограничение новых SYN от
одного IPv4-адреса до `54/minute`, burst `5`, с немедленным TCP RST для лишних попыток
позволяет iPhone подключиться к Telemt.

## Архитектура

Telemt опубликован Docker через host port `443`, поэтому трафик проходит через
`FORWARD` и `DOCKER-USER`, а не через host `INPUT`. Сервис
`telemt-syn-limit.service` владеет цепочкой `TELEMT_SYN_LIMIT` и подключает её
первым правилом `DOCKER-USER` только для новых TCP SYN на порт 443.

Допустимые SYN возвращаются в стандартную обработку Docker. Превысившие лимит
попытки получают TCP RST вместо молчаливого DROP.

## Развёртывание на dev

Playbook намеренно нацелен только на группу `mtproto_dev`, где находится один
хост `vds6`:

```bash
ansible-playbook -i deploy/inventory.ini deploy/telemt-syn-limit.yml \
  --limit vds6
```

Prod-хосты `vds1`–`vds5` не входят в `mtproto_dev`. Их rollout требует
отдельного решения после наблюдения за dev.

## Проверка

```bash
systemctl status telemt-syn-limit
iptables -vnL DOCKER-USER --line-numbers
iptables -vnL TELEMT_SYN_LIMIT --line-numbers
```

Первый счётчик цепочки показывает разрешённые SYN, второй — отклонённые через
RST.

## Rollback

Временно удалить правило:

```bash
systemctl stop telemt-syn-limit
```

Вернуть правило:

```bash
systemctl start telemt-syn-limit
```

Отключить автозапуск и удалить активную цепочку:

```bash
systemctl disable --now telemt-syn-limit
```

## Ограничение CGNAT

Hashlimit использует source IPv4. Несколько клиентов одного оператора могут
находиться за общим carrier-grade NAT и делить лимит `54/minute`. Перед prod
rollout нужно наблюдать число отклонений, время подключения и жалобы клиентов;
лимит нельзя повышать без повторной проверки через мобильную сеть.

## Проверка Telemt 3.4.22 на dev

3 июля 2026 года на `vds6` подтверждены Telemt `3.4.22` и профиль limiter
`54/minute`, burst `5`. Холодные подключения через мобильную сеть ускорились
примерно с 6–8 до 3 секунд. После повторных быстрых подключений счётчики RETURN
и REJECT увеличивались, ошибок handshake/SNI в контрольном окне не было.

FastAPI-контракт проверен транзакционным сценарием через работающий API:
создание пользователя, чтение, ротация секрета, повторное чтение, удаление и
проверка `404`. Временный пользователь удалён; секреты и ссылки не сохранялись.

## Production canary

Observation gate начат 3 июля 2026 года в 19:39 MSK на `vds1` и действует не
менее 24 часов. Canary использует Telemt `3.4.22` и limiter `54/minute`, burst
`5`. После миграции Telemt healthy, FastAPI-контейнер не перезапускался,
checksum конфигурации восстановлен к исходному значению. Limiter enabled/active,
в `DOCKER-USER` присутствует ровно один jump; RETURN и REJECT увеличиваются.

До отдельного подтверждения после observation gate запрещено изменять
`vds2`–`vds5`.
