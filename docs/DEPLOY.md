# Деплой

Автоматизированный деплой через Ansible. Один плейбук разворачивает сервис на любом количестве VDS с нуля.

## Что делает плейбук

1. Создаёт swap 2GB (если нет), выставляет `vm.swappiness=10`
2. Устанавливает `git` и Docker (если не установлен)
3. Клонирует репозиторий в `/opt/mtproto` (при повторном запуске — обновляет)
4. Создаёт `.env` из `.env.example` (пропускает если уже существует)
5. Запускает контейнеры: `docker compose up -d --build`

`telemt.toml` создаётся автоматически из `telemt.example.toml` init-контейнером при первом старте.

Размер swap можно изменить через переменную в `playbook.yml`:

```yaml
vars:
  swap_size_mb: 2048  # 2GB по умолчанию
```

## Структура

```
deploy/
├── ansible.cfg      # настройки Ansible (inventory, отключение host key check)
├── inventory.ini    # список серверов
└── playbook.yml     # шаги деплоя
```

## Предварительная настройка (один раз)

### 1. Установить Ansible

```bash
brew install ansible
```

### 2. Закинуть deploy-ключ на сервер

```bash
ssh-copy-id -i ~/.ssh/id_ed25519_deploy.pub root@<ip>
```

Если ключа нет — сначала создать:

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_ed25519_deploy -N "" -C "ansible-deploy"
```

### 3. Проверить связь

```bash
cd deploy/
ansible all -m ping
```

Ожидаемый результат: `pong` от всех серверов.

## Деплой

```bash
cd deploy/

# На все серверы
ansible-playbook playbook.yml

# На конкретный сервер
ansible-playbook playbook.yml --limit vds2
```

## Добавить новый сервер

1. Добавить запись в `deploy/inventory.ini`:

```ini
[mtproto_servers]
vds1 ansible_host=5.253.188.65
vds2 ansible_host=82.47.169.229
vds3 ansible_host=<новый ip>   ← добавить
```

2. Закинуть deploy-ключ:

```bash
ssh-copy-id -i ~/.ssh/id_ed25519_deploy.pub root@<новый ip>
```

3. Задеплоить:

```bash
ansible-playbook playbook.yml --limit vds3
```
