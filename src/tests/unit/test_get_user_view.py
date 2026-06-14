from fastapi.testclient import TestClient
from starlette import status


TLS_LINK = (
    "tg://proxy?server=172.18.0.3&port=443"
    "&secret=eed6a142b8536d7f6574753ace924b75c4706574726f766963682e7275"
)

TELEMT_USER_INFO_RESPONSE = {
    "ok": True,
    "data": {
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
        "links": {"classic": [], "secure": [], "tls": [TLS_LINK]},
    },
    "revision": "abc123",
}


def test_get_user_when_exists_returns_200(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=200,
        json=TELEMT_USER_INFO_RESPONSE,
        method="GET",
        url="http://172.17.0.1:9091/v1/users/john",
    )

    response = http_client.get("/users/John")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == {"username": "john", "link": TLS_LINK}


def test_get_user_when_not_found_returns_404(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=404,
        json={"ok": False, "error": {"code": "not_found", "message": "User not found"}},
        method="GET",
        url="http://172.17.0.1:9091/v1/users/john",
    )

    response = http_client.get("/users/John")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert response.json() == {"detail": "User not found"}
