import logging
from dataclasses import dataclass

import httpx

from src import config
from src.api.schemas import GetUserResponse

logger = logging.getLogger(__name__)


# Приоритет режимов подключения при выборе ссылки из ответа telemt.
_LINK_MODES = ("tls", "secure", "classic")


@dataclass(kw_only=True, slots=True, frozen=True)
class GetUserService:
    """Проверяет наличие пользователя в конфиге telemt (telemt.toml).

    Запрашивает у telemt API представление одного пользователя.
    Если пользователь есть в конфиге — telemt возвращает 200 и сервис
    отдаёт его username и tg://-ссылку (в ней зашит секрет). Если
    пользователя нет — telemt возвращает 404, который пробрасывается
    клиенту как есть.

    Сырой секрет telemt на GET не отдаёт, поэтому ссылка извлекается из
    поля `links` ответа по приоритету режимов tls → secure → classic.
    """

    username: str

    async def __call__(self) -> GetUserResponse:
        async with httpx.AsyncClient(base_url=config.TELEMT_API_ROOT) as client:
            response = await client.get(url=f"/users/{self.username.lower()}")
            response.raise_for_status()
            payload = response.json()

        return GetUserResponse(
            username=self.username.lower(),
            link=self._extract_link(payload),
        )

    def _extract_link(self, payload: dict) -> str:
        links = payload.get("data", {}).get("links", {})
        for mode in _LINK_MODES:
            mode_links = links.get(mode) or []
            if mode_links:
                return mode_links[0]
        return ""
