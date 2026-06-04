from fastapi.testclient import TestClient
from starlette import status

from src import config


TELEMT_ROTATE_SECRET_RESPONSE = {
    "ok": True,
    "data": {
        "user": {
            "username": "john",
            "user_ad_tag": None,
            "max_tcp_conns": None,
            "expiration_rfc3339": None,
            "data_quota_bytes": None,
            "max_unique_ips": 3,
            "current_connections": 0,
            "active_unique_ips": 0,
            "active_unique_ips_list": [],
            "recent_unique_ips": 0,
            "recent_unique_ips_list": [],
            "total_octets": 0,
            "links": {
                "classic": [],
                "secure": [],
                "tls": [
                    "tg://proxy?server=172.18.0.3&port=443&secret=eeabcdef12345678abcdef12345678ab706574726f766963682e7275",
                ]
            }
        },
        "secret": "abcdef12345678abcdef12345678ab00"
    },
    "revision": "abc123"
}


def test_rotate_secret_bad_body(http_client: TestClient):
    response = http_client.patch("/users")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_rotate_secret(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=200,
        json=TELEMT_ROTATE_SECRET_RESPONSE,
        method="POST",
        url="http://172.17.0.1:9091/v1/users/john/rotate-secret",
    )

    response = http_client.patch(
        "/users",
        json={"username": "John", "secret": "new_secret"},
    )
    assert response.status_code == status.HTTP_200_OK
    assert response.json().get("key") == "new_secret"
    assert response.json().get("tls_domain") == config.TLS_DOMAIN
    assert response.json().get("node_number") == config.NODE_NUMBER
