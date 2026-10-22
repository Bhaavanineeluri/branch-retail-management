from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from dependencies import get_current_user
from main import app
from models import UserRole


@pytest.fixture
def client():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=999999,
        email="staff-test@example.com",
        role=UserRole.STAFF,
        is_active=True,
    )

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", "/api/audit-logs", None),
        ("post", "/api/categories", {"name": "Test Category"}),
        ("post", "/api/products", {}),
        ("post", "/api/suppliers", {}),
        ("post", "/api/warehouses", {}),
        ("post", "/api/inventory/1/1/increase", {}),
        ("post", "/api/purchase-orders", {}),
        ("post", "/api/sales-orders", {}),
        ("post", "/api/stock-transfers", {}),
        ("post", "/api/product-returns", {}),
    ],
)
def test_staff_cannot_access_restricted_operations(
    client, method, path, payload
):
    request_method = getattr(client, method)

    if payload is None:
        response = request_method(path)
    else:
        response = request_method(path, json=payload)

    assert response.status_code == 403, (
        f"{method.upper()} {path}: expected 403, "
        f"received {response.status_code}: {response.text}"
    )
