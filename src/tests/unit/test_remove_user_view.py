from fastapi.testclient import TestClient
from starlette import status


def test_remove_user_bad_body(http_client: TestClient):
    response = http_client.request("DELETE", "/users")
    assert response.status_code == status.HTTP_422_UNPROCESSABLE_CONTENT


def test_remove_single_user(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=204,
        method="DELETE",
        url="http://172.17.0.1:9091/v1/users/john",
    )

    response = http_client.request(
        "DELETE",
        "/users",
        json={"usernames": ["John"]},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT


def test_remove_multiple_users(http_client: TestClient, httpx_mock):
    httpx_mock.add_response(
        status_code=204,
        method="DELETE",
        url="http://172.17.0.1:9091/v1/users/alice",
    )
    httpx_mock.add_response(
        status_code=204,
        method="DELETE",
        url="http://172.17.0.1:9091/v1/users/bob",
    )

    response = http_client.request(
        "DELETE",
        "/users",
        json={"usernames": ["Alice", "Bob"]},
    )
    assert response.status_code == status.HTTP_204_NO_CONTENT
