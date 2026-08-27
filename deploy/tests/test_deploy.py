from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
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
    assert hosts == ["vds1", "vds2", "vds3", "vds4", "vds5", "vds6"]


def test_repository_has_no_one_shot_cleanup_playbook_or_role() -> None:
    assert not (ROOT / "cleanup-experiments.yml").exists()
    assert not (ROOT / "roles" / "experiment_cleanup").exists()


def test_every_server_uses_the_role_wide_beatvault_profile() -> None:
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
    hostvars = json.loads(result.stdout)["_meta"]["hostvars"]
    profile_keys = {
        "mtproto_domain",
        "telemt_tls_domains",
        "telemt_preserve_existing_tls_domains",
        "telemt_mask_host",
        "telemt_mask_port",
        "telemt_self_steal_enabled",
        "telemt_disable_legacy_zapret",
        "telemt_client_mss",
        "telemt_client_mss_bulk",
    }
    for host in ("vds1", "vds2", "vds3", "vds4", "vds5", "vds6"):
        assert profile_keys.isdisjoint(hostvars[host])


def test_steady_state_migration_enforces_external_beatvault_profile(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    script_path = tmp_path / "configure-telemt.py"
    playbook = tmp_path / "render-configure-telemt.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "configure-telemt.py.j2"
    )
    config_path.write_text(
        """
[server]
port = 443
client_mss = "tspu"
client_mss_bulk = "1400"

[server.api]
enabled = true
listen = "0.0.0.0:9091"
whitelist = []
read_only = false

[censorship]
tls_domain = "old.example"
tls_domains = ["another.example", "beatvault.ru"]
unknown_sni_action = "drop"
mask = false
mask_host = "127.0.0.1"
mask_port = 8443
fake_cert_len = 2048
tls_emulation = true
mask_shape_hardening = true

[access.users]
existing = "unchanged-secret"
""".lstrip()
    )
    playbook.write_text(
        f"""
---
- name: Render steady-state Telemt migration
  hosts: localhost
  gather_facts: false
  vars:
    telemt_tls_domain: beatvault.ru
    telemt_api_listen: 172.17.0.1:9091
    telemt_api_whitelist:
      - 172.16.0.0/12
      - 203.0.113.10/32
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
    config = tomllib.loads(config_path.read_text())
    assert config["server"] == {
        "port": 443,
        "api": {
            "enabled": True,
            "listen": "172.17.0.1:9091",
            "whitelist": ["172.16.0.0/12", "203.0.113.10/32"],
            "read_only": False,
        },
    }
    assert config["censorship"] == {
        "tls_domain": "beatvault.ru",
        "unknown_sni_action": "mask",
        "mask": True,
        "mask_port": 443,
        "fake_cert_len": 2048,
        "tls_emulation": False,
        "mask_shape_hardening": True,
    }
    assert config["access"]["users"] == {"existing": "unchanged-secret"}


def test_application_checkout_is_separate_from_mutable_telemt_config(
    tmp_path: Path,
) -> None:
    playbook = tmp_path / "check-role-paths.yml"
    defaults_path = ROOT / "roles" / "mtproto_deploy" / "defaults" / "main.yml"
    playbook.write_text(
        f"""
---
- name: Check role storage paths
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Load role defaults
      ansible.builtin.include_vars:
        file: {json.dumps(str(defaults_path))}
    - name: Verify application and mutable state are separated
      ansible.builtin.assert:
        that:
          - mtproto_app_dir == '/opt/mtproto-app'
          - telemt_config_dir == '/opt/mtproto/telemt'
          - telemt_config_path == '/opt/mtproto/telemt/telemt.toml'
""".lstrip()
    )

    result = _run_local_playbook(playbook, tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout


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


def _load_ansible_yaml(path: Path) -> list[dict]:
    ansible_playbook = shutil.which("ansible-playbook")
    assert ansible_playbook is not None
    shebang = Path(ansible_playbook).read_text().splitlines()[0]
    assert shebang.startswith("#!")
    interpreter = shlex.split(shebang.removeprefix("#!"))
    result = subprocess.run(
        [
            *interpreter,
            "-c",
            (
                "import json, sys, yaml; from pathlib import Path; "
                "print(json.dumps(yaml.safe_load(Path(sys.argv[1]).read_text())))"
            ),
            str(path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def _prepare_swap_scenario(tmp_path: Path) -> dict[str, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    scenario = {
        "active": tmp_path / "active-swaps",
        "capacity": tmp_path / "capacity-bytes",
        "canonical": tmp_path / "swapfile",
        "failure_marker": tmp_path / "swapoff-failed-once",
        "log": tmp_path / "swap-commands.log",
        "signatures": tmp_path / "swap-signatures",
        "temporary": tmp_path / "swapfile.ansible-replacement",
    }
    for name in ("active", "log", "signatures"):
        scenario[name].write_text("")

    command = fake_bin / "swap-command"
    command.write_text(
        f"""#!{sys.executable}
import os
import sys
from pathlib import Path


def read_lines(variable):
    path = Path(os.environ[variable])
    if not path.exists():
        return []
    return [line for line in path.read_text().splitlines() if line]


def write_lines(variable, lines):
    Path(os.environ[variable]).write_text("".join(f"{{line}}\\n" for line in lines))


def available_bytes():
    capacity = int(Path(os.environ["SWAP_CAPACITY"]).read_text())
    allocated = sum(
        path.stat().st_size
        for path in (
            Path(os.environ["SWAP_CANONICAL"]),
            Path(os.environ["SWAP_TEMPORARY"]),
        )
        if path.exists()
    )
    return capacity - allocated


name = Path(sys.argv[0]).name
args = sys.argv[1:]
with Path(os.environ["SWAP_LOG"]).open("a") as log:
    log.write(f"{{name}} {{' '.join(args)}}\\n")

if name == "stat":
    print(Path(args[-1]).stat().st_size)
elif name == "df":
    print("Avail")
    print(available_bytes())
elif name == "blkid":
    path = args[-1]
    if path in read_lines("SWAP_SIGNATURES") and Path(path).exists():
        print("swap")
    else:
        raise SystemExit(2)
elif name == "fallocate":
    size = int(args[1].removesuffix("M")) * 1024 * 1024
    path = Path(args[2])
    previous_size = path.stat().st_size if path.exists() else 0
    if available_bytes() < max(size - previous_size, 0):
        raise SystemExit(1)
    path.touch()
    with path.open("r+b") as allocated:
        allocated.truncate(size)
    signatures = [item for item in read_lines("SWAP_SIGNATURES") if item != str(path)]
    write_lines("SWAP_SIGNATURES", signatures)
elif name == "mkswap":
    path = args[-1]
    signatures = read_lines("SWAP_SIGNATURES")
    if path not in signatures:
        signatures.append(path)
    write_lines("SWAP_SIGNATURES", signatures)
elif name == "swapon" and args[0].startswith("--show"):
    print("\\n".join(read_lines("SWAP_ACTIVE")))
elif name == "swapon":
    path = args[-1]
    if path not in read_lines("SWAP_SIGNATURES"):
        raise SystemExit(1)
    active = read_lines("SWAP_ACTIVE")
    if path not in active:
        active.append(path)
    write_lines("SWAP_ACTIVE", active)
elif name == "swapoff":
    path = args[-1]
    marker = Path(os.environ["SWAP_FAILURE_MARKER"])
    if path == os.environ.get("SWAP_FAIL_SWAPOFF_ONCE") and not marker.exists():
        marker.touch()
        raise SystemExit(1)
    active = read_lines("SWAP_ACTIVE")
    if path not in active:
        raise SystemExit(1)
    write_lines("SWAP_ACTIVE", [item for item in active if item != path])
else:
    raise SystemExit(f"unsupported fake command: {{name}} {{args}}")
"""
    )
    command.chmod(0o755)
    for name in ("blkid", "df", "fallocate", "mkswap", "stat", "swapoff", "swapon"):
        (fake_bin / name).symlink_to(command)
    scenario["fake_bin"] = fake_bin
    return scenario


def _run_swap_scenario(
    tmp_path: Path,
    scenario: dict[str, Path],
    *,
    fail_swapoff_once: Path | None = None,
) -> subprocess.CompletedProcess:
    tasks = _load_ansible_yaml(
        ROOT / "roles" / "mtproto_deploy" / "tasks" / "configure_swap.yml"
    )
    legacy_cleanup = next(
        index
        for index, task in enumerate(tasks)
        if task["name"] == "Read active swap devices before legacy cleanup"
    )
    tasks = tasks[:legacy_cleanup]
    for task in tasks:
        file_args = task.get("ansible.builtin.file")
        if file_args is not None:
            file_args.pop("owner", None)
            file_args.pop("group", None)

    scenario_tasks = tmp_path / "swap-scenario-tasks.json"
    scenario_tasks.write_text(json.dumps(tasks))
    playbook = tmp_path / "run-swap-scenario.yml"
    environment = {
        "PATH": f"{scenario['fake_bin']}:/usr/bin:/bin:/usr/sbin:/sbin",
        "SWAP_ACTIVE": str(scenario["active"]),
        "SWAP_CANONICAL": str(scenario["canonical"]),
        "SWAP_CAPACITY": str(scenario["capacity"]),
        "SWAP_FAILURE_MARKER": str(scenario["failure_marker"]),
        "SWAP_FAIL_SWAPOFF_ONCE": str(fail_swapoff_once or ""),
        "SWAP_LOG": str(scenario["log"]),
        "SWAP_SIGNATURES": str(scenario["signatures"]),
        "SWAP_TEMPORARY": str(scenario["temporary"]),
    }
    playbook.write_text(
        f"""
---
- name: Run swap state scenario
  hosts: localhost
  gather_facts: false
  environment: {json.dumps(environment)}
  vars:
    mtproto_swap_size_mb: 1
    mtproto_swap_path: {json.dumps(str(scenario["canonical"]))}
    mtproto_temporary_swap_path: {json.dumps(str(scenario["temporary"]))}
  tasks:
    - name: Run production swap tasks
      ansible.builtin.import_tasks: {json.dumps(str(scenario_tasks))}
""".lstrip()
    )
    return _run_local_playbook(playbook, tmp_path)


def _run_swap_fstab_normalizer(fstab_path: Path) -> subprocess.CompletedProcess:
    tasks = _load_ansible_yaml(
        ROOT / "roles" / "mtproto_deploy" / "tasks" / "configure_swap.yml"
    )
    persistence = next(
        task for task in tasks if task["name"] == "Persist canonical swap in fstab"
    )
    command = shlex.split(persistence["ansible.builtin.script"]["cmd"])
    assert command[1:] == ["/etc/fstab"]
    script = ROOT / "roles" / "mtproto_deploy" / "files" / command[0]
    assert script.exists()
    return subprocess.run(
        [sys.executable, str(script), str(fstab_path)],
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


def test_example_config_disables_optional_client_network_controls() -> None:
    config = tomllib.loads(
        (PROJECT_ROOT / "telemt" / "telemt.example.toml").read_text()
    )

    assert config["server"]["listeners"]
    assert all(
        listener.get("synlimit") is False
        for listener in config["server"]["listeners"]
    )
    assert "client_mss" not in config["server"]
    assert "client_mss_bulk" not in config["server"]
    assert config["censorship"] == {
        "tls_domain": "beatvault.ru",
        "unknown_sni_action": "mask",
        "mask": True,
        "mask_port": 443,
        "fake_cert_len": 2048,
        "tls_emulation": False,
    }


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
        "Read canonical swap size",
        "Check disk space for swap replacement",
        "Activate temporary replacement swap",
        "Replace incorrectly sized canonical swap",
        "Remove legacy extra swap",
        "Persist canonical swap in fstab",
        "Verify downloaded Telemt checksum",
        "Install Telemt binary",
        "Configure Telemt external TLS masking",
        "Inspect Telemt beobachten snapshot",
        "Repair Telemt beobachten snapshot ownership",
        "Apply pending service restarts",
        "Ensure Telemt systemd service is running",
        "Verify Telemt external TLS mask",
        "Verify FastAPI can reach host Telemt without changing config",
    ):
        assert task_name in result.stdout

    for legacy_task_name in (
        "Install Caddy",
        "Remove residual Meko V3 firewall rules",
        "Remove experimental Meko V3 service files",
        "Remove legacy Telemt container",
        "Stop Telemt systemd service before config migration",
        "Disable built-in Telemt SYN limiter",
        "Configure built-in Telemt SYN limiter",
        "Verify Telemt SYN limiter rules are absent",
        "Verify built-in Telemt SYN limiter rules",
        "Verify MTProto Zapret2 runtime",
        "Verify Zapret2 NFQUEUE is available",
        "Install Zapret2 nfqws2 binary",
        "Install MTProto Zapret2 service",
        "Ensure MTProto Zapret2 service is running",
        "Verify Telemt config checksum is unchanged",
        "Wait for FastAPI port",
    ):
        assert legacy_task_name not in result.stdout


def test_swap_defaults_render_canonical_paths(tmp_path: Path) -> None:
    rendered_defaults = tmp_path / "swap-defaults.json"
    defaults_path = ROOT / "roles" / "mtproto_deploy" / "defaults" / "main.yml"
    playbook = tmp_path / "render-swap-defaults.yml"
    playbook.write_text(
        f"""
---
- name: Render swap defaults
  hosts: localhost
  gather_facts: false
  tasks:
    - name: Load role defaults
      ansible.builtin.include_vars:
        file: {json.dumps(str(defaults_path))}
    - name: Render canonical swap paths
      ansible.builtin.copy:
        content: >-
          {{{{ {{'path': mtproto_swap_path,
                 'temporary_path': mtproto_temporary_swap_path}} | to_json }}}}
        dest: {json.dumps(str(rendered_defaults))}
        mode: "0600"
""".lstrip()
    )

    result = _run_local_playbook(playbook, tmp_path)

    assert result.returncode == 0, result.stderr + result.stdout
    rendered = json.loads(rendered_defaults.read_text())
    mtproto_swap_path = rendered["path"]
    mtproto_temporary_swap_path = rendered["temporary_path"]
    assert mtproto_swap_path == "/swapfile"
    assert mtproto_temporary_swap_path == "/swapfile.ansible-replacement"


def test_installed_telemt_version_check_is_exact() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert 'telemt_version_output.stdout | trim != ("telemt " ~ telemt_version)' in tasks
    assert "telemt {{ telemt_version }}" not in tasks


def test_architecture_selection_uses_non_deprecated_ansible_facts() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()

    assert 'ansible_facts["architecture"] in telemt_release_arches' in tasks
    assert 'telemt_release_arches[ansible_facts["architecture"]]' in tasks
    assert "ansible_architecture" not in tasks


def test_api_whitelist_uses_non_deprecated_ansible_facts() -> None:
    defaults = (
        ROOT / "roles" / "mtproto_deploy" / "defaults" / "main.yml"
    ).read_text()

    assert 'ansible_facts["default_ipv4"]["address"]' in defaults
    assert "ansible_default_ipv4" not in defaults


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
    assert "After=network-online.target" in unit
    assert "caddy.service" not in unit
    assert "zapret" not in unit.lower()
    assert (
        "ExecStart=/usr/local/bin/telemt /opt/mtproto/telemt/telemt.toml" in unit
    )
    assert "LimitNOFILE=65536" in unit
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in unit
    assert "CAP_NET_ADMIN" not in unit
    assert "NoNewPrivileges=true" in unit
    assert "UMask=0027" in unit


def test_steady_state_migration_preserves_unrelated_telemt_config(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    script_path = tmp_path / "configure-telemt.py"
    playbook = tmp_path / "render-telemt-migration.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "configure-telemt.py.j2"
    )
    source = """
[server]
port = 443
client_mss = "2in8"
client_mss_bulk = "1200"

[server.api]
enabled = true
listen = "127.0.0.1:9091"
whitelist = ["127.0.0.1/32"]
read_only = false

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
- name: Render Telemt migration
  hosts: localhost
  gather_facts: false
  vars:
    telemt_tls_domain: beatvault.ru
    telemt_api_listen: 172.17.0.1:9091
    telemt_api_whitelist: ["172.17.0.0/16"]
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
    assert config["server"]["port"] == 443
    assert config["censorship"] == {
        "tls_domain": "beatvault.ru",
        "unknown_sni_action": "mask",
        "mask": True,
        "mask_port": 443,
        "fake_cert_len": 2048,
        "tls_emulation": False,
        "mask_shape_hardening": True,
    }
    assert config["access"]["users"]["application"] == "unchanged-secret"


def test_steady_state_migration_removes_mss(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    script_path = tmp_path / "configure-telemt.py"
    playbook = tmp_path / "render-telemt-migration.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "configure-telemt.py.j2"
    )
    config_path.write_text(
        """
[server]
port = 443
client_mss = "tspu"
client_mss_bulk = "1400"

[server.api]
enabled = true
listen = "127.0.0.1:9091"
whitelist = ["127.0.0.1/32"]
read_only = false

[censorship]
tls_domain = "old.example"

[access.users]
application = "unchanged-secret"
""".lstrip()
    )
    playbook.write_text(
        f"""
---
- name: Render Telemt migration
  hosts: localhost
  gather_facts: false
  vars:
    telemt_tls_domain: beatvault.ru
    telemt_api_listen: 172.17.0.1:9091
    telemt_api_whitelist: ["172.17.0.0/16"]
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
    assert config["server"]["port"] == 443
    assert config["access"]["users"]["application"] == "unchanged-secret"


def test_external_mask_migration_replaces_tls_domains_without_touching_users(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    script_path = tmp_path / "configure-external-mask.py"
    playbook = tmp_path / "render-external-mask-migration.yml"
    template_path = (
        ROOT
        / "roles"
        / "mtproto_deploy"
        / "templates"
        / "configure-telemt.py.j2"
    )
    config_path.write_text(
        """
[server]
port = 443

[server.api]
enabled = true
listen = "127.0.0.1:9091"
whitelist = ["127.0.0.1/32"]
read_only = false

[censorship]
tls_domain = "check.mtprotokeys.com"
tls_domains = ["old.example", "beatvault.ru"]
unknown_sni_action = "mask"
mask = true
mask_host = "127.0.0.1"
mask_port = 8443
fake_cert_len = 2048
tls_emulation = false

[access.users]
existing = "unchanged-secret"
""".lstrip()
    )
    playbook.write_text(
        f"""
---
- name: Render external-mask migration
  hosts: localhost
  gather_facts: false
  vars:
    telemt_tls_domain: beatvault.ru
    telemt_api_listen: 172.17.0.1:9091
    telemt_api_whitelist: ["172.17.0.0/16"]
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
    assert config["censorship"] == {
        "tls_domain": "beatvault.ru",
        "unknown_sni_action": "mask",
        "mask": True,
        "mask_port": 443,
        "fake_cert_len": 2048,
        "tls_emulation": False,
    }
    assert config["server"]["port"] == 443
    assert config["access"]["users"] == {"existing": "unchanged-secret"}


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


def test_swap_replacement_preserves_active_temporary_swap_until_canonical_active(
) -> None:
    tasks = _load_ansible_yaml(
        ROOT / "roles" / "mtproto_deploy" / "tasks" / "configure_swap.yml"
    )
    tasks_by_name = {task["name"]: task for task in tasks}
    task_names = [task["name"] for task in tasks]

    required_state_tasks = {
        "Read active swap devices before replacement",
        "Record whether temporary replacement swap is active",
        "Remove inactive stale temporary replacement swap",
        "Allocate temporary replacement swap",
        "Protect temporary replacement swap",
        "Format temporary replacement swap",
        "Activate temporary replacement swap",
        "Disable incorrectly sized canonical swap",
        "Replace incorrectly sized canonical swap",
        "Format new canonical swap",
        "Activate canonical swap",
        "Disable temporary replacement swap",
        "Remove temporary replacement swap",
    }
    assert required_state_tasks <= tasks_by_name.keys()

    temporary_active_fact = tasks_by_name[
        "Record whether temporary replacement swap is active"
    ]["ansible.builtin.set_fact"]["mtproto_temporary_swap_active"]
    assert "mtproto_temporary_swap_path in" in temporary_active_fact
    assert "mtproto_active_swaps_before.stdout_lines" in temporary_active_fact

    read_active = task_names.index("Read active swap devices before replacement")
    record_temporary = task_names.index(
        "Record whether temporary replacement swap is active"
    )
    activate_temporary = task_names.index("Activate temporary replacement swap")
    disable_canonical = task_names.index(
        "Disable incorrectly sized canonical swap"
    )
    replace_canonical = task_names.index(
        "Replace incorrectly sized canonical swap"
    )
    format_canonical = task_names.index("Format new canonical swap")
    activate_canonical = task_names.index("Activate canonical swap")
    disable_temporary = task_names.index("Disable temporary replacement swap")
    remove_temporary = task_names.index("Remove temporary replacement swap")
    assert (
        read_active
        < record_temporary
        < activate_temporary
        < disable_canonical
        < replace_canonical
        < format_canonical
        < activate_canonical
        < disable_temporary
        < remove_temporary
    )

    for task_name in (
        "Remove inactive stale temporary replacement swap",
        "Allocate temporary replacement swap",
        "Protect temporary replacement swap",
        "Format temporary replacement swap",
        "Activate temporary replacement swap",
    ):
        conditions = tasks_by_name[task_name]["when"]
        if isinstance(conditions, str):
            conditions = [conditions]
        assert "mtproto_swap_needs_replacement" in conditions
        assert "not mtproto_temporary_swap_active" in conditions

    assert "Disable stale temporary replacement swap" not in tasks_by_name
    assert tasks_by_name["Activate canonical swap"]["ansible.builtin.command"][
        "argv"
    ] == ["swapon", "{{ mtproto_swap_path }}"]
    assert tasks_by_name["Disable temporary replacement swap"][
        "ansible.builtin.command"
    ]["argv"] == ["swapoff", "{{ mtproto_temporary_swap_path }}"]
    cleanup_condition = tasks_by_name["Disable temporary replacement swap"][
        "when"
    ]
    assert "mtproto_swap_needs_replacement" not in cleanup_condition
    assert "mtproto_temporary_swap_path in" in cleanup_condition
    assert "when" not in tasks_by_name["Remove temporary replacement swap"]


def test_swap_rerun_reuses_active_temporary_swap_with_reduced_free_space(
    tmp_path: Path,
) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    scenario["canonical"].write_bytes(b"\0" * (512 * 1024))
    scenario["active"].write_text(f"{scenario['canonical']}\n")
    scenario["signatures"].write_text(f"{scenario['canonical']}\n")
    scenario["capacity"].write_text(str(3_145_728))

    interrupted = _run_swap_scenario(
        tmp_path,
        scenario,
        fail_swapoff_once=scenario["canonical"],
    )

    assert interrupted.returncode != 0
    assert "Disable incorrectly sized canonical swap" in interrupted.stdout, (
        interrupted.stderr + interrupted.stdout
    )
    assert scenario["active"].read_text().splitlines() == [
        str(scenario["canonical"]),
        str(scenario["temporary"]),
    ]
    assert scenario["temporary"].exists()
    scenario["capacity"].write_text(str(2_097_152))

    recovered = _run_swap_scenario(
        tmp_path,
        scenario,
        fail_swapoff_once=scenario["canonical"],
    )

    assert recovered.returncode == 0, recovered.stderr + recovered.stdout
    assert scenario["active"].read_text().splitlines() == [
        str(scenario["canonical"])
    ]
    assert scenario["canonical"].stat().st_size == 1_048_576
    assert str(scenario["canonical"]) in (
        scenario["signatures"].read_text().splitlines()
    )
    assert not scenario["temporary"].exists()


def test_swap_rerun_formats_partially_allocated_fresh_canonical_file(
    tmp_path: Path,
) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    scenario["canonical"].write_bytes(b"\0" * 1_048_576)
    scenario["capacity"].write_text(str(5_242_880))

    recovered = _run_swap_scenario(tmp_path, scenario)

    assert recovered.returncode == 0, recovered.stderr + recovered.stdout
    assert scenario["active"].read_text().splitlines() == [
        str(scenario["canonical"])
    ]
    assert scenario["signatures"].read_text().splitlines() == [
        str(scenario["canonical"])
    ]


def test_swap_rerun_formats_partially_allocated_replacement_canonical_file(
    tmp_path: Path,
) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    scenario["canonical"].write_bytes(b"\0" * 1_048_576)
    scenario["temporary"].write_bytes(b"\0" * 1_048_576)
    scenario["active"].write_text(f"{scenario['temporary']}\n")
    scenario["signatures"].write_text(f"{scenario['temporary']}\n")
    scenario["capacity"].write_text(str(3_145_728))

    recovered = _run_swap_scenario(tmp_path, scenario)

    assert recovered.returncode == 0, recovered.stderr + recovered.stdout
    assert scenario["active"].read_text().splitlines() == [
        str(scenario["canonical"])
    ]
    assert scenario["signatures"].read_text().splitlines() == [
        str(scenario["temporary"]),
        str(scenario["canonical"]),
    ]
    assert not scenario["temporary"].exists()


def test_swap_fstab_normalizer_replaces_indented_and_duplicate_entries(
    tmp_path: Path,
) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text(
        "UUID=root / ext4 defaults 0 1\n"
        "  /2G_swapfile none swap sw 0 0\n"
        "tmpfs /tmp tmpfs defaults 0 0\n"
        "/swapfile none swap defaults 0 0\n"
    )

    result = _run_swap_fstab_normalizer(fstab)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "changed"
    assert fstab.read_text() == (
        "UUID=root / ext4 defaults 0 1\n"
        "/swapfile none swap sw 0 0\n"
        "tmpfs /tmp tmpfs defaults 0 0\n"
    )


def test_swap_fstab_normalizer_preserves_line_after_malformed_managed_entry(
    tmp_path: Path,
) -> None:
    fstab = tmp_path / "fstab"
    fstab.write_text(
        "/swapfile\n"
        "UUID=data /srv/data ext4 defaults 0 2\n"
    )

    result = _run_swap_fstab_normalizer(fstab)

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "changed"
    assert fstab.read_text() == (
        "/swapfile none swap sw 0 0\n"
        "UUID=data /srv/data ext4 defaults 0 2\n"
    )


def test_swap_fstab_normalizer_skips_canonical_second_run(tmp_path: Path) -> None:
    fstab = tmp_path / "fstab"
    canonical = (
        "UUID=root / ext4 defaults 0 1\n"
        "/swapfile none swap sw 0 0\n"
        "UUID=data /srv/data ext4 defaults 0 2\n"
    )
    fstab.write_text(canonical)
    original_inode = fstab.stat().st_ino

    first = _run_swap_fstab_normalizer(fstab)
    second = _run_swap_fstab_normalizer(fstab)

    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "unchanged"
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "unchanged"
    assert fstab.read_text() == canonical
    assert fstab.stat().st_ino == original_inode


def test_verified_archive_always_reextracts_the_installed_binary() -> None:
    tasks = (ROOT / "roles" / "mtproto_deploy" / "tasks" / "main.yml").read_text()
    verified = tasks.index("- name: Verify downloaded Telemt checksum")
    extracted = tasks.index("- name: Extract Telemt binary")
    installed = tasks.index("- name: Install Telemt binary")
    extraction = tasks[extracted:installed]

    assert verified < extracted < installed
    assert "creates:" not in extraction
