import pytest
from fastapi.testclient import TestClient

from src import config
from src.app import app


@pytest.fixture(autouse=True)
def _set_telemt_api_root(monkeypatch):
    monkeypatch.setattr(config, "TELEMT_API_ROOT", "http://172.17.0.1:9091/v1")


@pytest.fixture
def http_client() -> TestClient:
    return TestClient(app=app, base_url="http://127.0.0.1:8080/api")
