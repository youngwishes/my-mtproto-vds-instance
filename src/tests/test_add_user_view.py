from fastapi.testclient import TestClient
from starlette import status

from src import config
from src.tests.utils import get_toml_file_data


def test_bad_body(http_client: TestClient):
    response = http_client.post("/add-new-user")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_add_new_user_schema(http_client: TestClient):
    username = "John"
    response = http_client.post("/add-new-user", json={"username": username})
    assert response.json().get("key")
    assert response.json().get("tls_domain") == config.TLS_DOMAIN


def test_add_new_user(http_client: TestClient):
    toml_file_data = get_toml_file_data()

    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 1
    application_key = toml_file_data["access"]["users"]["application"]

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 1
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0

    username = "John"
    response = http_client.post("/add-new-user", json={"username": username})
    john_key = response.json()["key"]

    assert response.status_code == status.HTTP_200_OK

    toml_file_data = get_toml_file_data()

    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 2
    assert toml_file_data["access"]["users"]["application"] == application_key
    assert toml_file_data["access"]["users"][username] == john_key

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 2
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0
    assert toml_file_data["access"]["user_max_unique_ips"][username] == 3


def test_add_new_user_duplicate(http_client: TestClient):
    toml_file_data = get_toml_file_data()

    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 1
    application_key = toml_file_data["access"]["users"]["application"]

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 1
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0

    username = "John"
    response = http_client.post("/add-new-user", json={"username": username})
    john_key = response.json()["key"]
    assert response.status_code == status.HTTP_200_OK

    toml_file_data = get_toml_file_data()

    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 2
    assert toml_file_data["access"]["users"]["application"] == application_key
    assert toml_file_data["access"]["users"][username] == john_key

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 2
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0
    assert toml_file_data["access"]["user_max_unique_ips"][username] == 3

    response = http_client.post("/add-new-user", json={"username": username})
    john_key = response.json()["key"]
    assert response.status_code == status.HTTP_200_OK
    toml_file_data = get_toml_file_data()

    assert len(toml_file_data["show_link"]) == 1
    assert toml_file_data["show_link"][0] == "application"

    assert len(toml_file_data["access"]["users"]) == 2
    assert toml_file_data["access"]["users"]["application"] == application_key
    assert toml_file_data["access"]["users"][username] == john_key

    assert len(toml_file_data["access"]["user_max_tcp_conns"]) == 1
    assert toml_file_data["access"]["user_max_tcp_conns"]["application"] == 0

    assert len(toml_file_data["access"]["user_max_unique_ips"]) == 2
    assert toml_file_data["access"]["user_max_unique_ips"]["application"] == 0
    assert toml_file_data["access"]["user_max_unique_ips"][username] == 3
