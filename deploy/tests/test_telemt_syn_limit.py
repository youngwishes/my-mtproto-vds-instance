from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_syn_limit_playbook_targets_only_dev_group() -> None:
    inventory = (ROOT / "inventory.ini").read_text()
    playbook = (ROOT / "telemt-syn-limit.yml").read_text()

    assert "[mtproto_dev]" in inventory
    assert "vds6" in inventory.split("[mtproto_dev]", 1)[1]
    assert "hosts: mtproto_dev" in playbook
    assert "hosts: mtproto_servers" not in playbook


def test_dev_playbook_uses_role_and_targets_only_dev() -> None:
    playbook = (ROOT / "telemt-syn-limit.yml").read_text()

    assert "hosts: mtproto_dev" in playbook
    assert "role: telemt_syn_limit" in playbook
    assert "hosts: mtproto_prod" not in playbook


def test_role_keeps_proven_firewall_behavior() -> None:
    role = ROOT / "roles" / "telemt_syn_limit"
    defaults = (role / "defaults" / "main.yml").read_text()
    script = (role / "files" / "telemt-syn-limit").read_text()
    unit = (role / "templates" / "telemt-syn-limit.service.j2").read_text()

    assert "telemt_syn_port: 443" in defaults
    assert 'telemt_syn_rate: "54/minute"' in defaults
    assert "telemt_syn_burst: 5" in defaults
    assert "DOCKER-USER" in script
    assert "--hashlimit-mode srcip" in script
    assert '--hashlimit-burst "$BURST"' in script
    assert "--reject-with tcp-reset" in script
    assert 'ansible_facts["default_ipv4"]["interface"]' in unit
    assert "ansible_default_ipv4" not in unit
    assert "ExecStop=/usr/local/sbin/telemt-syn-limit stop" in unit


def test_firewall_script_uses_docker_user_rate_limit_and_rst() -> None:
    role = ROOT / "roles" / "telemt_syn_limit"
    defaults = (role / "defaults" / "main.yml").read_text()
    script = (role / "files" / "telemt-syn-limit").read_text()

    assert "DOCKER-USER" in script
    assert "--hashlimit-mode srcip" in script
    assert 'RATE="${TELEMT_SYN_RATE:-54/minute}"' in script
    assert 'BURST="${TELEMT_SYN_BURST:-5}"' in script
    assert '--hashlimit-upto "$RATE"' in script
    assert '--hashlimit-burst "$BURST"' in script
    assert "telemt_syn_burst: 5" in defaults
    assert "--reject-with tcp-reset" in script
    assert "-j INPUT" not in script
    assert 'case "${1:-start}"' in script
    assert "stop)" in script


def _inventory_group(inventory: str, group: str) -> list[str]:
    section = inventory.split(f"[{group}]", 1)[1].split("[", 1)[0]
    return [line.split()[0] for line in section.splitlines() if line.strip()]


def test_inventory_has_exact_dev_and_prod_groups() -> None:
    inventory = (ROOT / "inventory.ini").read_text()

    assert _inventory_group(inventory, "mtproto_dev") == ["vds6"]
    assert _inventory_group(inventory, "mtproto_prod") == [
        "vds1",
        "vds2",
        "vds3",
        "vds4",
        "vds5",
    ]


def test_prod_playbook_is_serial_and_uses_role() -> None:
    playbook = (ROOT / "telemt-syn-limit-prod.yml").read_text()

    assert "hosts: mtproto_prod" in playbook
    assert "serial: 1" in playbook
    assert "any_errors_fatal: true" in playbook
    assert "role: telemt_syn_limit" in playbook


def test_full_deploy_playbooks_are_environment_specific() -> None:
    dev = (ROOT / "playbook-dev.yml").read_text()
    prod = (ROOT / "playbook-prod.yml").read_text()

    assert not (ROOT / "playbook.yml").exists()
    assert "hosts: mtproto_dev" in dev
    assert "hosts: mtproto_prod" not in dev
    assert "hosts: mtproto_prod" in prod
    assert "hosts: mtproto_dev" not in prod
    assert "serial: 1" in prod
    assert "any_errors_fatal: true" in prod


def test_full_deploy_playbooks_install_app_before_limiter() -> None:
    for name in ("playbook-dev.yml", "playbook-prod.yml"):
        playbook = (ROOT / name).read_text()

        assert "role: mtproto_deploy" in playbook
        assert "role: telemt_syn_limit" in playbook
        assert playbook.index("role: mtproto_deploy") < playbook.index(
            "role: telemt_syn_limit"
        )


def test_mtproto_deploy_role_owns_full_application_deployment() -> None:
    role = ROOT / "roles" / "mtproto_deploy"
    defaults = (role / "defaults" / "main.yml").read_text()
    tasks = (role / "tasks" / "main.yml").read_text()

    assert "mtproto_repo_url:" in defaults
    assert "mtproto_deploy_dir:" in defaults
    assert "mtproto_repo_branch:" in defaults
    assert "mtproto_swap_size_mb:" in defaults
    assert "Ensure Docker is running" in tasks
    assert "Clone or update repository" in tasks
    assert "docker compose up -d --build" in tasks


def test_rollback_is_serial_and_only_disables_limiter() -> None:
    playbook = (ROOT / "telemt-syn-limit-rollback.yml").read_text()

    assert "hosts: mtproto_prod" in playbook
    assert "serial: 1" in playbook
    assert "any_errors_fatal: true" in playbook
    assert "telemt-syn-limit.service" in playbook
    assert "state: stopped" in playbook
    assert "enabled: false" in playbook
    assert "role: telemt_syn_limit" not in playbook
    assert "telemt" not in playbook.replace("telemt-syn-limit.service", "")


def test_deploy_docs_describe_safe_limiter_rollout() -> None:
    docs = (ROOT.parent / "docs" / "DEPLOY.md").read_text()

    assert "deploy/playbook.yml" not in docs
    assert "deploy/playbook-dev.yml" in docs
    assert "deploy/playbook-prod.yml" in docs
    assert "mtproto_dev" in docs
    assert "mtproto_prod" in docs
    assert "--limit vds6" in docs
    assert "--limit vds1" in docs
    assert "telemt-syn-limit-rollback.yml" in docs
    assert "24" in docs
    assert "vds2–vds5" in docs


def test_limiter_documentation_describes_completed_current_state() -> None:
    docs = (ROOT / "TELEMT-SYN-LIMIT.md").read_text()

    assert "## Текущее состояние" in docs
    assert "playbook-dev.yml" in docs
    assert "playbook-prod.yml" in docs
    assert "54/minute" in docs
    assert "burst `5`" in docs
    assert "tcp-reset" in docs
    assert "## Проверка" in docs
    assert "## Управление и rollback" in docs
    assert "## Ограничение CGNAT" in docs
    assert "Production rollout" not in docs
    assert "Post-rollout" not in docs
    assert "Observation gate" not in docs
    assert "### vds" not in docs
    assert "fingerprint" not in docs
