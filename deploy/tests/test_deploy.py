from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent


def _run_local_playbook(
    playbook: Path, tmp_path: Path
) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    environment["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible-local")
    environment["ANSIBLE_REMOTE_TEMP"] = "/tmp/ansible-remote"
    return subprocess.run(
        ["ansible-playbook", "-i", "localhost,", "-c", "local", str(playbook)],
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


def _render_configure_telemt(tmp_path: Path) -> Path:
    script_path = tmp_path / "configure-telemt.py"
    template_path = ROOT / "roles/mtproto_deploy/templates/configure-telemt.py.j2"
    playbook = tmp_path / "render-configure-telemt.yml"
    playbook.write_text(
        f"""
---
- name: Render Telemt configuration helper
  hosts: localhost
  gather_facts: false
  vars:
    telemt_tls_domain: beatvault.ru
    telemt_api_listen: 172.17.0.1:9091
    telemt_api_whitelist:
      - 172.16.0.0/12
      - 203.0.113.10/32
    telemt_beobachten_path: /opt/telemt/beobachten.txt
  tasks:
    - name: Render production helper
      ansible.builtin.template:
        src: {json.dumps(str(template_path))}
        dest: {json.dumps(str(script_path))}
        mode: "0755"
""".lstrip()
    )
    result = _run_local_playbook(playbook, tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    return script_path


def _section_bytes(config: str, section: str) -> str:
    marker = f"[{section}]"
    start = config.index(marker)
    next_section = config.find("\n[", start + len(marker))
    return config[start:] if next_section == -1 else config[start:next_section]


def _run_config_convergence_scenario(
    tmp_path: Path,
    config: str,
    *,
    fail_apply: bool = False,
    preconfigure: bool = False,
) -> tuple[subprocess.CompletedProcess[str], Path, Path]:
    config_path = tmp_path / "telemt.toml"
    config_path.write_text(config)
    script_path = _render_configure_telemt(tmp_path)
    if preconfigure:
        configured = subprocess.run(
            [str(script_path), str(config_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        assert configured.returncode == 0, configured.stderr
    tasks = _load_ansible_yaml(ROOT / "roles/mtproto_deploy/tasks/main.yml")
    tasks_by_name = {task["name"]: task for task in tasks}
    selected = json.loads(
        json.dumps(
            [
                tasks_by_name["Check whether Telemt configuration is current"],
                tasks_by_name["Apply pending Telemt configuration"],
            ]
        )
    )

    service_log = tmp_path / "service.log"
    fake_service = tmp_path / "fake-service.py"
    fake_service.write_text(
        f"""#!{sys.executable}
import sys
from pathlib import Path

state, config_name, log_name = sys.argv[1:]
config_path = Path(config_name)
with Path(log_name).open("a") as log:
    if state == "stopped":
        pending = 'tls_domain = "old.example"' in config_path.read_text()
        log.write(f"stopped:{{'pending' if pending else 'already-written'}}\\n")
    else:
        log.write(f"{{state}}\\n")
if state == "stopped":
    config_path.write_text(
        config_path.read_text().replace("old-secret", "rotated-secret")
    )
"""
    )
    fake_service.chmod(0o755)
    apply = selected[1]
    for task in [*apply["block"], *apply["always"]]:
        service = task.pop("ansible.builtin.systemd_service", None)
        if service is not None:
            task["ansible.builtin.command"] = {
                "argv": [
                    str(fake_service),
                    service["state"],
                    str(config_path),
                    str(service_log),
                ]
            }
    if fail_apply:
        configure_task = next(
            task
            for task in apply["block"]
            if task["name"] == "Configure Telemt while stopped"
        )
        configure_task["ansible.builtin.command"] = {
            "argv": [sys.executable, "-c", "raise SystemExit(23)"]
        }
        configure_task.pop("register", None)
        configure_task.pop("changed_when", None)

    task_file = tmp_path / "configure-tasks.json"
    task_file.write_text(json.dumps(selected))
    playbook = tmp_path / "run-configure-tasks.yml"
    playbook.write_text(
        f"""
---
- name: Run production configuration tasks
  hosts: localhost
  gather_facts: false
  vars:
    telemt_configure_script_path: {json.dumps(str(script_path))}
    telemt_config_path: {json.dumps(str(config_path))}
  tasks:
    - name: Run role tasks
      ansible.builtin.import_tasks: {json.dumps(str(task_file))}
""".lstrip()
    )
    return _run_local_playbook(playbook, tmp_path), config_path, service_log


def _run_fastapi_start_task(
    tmp_path: Path,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    tasks = _load_ansible_yaml(ROOT / "roles/mtproto_deploy/tasks/main.yml")
    start_task = next(
        task for task in tasks if task["name"] == "Start FastAPI container"
    )
    scenario_tasks = tmp_path / "start-fastapi-task.json"
    scenario_tasks.write_text(json.dumps([start_task]))
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    invocation_path = tmp_path / "docker-invocation.json"
    fake_docker = fake_bin / "docker"
    fake_docker.write_text(
        f"""#!{sys.executable}
import json
import os
import sys
from pathlib import Path

Path(os.environ["COMPOSE_INVOCATION"]).write_text(json.dumps({{
    "argv": sys.argv[1:],
    "cwd": os.getcwd(),
}}))
"""
    )
    fake_docker.chmod(0o755)
    app_dir = tmp_path / "app"
    app_dir.mkdir()
    playbook = tmp_path / "run-start-fastapi.yml"
    playbook.write_text(
        f"""
---
- name: Run production FastAPI start task
  hosts: localhost
  gather_facts: false
  environment:
    PATH: {json.dumps(f"{fake_bin}:/usr/bin:/bin:/usr/sbin:/sbin")}
    COMPOSE_INVOCATION: {json.dumps(str(invocation_path))}
  vars:
    mtproto_app_dir: {json.dumps(str(app_dir))}
  tasks:
    - name: Run production task
      ansible.builtin.import_tasks: {json.dumps(str(scenario_tasks))}
""".lstrip()
    )
    return _run_local_playbook(playbook, tmp_path), invocation_path


def _prepare_swap_scenario(tmp_path: Path) -> dict[str, Path]:
    fake_bin = tmp_path / "fake-bin"
    fake_bin.mkdir()
    scenario = {
        "active": tmp_path / "active-swaps",
        "canonical": tmp_path / "swapfile",
        "fstab": tmp_path / "fstab",
        "log": tmp_path / "swap-commands.log",
        "signatures": tmp_path / "swap-signatures",
    }
    for name in ("active", "log", "signatures"):
        scenario[name].write_text("")
    scenario["fstab"].write_text("UUID=root / ext4 defaults 0 1\n")
    command = fake_bin / "swap-command"
    command.write_text(
        f"""#!{sys.executable}
import os
import sys
from pathlib import Path


def read_lines(variable):
    path = Path(os.environ[variable])
    return path.read_text().splitlines() if path.exists() else []


def write_lines(variable, lines):
    Path(os.environ[variable]).write_text("".join(f"{{line}}\\n" for line in lines))


name = Path(sys.argv[0]).name
args = sys.argv[1:]
with Path(os.environ["SWAP_LOG"]).open("a") as log:
    log.write(f"{{name}} {{' '.join(args)}}\\n")

if name == "stat":
    print(Path(args[-1]).stat().st_size)
elif name == "blkid":
    path = args[-1]
    if path in read_lines("SWAP_SIGNATURES") and Path(path).exists():
        print("swap")
    else:
        raise SystemExit(2)
elif name == "fallocate":
    size = int(args[1].removesuffix("M")) * 1024 * 1024
    path = Path(args[2])
    path.touch()
    with path.open("r+b") as allocated:
        allocated.truncate(size)
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
else:
    raise SystemExit(f"unsupported fake command: {{name}} {{args}}")
"""
    )
    command.chmod(0o755)
    for name in ("blkid", "fallocate", "mkswap", "stat", "swapon"):
        (fake_bin / name).symlink_to(command)
    scenario["fake_bin"] = fake_bin
    return scenario


def _run_swap_scenario(
    tmp_path: Path,
    scenario: dict[str, Path],
) -> subprocess.CompletedProcess[str]:
    tasks = _load_ansible_yaml(ROOT / "roles/mtproto_deploy/tasks/configure_swap.yml")
    for task in tasks:
        file_args = task.get("ansible.builtin.file")
        if file_args is not None:
            file_args.pop("owner", None)
            file_args.pop("group", None)
        line_args = task.get("ansible.builtin.lineinfile")
        if line_args is not None and line_args.get("path") == "/etc/fstab":
            line_args["path"] = str(scenario["fstab"])
    scenario_tasks = tmp_path / "swap-scenario-tasks.json"
    scenario_tasks.write_text(json.dumps(tasks))
    playbook = tmp_path / "run-swap-scenario.yml"
    playbook.write_text(
        f"""
---
- name: Run production swap tasks
  hosts: localhost
  gather_facts: false
  environment:
    PATH: {json.dumps(f"{scenario['fake_bin']}:/usr/bin:/bin:/usr/sbin:/sbin")}
    SWAP_ACTIVE: {json.dumps(str(scenario["active"]))}
    SWAP_LOG: {json.dumps(str(scenario["log"]))}
    SWAP_SIGNATURES: {json.dumps(str(scenario["signatures"]))}
  vars:
    mtproto_swap_size_mb: 1
    mtproto_swap_path: {json.dumps(str(scenario["canonical"]))}
  tasks:
    - name: Run role task file
      ansible.builtin.import_tasks: {json.dumps(str(scenario_tasks))}
""".lstrip()
    )
    return _run_local_playbook(playbook, tmp_path)


def _run_snapshot_scenario(
    tmp_path: Path,
    *,
    exists: bool,
) -> tuple[subprocess.CompletedProcess[str], Path]:
    tasks = _load_ansible_yaml(ROOT / "roles/mtproto_deploy/tasks/main.yml")
    tasks_by_name = {task["name"]: task for task in tasks}
    inspect = tasks_by_name["Wait for Telemt beobachten snapshot"]
    assert inspect["retries"] == 6
    assert inspect["delay"] == 1
    assert inspect["until"] == [
        "telemt_beobachten.stat.exists",
        "telemt_beobachten.stat.isreg",
    ]
    selected = [
        inspect,
        tasks_by_name["Protect Telemt beobachten snapshot"],
    ]
    snapshot = tmp_path / "beobachten.txt"
    if exists:
        snapshot.write_text("snapshot\n")
        snapshot.chmod(0o666)
    for task in selected:
        for module in ("ansible.builtin.stat", "ansible.builtin.file"):
            args = task.get(module)
            if args is not None:
                args["path"] = str(snapshot)
                args.pop("owner", None)
                args.pop("group", None)
    task_file = tmp_path / "snapshot-tasks.json"
    task_file.write_text(json.dumps(selected))
    playbook = tmp_path / "run-snapshot-tasks.yml"
    playbook.write_text(
        f"""
---
- name: Run production snapshot tasks
  hosts: localhost
  gather_facts: false
  vars:
    telemt_beobachten_path: {json.dumps(str(snapshot))}
  tasks:
    - name: Run role tasks
      ansible.builtin.import_tasks: {json.dumps(str(task_file))}
""".lstrip()
    )
    return _run_local_playbook(playbook, tmp_path), snapshot


def test_single_playbook_targets_every_inventory_server_serially(
    tmp_path: Path,
) -> None:
    environment = os.environ.copy()
    environment["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible-local")
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


def test_example_config_has_fixed_application_user_and_canonical_paths() -> None:
    config = tomllib.loads((PROJECT_ROOT / "telemt/telemt.example.toml").read_text())
    assert config["access"]["users"] == {
        "application": "f7500d69d0479eb1c90454490aa7096d"
    }
    assert config["access"]["user_max_unique_ips"] == {"application": 1}
    assert config["general"]["beobachten_file"] == "/opt/telemt/beobachten.txt"
    assert config["general"]["links"] == {"show": "*"}
    assert "show_link" not in config


def test_existing_users_are_byte_preserved_while_managed_config_converges(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "telemt.toml"
    source = """
show_link = ["existing"]

[general]
fast_mode = true
beobachten_file = "/etc/telemt/beobachten.txt"

[server]
port = 443
client_mss = "keep-me"

[server.api]
enabled = true
listen = "0.0.0.0:9091"
whitelist = []
read_only = false

[censorship]
tls_domain = "old.example"
tls_domains = ["keep.example"]
unknown_sni_action = "drop"
mask = false
mask_host = "keep.example"
mask_port = 8443
tls_emulation = true

[access.users]
# Managed by the backend. Preserve these bytes exactly.
alice   = "first-secret"
bob = 'second-secret'
""".lstrip()
    config_path.write_text(source)
    original_users = _section_bytes(source, "access.users")
    script_path = _render_configure_telemt(tmp_path)
    first = subprocess.run(
        [str(script_path), str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    first_result = config_path.read_text()
    second = subprocess.run(
        [str(script_path), str(config_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, first.stderr
    assert first.stdout.strip() == "changed"
    assert second.returncode == 0, second.stderr
    assert second.stdout.strip() == "unchanged"
    assert config_path.read_text() == first_result
    assert _section_bytes(first_result, "access.users") == original_users
    config = tomllib.loads(first_result)
    assert "beobachten_file" not in config
    assert config["general"]["beobachten_file"] == "/opt/telemt/beobachten.txt"
    assert config["general"]["links"] == {"show": "*"}
    assert config["server"]["api"]["listen"] == "172.17.0.1:9091"
    assert config["server"]["api"]["whitelist"] == [
        "172.16.0.0/12",
        "203.0.113.10/32",
    ]
    assert config["censorship"]["tls_domain"] == "beatvault.ru"
    assert config["censorship"]["unknown_sni_action"] == "mask"
    assert config["censorship"]["mask"] is True
    assert config["censorship"]["mask_port"] == 443
    assert config["censorship"]["tls_emulation"] is False
    assert config["server"]["client_mss"] == "keep-me"
    assert config["censorship"]["tls_domains"] == ["keep.example"]
    assert config["censorship"]["mask_host"] == "keep.example"


def test_pending_config_is_reread_after_stop_and_preserves_rotated_user(
    tmp_path: Path,
) -> None:
    source = """
[general]
fast_mode = true

[server.api]
enabled = true
listen = "0.0.0.0:9091"
whitelist = []
read_only = false

[censorship]
tls_domain = "old.example"
unknown_sni_action = "drop"
mask = false
mask_port = 8443
tls_emulation = true

[access.users]
alice = "old-secret"
""".lstrip()

    result, config_path, service_log = _run_config_convergence_scenario(
        tmp_path, source
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert service_log.read_text().splitlines() == ["stopped:pending", "started"]
    config = tomllib.loads(config_path.read_text())
    assert config["access"]["users"] == {"alice": "rotated-secret"}
    assert config["general"]["beobachten_file"] == "/opt/telemt/beobachten.txt"
    assert config["server"]["api"]["listen"] == "172.17.0.1:9091"


def test_current_config_does_not_stop_telemt(tmp_path: Path) -> None:
    source = """
[general]
fast_mode = true

[server.api]
enabled = true
listen = "0.0.0.0:9091"
whitelist = []
read_only = false

[censorship]
tls_domain = "old.example"
unknown_sni_action = "drop"
mask = false
mask_port = 8443
tls_emulation = true

[access.users]
alice = "old-secret"
""".lstrip()

    result, _, service_log = _run_config_convergence_scenario(
        tmp_path, source, preconfigure=True
    )

    assert result.returncode == 0, result.stderr + result.stdout
    assert not service_log.exists()


def test_failed_config_apply_starts_telemt_before_failing_play(
    tmp_path: Path,
) -> None:
    source = """
[general]
beobachten_file = "/etc/telemt/beobachten.txt"

[server.api]
listen = "0.0.0.0:9091"
whitelist = []

[censorship]
tls_domain = "old.example"
unknown_sni_action = "drop"
mask = false
mask_port = 8443
tls_emulation = true

[access.users]
alice = "old-secret"
""".lstrip()

    result, _, service_log = _run_config_convergence_scenario(
        tmp_path, source, fail_apply=True
    )

    assert result.returncode != 0
    assert "Configure Telemt while stopped" in result.stdout
    assert service_log.read_text().splitlines() == ["stopped:pending", "started"]


def test_clean_swap_is_created_activated_and_persisted(tmp_path: Path) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    result = _run_swap_scenario(tmp_path, scenario)
    assert result.returncode == 0, result.stderr + result.stdout
    assert scenario["canonical"].stat().st_size == 1_048_576
    assert scenario["canonical"].stat().st_mode & 0o777 == 0o600
    assert scenario["signatures"].read_text().splitlines() == [
        str(scenario["canonical"])
    ]
    assert scenario["active"].read_text().splitlines() == [str(scenario["canonical"])]
    assert scenario["fstab"].read_text().splitlines() == [
        "UUID=root / ext4 defaults 0 1",
        f"{scenario['canonical']} none swap sw 0 0",
    ]


def test_correct_existing_swap_is_accepted_without_reformatting(tmp_path: Path) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    scenario["canonical"].write_bytes(b"\0" * 1_048_576)
    scenario["signatures"].write_text(f"{scenario['canonical']}\n")
    result = _run_swap_scenario(tmp_path, scenario)
    assert result.returncode == 0, result.stderr + result.stdout
    log = scenario["log"].read_text()
    assert "mkswap " not in log
    assert "fallocate " not in log
    assert scenario["active"].read_text().splitlines() == [str(scenario["canonical"])]


@pytest.mark.parametrize("valid_signature", [True, False])
def test_invalid_existing_swap_fails_without_mutation(
    tmp_path: Path,
    valid_signature: bool,
) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    size = 524_288 if valid_signature else 1_048_576
    scenario["canonical"].write_bytes(b"\0" * size)
    if valid_signature:
        scenario["signatures"].write_text(f"{scenario['canonical']}\n")
    result = _run_swap_scenario(tmp_path, scenario)
    assert result.returncode != 0
    assert "Validate existing canonical swap" in result.stdout
    assert scenario["canonical"].stat().st_size == size
    assert "mkswap " not in scenario["log"].read_text()
    assert "fallocate " not in scenario["log"].read_text()


def test_unexpected_active_swap_fails_visibly(tmp_path: Path) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    scenario["canonical"].write_bytes(b"\0" * 1_048_576)
    scenario["signatures"].write_text(f"{scenario['canonical']}\n")
    scenario["active"].write_text(f"{scenario['canonical']}\n/dev/unexpected\n")
    result = _run_swap_scenario(tmp_path, scenario)
    assert result.returncode != 0
    assert "Require no unexpected active swap before changes" in result.stdout
    assert scenario["active"].read_text().splitlines() == [
        str(scenario["canonical"]),
        "/dev/unexpected",
    ]
    assert scenario["fstab"].read_text() == "UUID=root / ext4 defaults 0 1\n"
    assert all(
        not line.startswith(("fallocate ", "mkswap ", "swapon /"))
        for line in scenario["log"].read_text().splitlines()
    )


def test_missing_swap_cannot_already_be_active(tmp_path: Path) -> None:
    scenario = _prepare_swap_scenario(tmp_path)
    scenario["active"].write_text(f"{scenario['canonical']}\n")

    result = _run_swap_scenario(tmp_path, scenario)

    assert result.returncode != 0
    assert "Require no unexpected active swap before changes" in result.stdout
    assert not scenario["canonical"].exists()
    assert scenario["fstab"].read_text() == "UUID=root / ext4 defaults 0 1\n"


def test_snapshot_must_exist_and_is_protected(tmp_path: Path) -> None:
    success, snapshot = _run_snapshot_scenario(tmp_path, exists=True)
    assert success.returncode == 0, success.stderr + success.stdout
    assert snapshot.read_text() == "snapshot\n"
    assert snapshot.stat().st_mode & 0o777 == 0o640
    missing_dir = tmp_path / "missing"
    missing_dir.mkdir()
    failure, missing = _run_snapshot_scenario(missing_dir, exists=False)
    assert failure.returncode != 0
    assert "Wait for Telemt beobachten snapshot" in failure.stdout
    assert not missing.exists()


def test_fastapi_start_uses_stable_project_without_orphan_cleanup(
    tmp_path: Path,
) -> None:
    result, invocation_path = _run_fastapi_start_task(tmp_path)
    assert result.returncode == 0, result.stderr + result.stdout
    assert json.loads(invocation_path.read_text()) == {
        "argv": ["compose", "--project-name", "mtproto", "up", "-d", "--build", "api"],
        "cwd": str(tmp_path / "app"),
    }


def _compose_config(compose_file: Path) -> dict:
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "config", "--format", "json"],
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
    assert config["services"]["api"]["extra_hosts"] == [
        "host.docker.internal=host-gateway"
    ]


def test_local_compose_runs_pinned_telemt_without_net_admin() -> None:
    config = _compose_config(PROJECT_ROOT / "docker-compose.local.yaml")
    telemt = config["services"]["telemt"]
    assert telemt["image"] == "telemt:3.4.25"
    assert telemt["cap_add"] == ["NET_BIND_SERVICE"]
    assert (
        config["services"]["api"]["environment"]["TELEMT_API_ROOT"]
        == "http://telemt:9091/v1"
    )


def test_systemd_unit_is_minimally_privileged(tmp_path: Path) -> None:
    unit_path = tmp_path / "telemt.service"
    template_path = ROOT / "roles/mtproto_deploy/templates/telemt.service.j2"
    playbook = tmp_path / "render-telemt-unit.yml"
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
    - name: Render production unit
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
    assert "AmbientCapabilities=CAP_NET_BIND_SERVICE" in unit
    assert "CapabilityBoundingSet=CAP_NET_BIND_SERVICE" in unit
    assert "CAP_NET_ADMIN" not in unit
    assert "UMask=0027" in unit


def test_deploy_playbook_syntax(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment["ANSIBLE_LOCAL_TEMP"] = str(tmp_path / "ansible-local")
    result = subprocess.run(
        [
            "ansible-playbook",
            "-i",
            str(ROOT / "inventory.example.ini"),
            str(ROOT / "playbook.yml"),
            "--syntax-check",
        ],
        cwd=ROOT,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr + result.stdout
