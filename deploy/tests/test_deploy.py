from __future__ import annotations

import json
import os
import subprocess
import tomllib
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
    assert hosts == ["vds1", "vds2", "vds3", "vds4", "vds5"]


def test_inventory_assigns_the_expected_domain_to_every_server() -> None:
    result = subprocess.run(
        [
            "ansible-inventory",
            "-i",
            str(ROOT / "inventory.example.ini"),
            "--list",
        ],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(result.stdout)
    hostvars = inventory["_meta"]["hostvars"]
    assert {
        host: hostvars[host]["mtproto_domain"]
        for host in ("vds1", "vds2", "vds3", "vds4", "vds5")
    } == {
        "vds1": "fast.mtprotokeys.com",
        "vds2": "reserve.mtprotokeys.com",
        "vds3": "sub.mtprotokeys.com",
        "vds4": "space.mtprotokeys.com",
        "vds5": "kz.mtprotokeys.com",
    }


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


def test_example_config_enables_required_client_network_controls() -> None:
    config = tomllib.loads(
        (PROJECT_ROOT / "telemt" / "telemt.example.toml").read_text()
    )

    assert config["server"]["listeners"]
    assert all(
        listener.get("synlimit") is False
        for listener in config["server"]["listeners"]
    )
    assert config["server"]["client_mss"] == "tspu"
    assert config["server"]["client_mss_bulk"] == "1400"


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
        "Verify the server domain resolves to this host",
        "Install Caddy",
        "Install Caddy configuration",
        "Ensure Caddy service is running",
        "Verify downloaded Telemt checksum",
        "Install Telemt binary",
        "Configure Telemt self-steal masking",
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
        "Verify Zapret2 NFQUEUE is available",
        "Install Zapret2 nfqws2 binary",
        "Install MTProto Zapret2 service",
        "Ensure MTProto Zapret2 service is running",
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
    assert "Requires=caddy.service" in unit
    assert "After=network-online.target caddy.service" in unit
    assert (
        "ExecStart=/usr/local/bin/telemt /opt/mtproto/telemt/telemt.toml" in unit
    )
    assert "LimitNOFILE=65536" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in unit
    assert "CAP_NET_ADMIN" not in unit
    assert "NoNewPrivileges=true" in unit


def test_caddy_serves_http_publicly_and_https_on_the_self_steal_port(
    tmp_path: Path,
) -> None:
    caddyfile_path = tmp_path / "Caddyfile"
    playbook = tmp_path / "render-caddyfile.yml"
    template_path = ROOT / "roles" / "mtproto_deploy" / "templates" / "Caddyfile.j2"
    playbook.write_text(
        f"""
---
- name: Render Caddyfile
  hosts: localhost
  gather_facts: false
  vars:
    mtproto_domain: fast.mtprotokeys.com
    caddy_self_steal_port: 8443
  tasks:
    - name: Render production Caddyfile
      ansible.builtin.template:
        src: {json.dumps(str(template_path))}
        dest: {json.dumps(str(caddyfile_path))}
        mode: "0644"
""".lstrip()
    )

    result = _run_local_playbook(playbook, tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    caddyfile = caddyfile_path.read_text()
    assert "https_port 8443" in caddyfile
    assert "http://fast.mtprotokeys.com" in caddyfile
    assert "fast.mtprotokeys.com {" in caddyfile
    assert "bind 0.0.0.0" in caddyfile
    assert "bind 127.0.0.1" in caddyfile
    assert "disable_tlsalpn_challenge" in caddyfile


def test_self_steal_migration_preserves_unrelated_telemt_config(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    script_path = tmp_path / "configure-self-steal.py"
    playbook = tmp_path / "render-self-steal-migration.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "configure-telemt-self-steal.py.j2"
    )
    source = """
[server]
port = 443
client_mss = "2in8"
client_mss_bulk = "1200"

[censorship]
tls_domain = "old.example"
tls_domains = ["another.example"]
unknown_sni_action = "drop"
mask = true
mask_host = "old.example"
mask_port = 443
fake_cert_len = 2048
tls_emulation = true
mask_shape_hardening = true

[access.users]
application = "unchanged-secret"
""".lstrip()
    config_path.write_text(source)
    playbook.write_text(
        f"""
---
- name: Render self-steal migration
  hosts: localhost
  gather_facts: false
  vars:
    mtproto_domain: fast.mtprotokeys.com
    caddy_self_steal_port: 8443
    telemt_client_mss: tspu
    telemt_client_mss_bulk: "1400"
  tasks:
    - name: Render migration script
      ansible.builtin.template:
        src: {json.dumps(str(template_path))}
        dest: {json.dumps(str(script_path))}
        mode: "0755"
""".lstrip()
    )

    rendered = _run_local_playbook(playbook, tmp_path)

    assert rendered.returncode == 0, rendered.stderr + rendered.stdout
    first_run = subprocess.run(
        [str(script_path), str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    first_result = config_path.read_text()
    second_run = subprocess.run(
        [str(script_path), str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert first_run.returncode == 0, first_run.stderr
    assert first_run.stdout.strip() == "changed"
    assert second_run.returncode == 0, second_run.stderr
    assert second_run.stdout.strip() == "unchanged"
    assert config_path.read_text() == first_result
    config = tomllib.loads(first_result)
    assert config["server"] == {
        "port": 443,
        "client_mss": "tspu",
        "client_mss_bulk": "1400",
    }
    assert "tls_domains" not in config["censorship"]
    assert config["censorship"] == {
        "tls_domain": "fast.mtprotokeys.com",
        "unknown_sni_action": "mask",
        "mask": True,
        "mask_host": "127.0.0.1",
        "mask_port": 8443,
        "fake_cert_len": 2048,
        "tls_emulation": False,
        "mask_shape_hardening": True,
    }
    assert config["access"]["users"]["application"] == "unchanged-secret"


def test_env_migration_replaces_only_telemt_api_root() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    migration = tasks.split("- name: Route FastAPI to Telemt on the Docker host", 1)[
        1
    ].split("- name: Apply pending service restarts", 1)[0]

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


def test_verified_archive_always_reextracts_the_installed_binary() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    verified = tasks.index("- name: Verify downloaded Telemt checksum")
    extracted = tasks.index("- name: Extract Telemt binary")
    installed = tasks.index("- name: Install Telemt binary")
    extraction = tasks[extracted:installed]

    assert verified < extracted < installed
    assert "creates:" not in extraction
