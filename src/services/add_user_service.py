import os
from dataclasses import dataclass

import aiofiles
import toml

from src import config
from src.api.schemas import AddNewUserResponse


@dataclass(kw_only=True, slots=True, frozen=True)
class AddUserService:
    username: str

    async def __call__(self) -> AddNewUserResponse:
        async with aiofiles.open(
            config.TELEMT_TOML_PATH, "r", encoding="utf-8"
        ) as file:
            content = await file.read()
            toml_file = toml.loads(content)
        key = await self._add_user(toml_file)
        return AddNewUserResponse(tls_domain=config.TLS_DOMAIN, key=key)

    async def _add_user(self, toml_file: dict) -> str:
        key = str(os.urandom(16).hex())
        toml_file["access"]["users"][self.username] = key
        toml_file["access"]["user_max_tcp_conns"][self.username] = 50
        toml_file["access"]["user_max_unique_ips"][self.username] = 3
        with open(config.TELEMT_TOML_PATH, "w", encoding="utf-8") as f:
            toml.dump(toml_file, f)
        return key
