from dataclasses import dataclass

import httpx

from src import config
from src.api.schemas import AddNewUserResponse


@dataclass(kw_only=True, slots=True, frozen=True)
class AddUserServiceV2:
    username: str
    secret: str

    async def __call__(self) -> AddNewUserResponse:
        async with httpx.AsyncClient(base_url=config.TELEMT_API_ROOT) as client:
            try:
                response = await client.post(
                    url="/users",
                    json={
                        "username": self.username,
                        "secret": self.secret,
                        "max_unique_ips": 3,
                    },
                )
                response.raise_for_status()
            except Exception as exc:
                error_data = response.json()
                if error_data.get("error").get("code") == "user_exists":
                    await client.delete(
                        url=f"/users/{self.username.lower()}",
                    )
                    await client.post(
                        url="/users",
                        json={
                            "username": self.username,
                            "secret": self.secret,
                            "max_unique_ips": 3,
                        },
                    )

        return AddNewUserResponse(
            tls_domain=config.TLS_DOMAIN,
            key=self.secret,
            node_number=config.NODE_NUMBER,
        )
