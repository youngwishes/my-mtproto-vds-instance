import logging
from dataclasses import dataclass

import aiofiles
import toml

from src import config

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, slots=True, frozen=True)
class RemoveUserService:
    usernames: list[str]

    async def __call__(self) -> None:
        async with aiofiles.open(
            config.TELEMT_TOML_PATH, "r", encoding="utf-8"
        ) as file:
            content = await file.read()
            toml_file = toml.loads(content)
        self._remove_user(toml_file)

    def _remove_user(self, toml_file: dict) -> None:
        for username in self.usernames:
            if username in toml_file["access"]["users"]:
                del toml_file["access"]["users"][username]

            if username in toml_file["access"]["user_max_tcp_conns"]:
                del toml_file["access"]["user_max_tcp_conns"][username]

            if username in toml_file["access"]["user_max_unique_ips"]:
                del toml_file["access"]["user_max_unique_ips"][username]

            if username in toml_file["show_link"]:
                toml_file["show_link"].remove(username)

        with open(config.TELEMT_TOML_PATH, "w", encoding="utf-8") as f:
            toml.dump(toml_file, f)
