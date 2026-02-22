from src.api.routes import router
from contextlib import asynccontextmanager

import aiofiles
import toml
from fastapi import FastAPI

from src import config



async def prepare_toml_file() -> dict | None:
    async with aiofiles.open(config.TELEMT_TOML_PATH, "r", encoding="utf-8") as file:
        content = await file.read()
        toml_file = toml.loads(content)

    if toml_file.get("show_link", []):
        return None

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


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Starting up... Preparing TOML configuration")
    try:
        await prepare_toml_file()
        print("✅ TOML configuration prepared successfully")
    except Exception as e:
        print(f"❌ Failed to prepare TOML configuration: {e}")
        raise

    yield

    print("🛑 Shutting down...")


app = FastAPI(title="MTProto Management API", lifespan=lifespan)

app.include_router(router)
