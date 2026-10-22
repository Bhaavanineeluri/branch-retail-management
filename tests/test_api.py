import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_check(client):
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == (
        "Branch Retail Management API is running"
    )


def test_openapi_documentation(client):
    response = client.get("/openapi.json")

    assert response.status_code == 200

    paths = response.json()["paths"]

    assert "/api/auth/register" in paths
    assert "/api/auth/login" in paths
    assert "/api/products" in paths
    assert "/api/inventory" in paths
    assert "/api/purchase-orders" in paths
    assert "/api/sales-orders" in paths
    assert "/api/stock-transfers" in paths
    assert "/api/product-returns" in paths
    assert "/api/reports/low-stock" in paths
    assert "/api/audit-logs" in paths


@pytest.mark.parametrize(
    "path",
    [
        "/api/auth/me",
        "/api/users",
        "/api/categories",
        "/api/products",
        "/api/suppliers",
        "/api/warehouses",
        "/api/inventory",
        "/api/purchase-orders",
        "/api/sales-orders",
        "/api/stock-transfers",
        "/api/product-returns",
        "/api/reports/low-stock",
        "/api/audit-logs",
    ],
)
def test_protected_endpoints_require_authentication(client, path):
    response = client.get(path)

    assert response.status_code == 401, (
        f"{path} returned {response.status_code} without authentication"
    )


def test_register_rejects_invalid_email(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "not-an-email",
            "full_name": "Test User",
            "password": "TestPassword123",
        },
    )

    assert response.status_code == 422


def test_register_rejects_short_password(client):
    response = client.post(
        "/api/auth/register",
        json={
            "email": "pytest-user@example.com",
            "full_name": "Test User",
            "password": "short",
        },
    )

    assert response.status_code == 422


def test_unknown_endpoint_returns_404(client):
    response = client.get("/this-endpoint-does-not-exist")

    assert response.status_code == 404
