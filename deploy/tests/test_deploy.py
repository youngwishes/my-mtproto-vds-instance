from __future__ import annotations

import json
import os
import subprocess
import tomllib
from pathlib import Path

import pytest


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
    assert hosts == ["vds1", "vds2", "vds3", "vds4", "vds5"]


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


def _run_local_playbook(playbook: Path, tmp_path: Path) -> subprocess.CompletedProcess:
    environment = os.environ.copy()
    environment["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible-local")
    environment["ANSIBLE_REMOTE_TEMP"] = "/tmp/ansible-remote"
    return subprocess.run(
        [
            "ansible-playbook",
            "-i",
            "localhost,",
            "-c",
            "local",
            str(playbook),
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )


def test_production_compose_runs_only_api_and_routes_to_host_telemt() -> None:
    config = _compose_config(PROJECT_ROOT / "docker-compose.yaml")

    assert set(config["services"]) == {"api"}
    api = config["services"]["api"]
    assert api["extra_hosts"] == ["host.docker.internal=host-gateway"]


def test_local_compose_runs_pinned_telemt_without_net_admin() -> None:
    config = _compose_config(PROJECT_ROOT / "docker-compose.local.yaml")

    setup = config["services"]["telemt-setup"]
    telemt = config["services"]["telemt"]
    assert "disable-syn-limiter.sh" in " ".join(setup["command"])
    assert telemt["image"] == "telemt:3.4.25"
    assert telemt["build"]["target"] == "prod"
    assert telemt["cap_add"] == ["NET_BIND_SERVICE"]
    assert config["services"]["api"]["environment"]["TELEMT_API_ROOT"] == (
        "http://telemt:9091/v1"
    )


def test_example_config_disables_syn_limiter_for_every_listener() -> None:
    config = tomllib.loads(
        (PROJECT_ROOT / "telemt" / "telemt.example.toml").read_text()
    )

    assert config["server"]["listeners"]
    assert all(
        listener.get("synlimit") is False
        for listener in config["server"]["listeners"]
    )


def test_local_migration_disables_existing_config_without_other_changes(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    source = """
# Listener comments and formatting must survive.
[[server.listeners]]
ip = "0.0.0.0"
synlimit   = "iptables"   # temporary backend

[[server.listeners]]
ip = "::"
synlimit = 'nftables'# literal string

[access.users]
application = "unchanged-secret"
""".lstrip().rstrip("\n")
    expected = source.replace('"iptables"', "false").replace(
        "'nftables'", "false"
    )
    config_path.write_text(source)
    script = PROJECT_ROOT / "telemt" / "disable-syn-limiter.sh"

    first_run = subprocess.run(
        ["sh", str(script), str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert first_run.returncode == 0, first_run.stderr
    assert config_path.read_text() == expected

    second_run = subprocess.run(
        ["sh", str(script), str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert second_run.returncode == 0, second_run.stderr
    assert config_path.read_text() == expected


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
        "Stop Telemt systemd service before config migration",
        "Disable built-in Telemt SYN limiter",
        "Start Telemt systemd service",
        "Verify Telemt SYN limiter rules are absent",
        "Verify FastAPI can reach host Telemt without changing config",
        "Verify Telemt config checksum is unchanged",
    ):
        assert task_name in result.stdout

    stopped_container = result.stdout.index("Remove legacy Telemt container")
    stopped_service = result.stdout.index(
        "Stop Telemt systemd service before config migration"
    )
    migrated = result.stdout.index("Disable built-in Telemt SYN limiter")
    checksummed = result.stdout.index("Record the stopped Telemt config checksum")
    started = result.stdout.index("Start Telemt systemd service")
    assert stopped_container < stopped_service < migrated < checksummed < started


def test_syn_limiter_migration_preserves_the_rest_of_the_config(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    source = """
# Preserve this comment and all original spacing.
[[server.listeners]]
ip = "0.0.0.0"
port = 443
synlimit   = "iptables"   # temporary backend

[[server.listeners]]
ip = "::"
port = 443
synlimit = 'nftables'# literal string

[[server.listeners]]
ip = "127.0.0.1"
port = 8443
synlimit = false

[access.users]
application = "unchanged-secret"
""".lstrip()
    expected = source.replace('"iptables"', "false").replace(
        "'nftables'", "false"
    )
    config_path.write_text(source)
    playbook = tmp_path / "disable-syn-limiter.yml"
    task_file = (
        ROOT / "roles" / "mtproto_deploy" / "tasks" / "disable_syn_limiter.yml"
    )
    playbook.write_text(
        f"""
---
- name: Test SYN limiter migration
  hosts: localhost
  gather_facts: false
  vars:
    telemt_config_path: {json.dumps(str(config_path))}
  tasks:
    - name: Run production migration task
      ansible.builtin.import_tasks: {json.dumps(str(task_file))}
""".lstrip()
    )

    first_run = _run_local_playbook(playbook, tmp_path)

    assert first_run.returncode == 0, first_run.stderr + first_run.stdout
    assert config_path.read_text() == expected
    migrated = tomllib.loads(config_path.read_text())
    assert [
        listener["synlimit"] for listener in migrated["server"]["listeners"]
    ] == [False, False, False]
    assert migrated["access"]["users"] == {"application": "unchanged-secret"}

    second_run = _run_local_playbook(playbook, tmp_path)

    assert second_run.returncode == 0, second_run.stderr + second_run.stdout
    assert "changed=0" in second_run.stdout


@pytest.mark.parametrize(
    ("iptables_output", "nft_output", "should_pass"),
    [
        ("", "table inet filter\n", True),
        (":TMT_SYN_0123456789ab - [0:0]\n", "", False),
        (":TELEMT_SYNLIMIT - [0:0]\n", "", False),
        ("", "table inet telemt_synlimit_0123456789abcdef\n", False),
        ("", "table ip telemt_synlimit\n", False),
    ],
)
def test_firewall_policy_detects_telemt_rules_from_both_backends(
    tmp_path: Path,
    iptables_output: str,
    nft_output: str,
    should_pass: bool,
) -> None:
    playbook = tmp_path / "verify-firewall-policy.yml"
    task_file = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "tasks"
        / "assert_no_syn_limiter_rules.yml"
    )
    playbook.write_text(
        f"""
---
- name: Test firewall policy
  hosts: localhost
  gather_facts: false
  vars:
    telemt_iptables_rule_sets:
      results:
        - stdout: {json.dumps(iptables_output)}
        - stdout: ""
    telemt_nft_tables:
      stdout: {json.dumps(nft_output)}
  tasks:
    - name: Run production firewall assertion
      ansible.builtin.import_tasks: {json.dumps(str(task_file))}
""".lstrip()
    )

    result = _run_local_playbook(playbook, tmp_path)

    if should_pass:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0
        assert "Telemt SYN limiter firewall rules are still present" in result.stdout


def test_installed_telemt_version_check_is_exact() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert 'telemt_version_output.stdout | trim != ("telemt " ~ telemt_version)' in tasks
    assert "telemt {{ telemt_version }}" not in tasks


def test_architecture_selection_uses_non_deprecated_ansible_facts() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert 'ansible_facts["architecture"] in telemt_release_arches' in tasks
    assert 'telemt_release_arches[ansible_facts["architecture"]]' in tasks
    assert "ansible_architecture" not in tasks


def test_systemd_unit_grants_only_bind_service_capability(tmp_path: Path) -> None:
    unit_path = tmp_path / "telemt.service"
    playbook = tmp_path / "render-telemt-unit.yml"
    template_path = (
        ROOT / "roles" / "mtproto_deploy" / "templates" / "telemt.service.j2"
    )
    playbook.write_text(
        f"""
---
- name: Render Telemt unit
  hosts: localhost
  gather_facts: false
  vars:
    telemt_work_dir: /opt/telemt
    telemt_binary_path: /usr/local/bin/telemt
    telemt_config_path: /opt/mtproto/telemt/telemt.toml
  tasks:
    - name: Render production systemd template
      ansible.builtin.template:
        src: {json.dumps(str(template_path))}
        dest: {json.dumps(str(unit_path))}
        mode: "0644"
""".lstrip()
    )

    result = _run_local_playbook(playbook, tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    unit = unit_path.read_text()

    assert "User=telemt" in unit
    assert "Group=telemt" in unit
    assert (
        "ExecStart=/usr/local/bin/telemt /opt/mtproto/telemt/telemt.toml" in unit
    )
    assert "LimitNOFILE=65536" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in unit
    assert "CAP_NET_ADMIN" not in unit
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
