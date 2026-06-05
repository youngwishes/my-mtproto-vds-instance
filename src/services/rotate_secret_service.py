import logging
from dataclasses import dataclass

import httpx

from src import config
from src.api.schemas import AddNewUserResponse

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, slots=True, frozen=True)
class RotateSecretService:
    """Перевыпускает секрет (ссылку) пользователя на MTProto-прокси.

    Используется когда клиент хочет инвалидировать текущую ссылку —
    например, если она была скомпрометирована (отправлена в общий чат)
    и по ней подключились посторонние. После ротации старая ссылка
    перестаёт работать, клиент получает новые параметры подключения.
    """

    username: str
    secret: str

    async def __call__(self) -> AddNewUserResponse:
        async with httpx.AsyncClient(base_url=config.TELEMT_API_ROOT) as client:
            response = await client.patch(
                url=f"/users/{self.username.lower()}",
                json={"secret": self.secret},
            )
            response.raise_for_status()

        return AddNewUserResponse(
            tls_domain=config.TLS_DOMAIN,
            key=self.secret,
        )
