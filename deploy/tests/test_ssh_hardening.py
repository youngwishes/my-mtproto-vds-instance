from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_inventory_is_private_and_example_contains_no_real_addresses() -> None:
    gitignore = (ROOT / ".gitignore").read_text().splitlines()
    example = (ROOT / "inventory.example.ini").read_text()

    assert "inventory.ini" in gitignore
    assert "192.0.2." in example
    assert "ansible_ssh_private_key_file" in example


def test_ssh_role_disables_password_authentication_only() -> None:
    role = ROOT / "roles" / "ssh_hardening"
    tasks = (role / "tasks" / "main.yml").read_text()
    config = (role / "templates" / "00-00-disable-password-auth.conf.j2").read_text()

    assert "PasswordAuthentication no" in config
    assert "KbdInteractiveAuthentication no" in config
    assert "ChallengeResponseAuthentication no" in config
    assert "PermitRootLogin" not in config
    assert "sshd -t" in tasks
    assert "state: reloaded" in tasks
    assert "ansible.builtin.wait_for_connection" in tasks
    assert "00-00-disable-password-auth.conf" in tasks
    assert "00-disable-password-auth.conf" in tasks


def test_ssh_hardening_rollout_is_dev_then_serial_prod() -> None:
    dev = (ROOT / "ssh-hardening-dev.yml").read_text()
    prod = (ROOT / "ssh-hardening-prod.yml").read_text()

    assert "hosts: mtproto_dev" in dev
    assert "role: ssh_hardening" in dev
    assert "gather_facts: false" in dev
    assert "ansible.builtin.wait_for_connection" in dev
    assert "hosts: mtproto_prod" in prod
    assert "serial: 1" in prod
    assert "any_errors_fatal: true" in prod
    assert "role: ssh_hardening" in prod
    assert "gather_facts: false" in prod
    assert "ansible.builtin.wait_for_connection" in prod
