import httpx
import pytest

BASE_URL = "http://127.0.0.1:8000/api"


def _api_is_reachable() -> bool:
    try:
        httpx.get(BASE_URL, timeout=2)
        return True
    except httpx.ConnectError:
        return False


requires_containers = pytest.mark.skipif(
    not _api_is_reachable(),
    reason="API containers are not running",
)


@pytest.fixture
def api() -> httpx.Client:
    with httpx.Client(base_url=BASE_URL, timeout=10) as client:
        yield client
