import os
import uuid

import httpx
from starlette import status

from .conftest import requires_containers


def _random_user() -> dict:
    return {
        "username": str(uuid.uuid4()),
        "secret": os.urandom(16).hex(),
    }


@requires_containers
class TestAddUser:
    def test_success(self, api: httpx.Client):
        user = _random_user()
        response = api.post("/users", json=user)

        assert response.status_code == status.HTTP_200_OK

        body = response.json()
        assert body["key"] == user["secret"]
        assert body["tls_domain"]

        api.request("DELETE", "/users", json={"usernames": [user["username"]]})

    def test_missing_body(self, api: httpx.Client):
        response = api.post("/users")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@requires_containers
class TestRotateSecret:
    def test_success(self, api: httpx.Client):
        user = _random_user()
        api.post("/users", json=user)

        new_secret = os.urandom(16).hex()
        response = api.patch(
            "/users",
            json={"username": user["username"], "secret": new_secret},
        )

        assert response.status_code == status.HTTP_200_OK
        assert response.json()["key"] == new_secret

        api.request("DELETE", "/users", json={"usernames": [user["username"]]})

    def test_missing_body(self, api: httpx.Client):
        response = api.patch("/users")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


@requires_containers
class TestRemoveUser:
    def test_single(self, api: httpx.Client):
        user = _random_user()
        api.post("/users", json=user)

        response = api.request("DELETE", "/users", json={"usernames": [user["username"]]})

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_multiple(self, api: httpx.Client):
        users = [_random_user() for _ in range(3)]
        for u in users:
            api.post("/users", json=u)

        usernames = [u["username"] for u in users]
        response = api.request("DELETE", "/users", json={"usernames": usernames})

        assert response.status_code == status.HTTP_204_NO_CONTENT

    def test_missing_body(self, api: httpx.Client):
        response = api.request("DELETE", "/users")

        assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT
