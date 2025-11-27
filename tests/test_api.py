"""
API endpoint tests
"""
import pytest
from fastapi.testclient import TestClient
from src.api.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    assert "status" in response.json()
    assert response.json()["status"] == "healthy"


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert "message" in response.json()


def test_list_clients():
    response = client.get("/api/clients")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_register_client_invalid():
    response = client.post("/api/clients/register", json={})
    assert response.status_code == 422

