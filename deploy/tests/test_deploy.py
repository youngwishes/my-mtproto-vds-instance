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
    assert hosts == ["vds1", "vds2", "vds3", "vds5"]


def test_clean_install_uses_netfilter_image_and_builtin_synlimit() -> None:
    result = subprocess.run(
        [
            "docker",
            "compose",
            "-f",
            str(PROJECT_ROOT / "docker-compose.yaml"),
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
    telemt = json.loads(result.stdout)["services"]["telemt"]
    assert telemt["image"] == "telemt-netfilter:3.4.25"
    assert telemt["build"]["target"] == "prod-netfilter"
    assert "NET_ADMIN" in telemt["cap_add"]

    with (PROJECT_ROOT / "telemt" / "telemt.example.toml").open("rb") as file:
        config = tomllib.load(file)
    assert config["server"]["listeners"] == [
        {"ip": "0.0.0.0", "port": 443, "synlimit": "iptables"},
        {"ip": "::", "port": 443, "synlimit": "iptables"},
    ]
