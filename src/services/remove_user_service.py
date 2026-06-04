import logging
from dataclasses import dataclass

import httpx

from src import config

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, slots=True, frozen=True)
class RemoveUserService:
    """Массово удаляет пользователей с MTProto-прокси.

    Вызывается внешним сервисом по расписанию (celery-задача, ежедневно)
    для очистки протухших ключей — ссылок, у которых истёк срок действия
    (обычно 30 дней с момента выдачи).
    """

    usernames: list[str]

    async def __call__(self) -> None:
        async with httpx.AsyncClient(base_url=config.TELEMT_API_ROOT) as client:
            for username in self.usernames:
                await client.delete(url=f"/users/{username.lower()}")
