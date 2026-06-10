import importlib

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    data_file = tmp_path / "orders.json"

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DATA_FILE", str(data_file))
    monkeypatch.setenv("PRODUCTS_URL", "http://products.test")

    import auth
    import main

    importlib.reload(auth)
    importlib.reload(main)

    return TestClient(main.app), auth.create_access_token, main


class _FakeResponse:
    def __init__(self, status_code, json_data=None):
        self.status_code = status_code
        self._json_data = json_data or {}

    def json(self):
        return self._json_data


def _mock_product(monkeypatch, main, status_code=200, json_data=None):
    monkeypatch.setattr(
        main.httpx, "get", lambda *a, **k: _FakeResponse(status_code, json_data)
    )


def test_health(client):
    test_client, _, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_create_order_requires_token(client):
    test_client, _, _ = client
    response = test_client.post("/orders", json={"productId": "p1", "quantity": 2})
    assert response.status_code in (401, 403)


def test_create_order_returns_404_when_product_missing(client, monkeypatch):
    test_client, create_access_token, main = client
    _mock_product(monkeypatch, main, status_code=404)
    token = create_access_token("user-1", "alice@example.com", "user")

    response = test_client.post(
        "/orders",
        json={"productId": "does-not-exist", "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 404


def test_create_order_returns_502_when_products_service_unreachable(client, monkeypatch):
    test_client, create_access_token, main = client

    def raise_error(*args, **kwargs):
        raise httpx.ConnectError("boom")

    monkeypatch.setattr(main.httpx, "get", raise_error)
    token = create_access_token("user-1", "alice@example.com", "user")

    response = test_client.post(
        "/orders",
        json={"productId": "p1", "quantity": 1},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 502


def test_create_order_succeeds_and_computes_total(client, monkeypatch):
    test_client, create_access_token, main = client
    _mock_product(
        monkeypatch,
        main,
        status_code=200,
        json_data={"id": "p1", "name": "Pizza Margherita", "price": 35.0},
    )
    token = create_access_token("user-1", "alice@example.com", "user")

    response = test_client.post(
        "/orders",
        json={"productId": "p1", "quantity": 2},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["userId"] == "user-1"
    assert body["productId"] == "p1"
    assert body["productName"] == "Pizza Margherita"
    assert body["unitPrice"] == 35.0
    assert body["quantity"] == 2
    assert body["total"] == 70.0
    assert body["status"] == "created"


def test_list_orders_requires_token(client):
    test_client, _, _ = client
    response = test_client.get("/orders/user-1")
    assert response.status_code in (401, 403)


def test_list_orders_returns_only_own_orders(client, monkeypatch):
    test_client, create_access_token, main = client
    _mock_product(
        monkeypatch,
        main,
        status_code=200,
        json_data={"id": "p1", "name": "Pizza Margherita", "price": 35.0},
    )
    token_user1 = create_access_token("user-1", "alice@example.com", "user")
    token_user2 = create_access_token("user-2", "bob@example.com", "user")

    test_client.post(
        "/orders",
        json={"productId": "p1", "quantity": 1},
        headers={"Authorization": f"Bearer {token_user1}"},
    )
    test_client.post(
        "/orders",
        json={"productId": "p1", "quantity": 3},
        headers={"Authorization": f"Bearer {token_user2}"},
    )

    response = test_client.get(
        "/orders/user-1", headers={"Authorization": f"Bearer {token_user1}"}
    )

    assert response.status_code == 200
    orders = response.json()
    assert len(orders) == 1
    assert orders[0]["userId"] == "user-1"


def test_list_orders_for_other_user_returns_403(client):
    test_client, create_access_token, _ = client
    token_user1 = create_access_token("user-1", "alice@example.com", "user")

    response = test_client.get(
        "/orders/user-2", headers={"Authorization": f"Bearer {token_user1}"}
    )

    assert response.status_code == 403


def test_list_orders_admin_can_view_any_user(client, monkeypatch):
    test_client, create_access_token, main = client
    _mock_product(
        monkeypatch,
        main,
        status_code=200,
        json_data={"id": "p1", "name": "Pizza Margherita", "price": 35.0},
    )
    token_user1 = create_access_token("user-1", "alice@example.com", "user")
    admin_token = create_access_token("admin-1", "admin@pizzaria.com", "admin")

    test_client.post(
        "/orders",
        json={"productId": "p1", "quantity": 1},
        headers={"Authorization": f"Bearer {token_user1}"},
    )

    response = test_client.get(
        "/orders/user-1", headers={"Authorization": f"Bearer {admin_token}"}
    )

    assert response.status_code == 200
    assert len(response.json()) == 1
