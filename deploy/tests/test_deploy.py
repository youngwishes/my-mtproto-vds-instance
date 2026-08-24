from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent


def test_single_playbook_targets_every_inventory_server_serially(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible-local")
    environment["ANSIBLE_REMOTE_TEMP"] = "/tmp/ansible-remote"
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(ROOT / "inventory.example.ini"),
            str(ROOT / "playbook.yml"),
            "--list-hosts",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    hosts = sorted(
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip().startswith("vds")
    )
    assert hosts == ["vds1", "vds2", "vds3", "vds5"]


def _compose_config(compose_file: Path) -> dict:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(compose_file),
            "config",
            "--format",
            "json",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_production_compose_runs_only_api_and_routes_to_host_telemt() -> None:
    config = _compose_config(PROJECT_ROOT / "docker-compose.yaml")

    assert set(config["services"]) == {"api"}
    api = config["services"]["api"]
    assert api["extra_hosts"] == ["host.docker.internal=host-gateway"]


def test_local_compose_keeps_pinned_netfilter_telemt_for_e2e() -> None:
    config = _compose_config(PROJECT_ROOT / "docker-compose.local.yaml")

    telemt = config["services"]["telemt"]
    assert telemt["image"] == "telemt-netfilter:3.4.25"
    assert telemt["build"]["target"] == "prod-netfilter"
    assert "NET_ADMIN" in telemt["cap_add"]
    assert config["services"]["api"]["environment"]["TELEMT_API_ROOT"] == (
        "http://telemt:9091/v1"
    )


def test_deploy_playbook_contains_binary_cutover_and_read_only_probe(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible-local")
    environment["ANSIBLE_REMOTE_TEMP"] = "/tmp/ansible-remote"
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(ROOT / "inventory.example.ini"),
            str(ROOT / "playbook.yml"),
            "--list-tasks",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    for task_name in (
        "Verify downloaded Telemt checksum",
        "Install Telemt binary",
        "Remove legacy Telemt container",
        "Start Telemt systemd service",
        "Verify FastAPI can reach host Telemt without changing config",
        "Verify Telemt config checksum is unchanged",
    ):
        assert task_name in result.stdout


def test_syn_limiter_check_accepts_version_3425_dynamic_chain_name() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert "TMT_SYN_[0-9a-f]{12}" in tasks
    assert "regex_search('TMT_SYN_[0-9a-f]{12}')) is not none" in tasks
    assert "'TELEMT_SYNLIMIT' in" not in tasks


def test_first_binary_migration_is_documented_as_vds4_only() -> None:
    deploy_guide = (PROJECT_ROOT / "docs" / "DEPLOY.md").read_text()

    assert (
        "ansible-playbook -i deploy/inventory.ini deploy/playbook.yml --limit vds4"
        in deploy_guide
    )


def test_installed_telemt_version_check_is_exact() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert 'telemt_version_output.stdout | trim != ("telemt " ~ telemt_version)' in tasks
    assert "telemt {{ telemt_version }}" not in tasks


def test_architecture_selection_uses_non_deprecated_ansible_facts() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert 'ansible_facts["architecture"] in telemt_release_arches' in tasks
    assert 'telemt_release_arches[ansible_facts["architecture"]]' in tasks
    assert "ansible_architecture" not in tasks


def test_systemd_unit_grants_only_required_network_capabilities() -> None:
    unit = (
        ROOT / "roles" / "mtproto_deploy" / "templates" / "telemt.service.j2"
    ).read_text()

    assert "User=telemt" in unit
    assert "Group=telemt" in unit
    assert "ExecStart={{ telemt_binary_path }} {{ telemt_config_path }}" in unit
    assert "LimitNOFILE=65536" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE CAP_NET_ADMIN" in unit
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE CAP_NET_ADMIN" in unit
    assert "NoNewPrivileges=true" in unit


def test_env_migration_replaces_only_telemt_api_root() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    migration = tasks.split("- name: Route FastAPI to Telemt on the Docker host", 1)[
        1
    ].split("- name: Check for legacy Telemt container", 1)[0]

    assert "ansible.builtin.lineinfile:" in migration
    assert "regexp: '^TELEMT_API_ROOT='" in migration
    assert 'line: "TELEMT_API_ROOT={{ telemt_api_root }}"' in migration
    assert "create: false" in migration


def test_cutover_checks_config_after_read_only_fastapi_probe() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    stopped = tasks.index("- name: Record the stopped Telemt config checksum")
    probe = tasks.index(
        "- name: Verify FastAPI can reach host Telemt without changing config"
    )
    verified = tasks.index("- name: Verify Telemt config checksum is unchanged")
    assert stopped < probe < verified
    assert (
        "fastapi_missing_user.json.detail != telemt_missing_user.json.error.message"
        in tasks
    )
    assert "telemt_config_after_cutover.stat.checksum == telemt_config_checksum" in tasks


def test_verified_archive_always_reextracts_the_installed_binary() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    verified = tasks.index("- name: Verify downloaded Telemt checksum")
    extracted = tasks.index("- name: Extract Telemt binary")
    installed = tasks.index("- name: Install Telemt binary")
    extraction = tasks[extracted:installed]

    assert verified < extracted < installed
    assert "creates:" not in extraction
