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


def test_deploy_playbook_contains_steady_state_services_without_legacy_tasks(
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
        "Verify Zapret2 NFQUEUE is available",
        "Install Zapret2 nfqws2 binary",
        "Install MTProto Zapret2 service",
        "Ensure MTProto Zapret2 service is running",
        "Apply pending service restarts",
        "Ensure Telemt systemd service is running",
        "Verify FastAPI can reach host Telemt without changing config",
    ):
        assert task_name in result.stdout

    for legacy_task_name in (
        "Remove legacy Telemt container",
        "Stop Telemt systemd service before config migration",
        "Disable built-in Telemt SYN limiter",
        "Stop legacy MTProto V3 SYN fix",
        "Remove legacy MTProto V3 firewall rules",
        "Verify Telemt SYN limiter rules are absent",
        "Verify MTProto Zapret2 runtime",
        "Verify Telemt config checksum is unchanged",
        "Wait for FastAPI port",
    ):
        assert legacy_task_name not in result.stdout


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
    assert "Requires=mtpr-zapret2.service" in unit
    assert "After=network-online.target mtpr-zapret2.service" in unit
    assert (
        "ExecStart=/usr/local/bin/telemt /opt/mtproto/telemt/telemt.toml" in unit
    )
    assert "LimitNOFILE=65536" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in unit
    assert "CAP_NET_ADMIN" not in unit
    assert "NoNewPrivileges=true" in unit


def test_systemd_unit_preserves_optional_caddy_dependency(tmp_path: Path) -> None:
    unit_path = tmp_path / "telemt.service"
    playbook = tmp_path / "render-telemt-unit-with-caddy.yml"
    template_path = (
        ROOT / "roles" / "mtproto_deploy" / "templates" / "telemt.service.j2"
    )
    playbook.write_text(
        f"""
---
- name: Render Telemt unit with Caddy dependency
  hosts: localhost
  gather_facts: false
  vars:
    telemt_work_dir: /opt/telemt
    telemt_binary_path: /usr/local/bin/telemt
    telemt_config_path: /opt/mtproto/telemt/telemt.toml
    telemt_caddy_dependency: true
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
    unit_lines = set(unit.splitlines())
    assert "After=network-online.target mtpr-zapret2.service caddy.service" in unit_lines
    assert "Wants=network-online.target caddy.service" in unit_lines


def test_env_migration_replaces_only_telemt_api_root() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    migration = tasks.split("- name: Route FastAPI to Telemt on the Docker host", 1)[
        1
    ].split("- name: Prepare pinned MTProto Zapret2 release", 1)[0]

    assert "ansible.builtin.lineinfile:" in migration
    assert "regexp: '^TELEMT_API_ROOT='" in migration
    assert 'line: "TELEMT_API_ROOT={{ telemt_api_root }}"' in migration
    assert "create: false" in migration


def test_fastapi_probe_retries_without_a_separate_port_wait() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    probe = tasks.index(
        "- name: Verify FastAPI can reach host Telemt without changing config"
    )
    probe_tasks = tasks[probe:]
    assert "fastapi_missing_user.get('status', -1) == 404" in probe_tasks
    assert "fastapi_missing_user.get('json', {}).get('detail', '') ==" in probe_tasks
    assert "retries: 6" in probe_tasks
    assert "delay: 2" in probe_tasks
    assert "ansible.builtin.wait_for:" not in tasks


def test_existing_swapfile_is_activated_when_not_listed_by_swapon() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert "swapon --show=NAME --noheadings" in tasks
    assert "when: not mtproto_swap_active" in tasks


def test_existing_zapret2_skips_first_install_queue_preflight() -> None:
    tasks = (
        ROOT / "roles" / "mtproto_deploy" / "tasks" / "install_zapret2.yml"
    ).read_text()

    for task_name in (
        "Read active NFQUEUE registry before Zapret2 cutover",
        "Read nftables queue rules before Zapret2 cutover",
        "Verify Zapret2 NFQUEUE is available",
    ):
        task = tasks.split(f"- name: {task_name}", 1)[1].split("\n- name:", 1)[0]
        assert "when: not mtproto_zapret2_existing_service.stat.exists" in task


def test_zapret2_file_changes_notify_the_restart_handler() -> None:
    tasks = (
        ROOT / "roles" / "mtproto_deploy" / "tasks" / "install_zapret2.yml"
    ).read_text()
    handlers = (
        ROOT / "roles" / "mtproto_deploy" / "handlers" / "main.yml"
    ).read_text()

    for task_name in (
        "Install Zapret2 nfqws2 binary",
        "Install upstream Zapret2 Lua libraries",
        "Install MTProto Zapret2 Lua strategy",
        "Install MTProto Zapret2 configuration",
        "Install MTProto Zapret2 startup script",
        "Install MTProto Zapret2 readiness probe",
        "Install MTProto Zapret2 service",
    ):
        task = tasks.split(f"- name: {task_name}", 1)[1].split("\n- name:", 1)[0]
        assert "notify: Restart MTProto Zapret2" in task

    assert "- name: Restart MTProto Zapret2" in handlers


def test_verified_archive_always_reextracts_the_installed_binary() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    verified = tasks.index("- name: Verify downloaded Telemt checksum")
    extracted = tasks.index("- name: Extract Telemt binary")
    installed = tasks.index("- name: Install Telemt binary")
    extraction = tasks[extracted:installed]

    assert verified < extracted < installed
    assert "creates:" not in extraction


def test_zapret2_startup_queues_both_mtproto_directions_before_starting_nfqws(
    tmp_path: Path,
) -> None:
    nft_log = tmp_path / "nft.log"
    nfqws_log = tmp_path / "nfqws.log"
    fake_nft = tmp_path / "nft"
    fake_nfqws = tmp_path / "nfqws2"
    fake_nft.write_text("#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$NFT_LOG\"\n")
    fake_nfqws.write_text(
        "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$NFQWS_LOG\"\n"
    )
    fake_nft.chmod(0o755)
    fake_nfqws.chmod(0o755)

    script_path = tmp_path / "mtpr-zapret2-start"
    playbook = tmp_path / "render-zapret2-start.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "mtpr-zapret2-start.sh.j2"
    )
    playbook.write_text(
        f"""
---
- name: Render MTProto Zapret2 startup script
  hosts: localhost
  gather_facts: false
  vars:
    mtproto_zapret2_nft_binary: {json.dumps(str(fake_nft))}
    mtproto_zapret2_binary_path: {json.dumps(str(fake_nfqws))}
    mtproto_zapret2_config_path: /etc/zapret2/mtproto.conf
    mtproto_zapret2_table: MTProto
    mtproto_zapret2_port: 443
    mtproto_zapret2_queue_num: 200
    mtproto_zapret2_fwmark: "0x40000000"
    mtproto_zapret2_conntrack_mark: "0x00040000"
    mtproto_zapret2_combined_mark: "0x40040000"
  tasks:
    - name: Render production Zapret2 startup template
      ansible.builtin.template:
        src: {json.dumps(str(template_path))}
        dest: {json.dumps(str(script_path))}
        mode: "0755"
""".lstrip()
    )

    rendered = _run_local_playbook(playbook, tmp_path)

    assert rendered.returncode == 0, rendered.stderr + rendered.stdout
    environment = os.environ.copy()
    environment["NFT_LOG"] = str(nft_log)
    environment["NFQWS_LOG"] = str(nfqws_log)
    applied = subprocess.run(
        [str(script_path)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert applied.returncode == 0, applied.stderr
    commands = nft_log.read_text()
    expected_in_order = (
        "delete table ip MTProto",
        "add table ip MTProto",
        "tcp sport 443 counter queue num 200 bypass",
        "tcp dport 443 counter queue num 200 bypass",
    )
    positions = [commands.index(fragment) for fragment in expected_in_order]

    assert positions == sorted(positions)
    assert nfqws_log.read_text() == "@/etc/zapret2/mtproto.conf\n"


def test_zapret2_readiness_requires_both_mtproto_directions(
    tmp_path: Path,
) -> None:
    fake_nft = tmp_path / "nft"
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    fake_nft.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' 'tcp sport 443 counter queue flags bypass to 200'\n"
    )
    fake_nft.chmod(0o755)
    (fake_bin / "awk").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "sleep").write_text("#!/bin/sh\nexit 0\n")
    (fake_bin / "awk").chmod(0o755)
    (fake_bin / "sleep").chmod(0o755)

    script_path = tmp_path / "mtpr-zapret2-ready"
    playbook = tmp_path / "render-zapret2-ready.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "mtpr-zapret2-ready.sh.j2"
    )
    playbook.write_text(
        f"""
---
- name: Render MTProto Zapret2 readiness probe
  hosts: localhost
  gather_facts: false
  vars:
    mtproto_zapret2_nft_binary: {json.dumps(str(fake_nft))}
    mtproto_zapret2_table: MTProto
    mtproto_zapret2_port: 443
    mtproto_zapret2_queue_num: 200
  tasks:
    - name: Render production Zapret2 readiness template
      ansible.builtin.template:
        src: {json.dumps(str(template_path))}
        dest: {json.dumps(str(script_path))}
        mode: "0755"
""".lstrip()
    )

    rendered = _run_local_playbook(playbook, tmp_path)

    assert rendered.returncode == 0, rendered.stderr + rendered.stdout
    environment = os.environ.copy()
    environment["PATH"] = f"{fake_bin}:{environment['PATH']}"
    ready = subprocess.run(
        [str(script_path)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert ready.returncode != 0

    fake_nft.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' "
        "'tcp sport 443 counter queue flags bypass to 200' "
        "'tcp dport 443 counter queue flags bypass to 200'\n"
    )
    ready = subprocess.run(
        [str(script_path)],
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )

    assert ready.returncode == 0, ready.stderr


@pytest.mark.parametrize(
    ("queue_registry", "queue_rules", "should_pass"),
    [
        ("", "", True),
        ("  200  1234  0 2 65531 0 0 0 1\n", "", False),
        ("", "queue flags bypass to 200\n", False),
        ("  201  1234  0 2 65531 0 0 0 1\n", "queue num 201\n", True),
    ],
)
def test_zapret2_queue_policy_rejects_only_the_configured_queue(
    tmp_path: Path,
    queue_registry: str,
    queue_rules: str,
    should_pass: bool,
) -> None:
    playbook = tmp_path / "verify-zapret2-queue.yml"
    task_file = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "tasks"
        / "assert_zapret2_queue_available.yml"
    )
    playbook.write_text(
        f"""
---
- name: Test Zapret2 queue policy
  hosts: localhost
  gather_facts: false
  vars:
    mtproto_zapret2_queue_num: 200
    mtproto_zapret2_queue_registry:
      stdout: {json.dumps(queue_registry)}
    mtproto_zapret2_queue_rules:
      stdout: {json.dumps(queue_rules)}
  tasks:
    - name: Run production queue assertion
      ansible.builtin.import_tasks: {json.dumps(str(task_file))}
""".lstrip()
    )

    result = _run_local_playbook(playbook, tmp_path)

    if should_pass:
        assert result.returncode == 0, result.stderr + result.stdout
    else:
        assert result.returncode != 0
        assert "Zapret2 NFQUEUE 200 is already in use" in result.stdout
