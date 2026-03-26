import logging
from dataclasses import dataclass
import httpx

from src import config

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, slots=True, frozen=True)
class RemoveUserServiceV2:
    usernames: list[str]

    async def __call__(self) -> None:
        for username in self.usernames:
            async with httpx.AsyncClient(base_url=config.TELEMT_API_ROOT) as client:
                await client.delete(
                    url=f"/users/{username.lower()}",
                )
