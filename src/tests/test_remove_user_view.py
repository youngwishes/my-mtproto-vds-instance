from fastapi.testclient import TestClient
from starlette import status

from src import config
from src.tests.utils import get_toml_file_data


def test_bad_body(http_client: TestClient):
    response = http_client.post("/remove-user")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_remove_user_service(http_client: TestClient):
    toml_file_data = get_toml_file_data()
    key1 = toml_file_data["access"]["users"]["application"]
    username = "John"
    response = http_client.post("/add-new-user", json={"username": username})
    assert response.status_code == status.HTTP_200_OK

    assert response.json().get("key")
    assert response.json().get("tls_domain") == config.TLS_DOMAIN

    response = http_client.post("/remove-user", json={"usernames": [username]})
    assert response.status_code == status.HTTP_204_NO_CONTENT

    toml_file_data = get_toml_file_data()
    key2 = toml_file_data["access"]["users"]["application"]

    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 1
    assert toml_file_data["access"]["users"]["application"]

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 1
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0

    response = http_client.post("/remove-user", json={"usernames": [username]})
    assert response.status_code == status.HTTP_204_NO_CONTENT

    toml_file_data = get_toml_file_data()
    key3 = toml_file_data["access"]["users"]["application"]
    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 1
    assert toml_file_data["access"]["users"]["application"]

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 1
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0

    assert key1 == key2 == key3


def test_remove_user_service_many(http_client: TestClient):
    toml_file_data = get_toml_file_data()
    assert toml_file_data["access"]["users"]["application"]
    username = "John"
    response = http_client.post("/add-new-user", json={"username": username})
    assert response.status_code == status.HTTP_200_OK
    assert response.json().get("key")
    assert response.json().get("tls_domain") == config.TLS_DOMAIN

    response = http_client.post(
        "/remove-user", json={"usernames": [username, "application"]}
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT

    toml_file_data = get_toml_file_data()

    assert len(toml_file_data["show_link"]) == 0
    assert len(toml_file_data["access"]["users"]) == 0
    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 0
    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 0
