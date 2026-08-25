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
    assert "/00-disable-password-auth.conf" not in tasks
    assert tasks.count("when: ssh_hardening_config.changed") == 4


def test_single_deploy_hardens_ssh_before_installing_application() -> None:
    playbook = (ROOT / "playbook.yml").read_text()

    assert "hosts: mtproto_servers" in playbook
    assert "serial: 1" in playbook
    assert "any_errors_fatal: true" in playbook
    assert "role: ssh_hardening" in playbook
    assert "role: mtproto_deploy" in playbook
    assert playbook.index("role: ssh_hardening") < playbook.index(
        "role: mtproto_deploy"
    )
