import logging
from dataclasses import dataclass

import httpx

from src import config
from src.api.schemas import AddNewUserResponse

logger = logging.getLogger(__name__)


@dataclass(kw_only=True, slots=True, frozen=True)
class AddUserService:
    """Регистрирует нового пользователя на MTProto-прокси через telemt API.

    Создаёт учётную запись с переданным секретом и ограничением
    в 3 одновременных уникальных IP-адреса (≈ 3 устройства).
    Возвращает параметры подключения, из которых внешний сервис
    формирует tg:// ссылку для клиента.
    """

    username: str
    secret: str

    async def __call__(self) -> AddNewUserResponse:
        async with httpx.AsyncClient(base_url=config.TELEMT_API_ROOT) as client:
            response = await client.post(
                url="/users",
                json={
                    "username": self.username,
                    "secret": self.secret,
                    "max_unique_ips": 3,
                },
            )
            response.raise_for_status()

        return AddNewUserResponse(
            tls_domain=config.TLS_DOMAIN,
            key=self.secret,
        )
