from fastapi.testclient import TestClient
from starlette import status

from src import config


TELEMT_SUCESS_RESPONSE = {
    "ok": True,
    "data": {
        "user": {
            "username": "test",
            "user_ad_tag": None,
            "max_tcp_conns": None,
            "expiration_rfc3339": None,
            "data_quota_bytes": None,
            "max_unique_ips": None,
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
                    "tg://proxy?server=172.18.0.3&port=443&secret=eed6a142b8536d7f6574753ace924b75c4706574726f766963682e7275",
                    "tg://proxy?server=::&port=443&secret=eed6a142b8536d7f6574753ace924b75c4706574726f766963682e7275"
                ]
            }
        },
        "secret": "d6a142b8536d7f6574753ace924b75c4"
    },
    "revision": "fea1481b3dc2a4d6cab1073b13b197c0417ffee31f09465756d50b7036e58ed2"
}


TELEMT_CONFLICT_RESPONSE = {
    "ok": False,
    "error": {
        "code": "user_exists",
        "message": "User already exists"
    },
    "request_id": 4
}



def test_bad_body(http_client: TestClient):
    response = http_client.post("/users/add")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_add_new_user_schema(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=200,
        json=TELEMT_SUCESS_RESPONSE,
    )

    username = "John"
    response = http_client.post(
        "/users/add", json={"username": username, "secret": "test"}
    )
    assert response.json().get("key") == "test"
    assert response.json().get("tls_domain") == config.TLS_DOMAIN


def test_add_new_user_if_exists(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=409,
        json=TELEMT_CONFLICT_RESPONSE,
        method="POST",
        url="http://172.17.0.1:9091/v1/users"
    )
    httpx_mock.add_response(
        status_code=204,
        method="DELETE",
        url="http://172.17.0.1:9091/v1/users/john"
    )
    httpx_mock.add_response(
        status_code=200,
        json=TELEMT_SUCESS_RESPONSE,
        method="POST",
        url="http://172.17.0.1:9091/v1/users"
    )

    username = "John"
    response = http_client.post(
        "/users/add", json={"username": username, "secret": "test"}
    )
    assert response.json().get("key") == "test"
    assert response.json().get("tls_domain") == config.TLS_DOMAIN

