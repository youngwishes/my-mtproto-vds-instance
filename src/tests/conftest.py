import pytest
from fastapi.testclient import TestClient

import toml
from src import config
from src.app import app


@pytest.fixture(scope="function")
def prepare_toml_file() -> dict | None:
    with open(config.TELEMT_TOML_PATH, "r", encoding="utf-8") as file:
        toml_file = toml.loads(file.read())

    toml_config = {
        "show_link": ["application"],

        "general": {
            "prefer_ipv6": False,
            "fast_mode": True,
            "use_middle_proxy": False,
            "modes": {
                "classic": False,
                "secure": False,
                "tls": True
            }
        },

        "server": {
            "port": 443,
            "listen_addr_ipv4": "0.0.0.0",
            "listen_addr_ipv6": "::"
        },

        "censorship": {
            "tls_domain": config.TLS_DOMAIN,
            "mask": True,
            "mask_port": 443,
            "fake_cert_len": 2048
        },

        "access": {
            "users": {"application": "f7500d69d0479eb1c90454490aa7096d"},
            "user_max_tcp_conns": {"application": 0},
            "user_max_unique_ips": {"application": 0},
        },

        "upstreams": [
            {
                "type": "direct",
                "enabled": True,
                "weight": 10
            }
        ]
    }

    with open(config.TELEMT_TOML_PATH, "w", encoding="utf-8") as f:
        toml.dump(toml_config, f)

    return toml_file


@pytest.fixture
def http_client(prepare_toml_file) -> TestClient:
    return TestClient(app=app, base_url="http://127.0.0.1:8000/api/v1")
