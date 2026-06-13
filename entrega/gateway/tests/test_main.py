import importlib
import json

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def gateway(monkeypatch):
    monkeypatch.setenv("USERS_URL", "http://users:5001")
    monkeypatch.setenv("ORDERS_URL", "http://orders:5003")
    monkeypatch.setenv("PRODUCTS_URLS", "http://products-1:5002,http://products-2:5012")
    monkeypatch.setenv("HEARTBEAT_FAILURE_THRESHOLD", "2")

    import main

    importlib.reload(main)

    return main


def _install_mock_transport(main, handler):
    mock_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    main.http_client = mock_client
    main.products_router.client = mock_client


def test_dashboard_status_lists_all_instances(gateway):
    client = TestClient(gateway.app)

    response = client.get("/dashboard/status")

    assert response.status_code == 200
    names = [s["name"] for s in response.json()["services"]]
    assert names == ["users", "orders", "products", "products"]


def test_users_proxy_forwards_request_when_up(gateway):
    async def handler(request):
        assert request.url.path == "/users/42"
        assert request.headers.get("authorization") == "Bearer abc"
        return httpx.Response(200, json={"id": "42", "name": "Alice"})

    _install_mock_transport(gateway, handler)
    for instance in gateway.registry.instances:
        instance.status = "UP"

    client = TestClient(gateway.app)
    response = client.get("/users/42", headers={"Authorization": "Bearer abc"})

    assert response.status_code == 200
    assert response.json() == {"id": "42", "name": "Alice"}


def test_users_proxy_returns_503_when_users_service_down(gateway):
    for instance in gateway.registry.instances:
        if instance.name == "users":
            instance.status = "DOWN"

    client = TestClient(gateway.app)
    response = client.get("/users/42", headers={"Authorization": "Bearer abc"})

    assert response.status_code == 503
    assert "indisponivel" in response.json()["error"]


def test_orders_create_proxy_forwards_post_request(gateway):
    async def handler(request):
        assert request.url.path == "/orders"
        return httpx.Response(201, json={"id": "order-1"})

    _install_mock_transport(gateway, handler)
    for instance in gateway.registry.instances:
        instance.status = "UP"

    client = TestClient(gateway.app)
    response = client.post(
        "/orders",
        json={"productId": "p1", "quantity": 1},
        headers={"Authorization": "Bearer abc"},
    )

    assert response.status_code == 201
    assert response.json() == {"id": "order-1"}


def test_orders_get_proxy_forwards_to_user_path(gateway):
    async def handler(request):
        assert request.url.path == "/orders/user-1"
        return httpx.Response(200, json=[])

    _install_mock_transport(gateway, handler)
    for instance in gateway.registry.instances:
        instance.status = "UP"

    client = TestClient(gateway.app)
    response = client.get("/orders/user-1", headers={"Authorization": "Bearer abc"})

    assert response.status_code == 200


def test_products_get_round_robins_between_replicas(gateway):
    seen_hosts = []

    async def handler(request):
        seen_hosts.append(request.url.host)
        return httpx.Response(200, json=[])

    _install_mock_transport(gateway, handler)
    for instance in gateway.registry.instances:
        instance.status = "UP"

    client = TestClient(gateway.app)
    client.get("/products")
    client.get("/products")

    assert seen_hosts == ["products-1", "products-2"]


def test_products_get_returns_503_when_all_replicas_down(gateway):
    for instance in gateway.registry.instances:
        if instance.name == "products":
            instance.status = "DOWN"

    client = TestClient(gateway.app)
    response = client.get("/products")

    assert response.status_code == 503


def test_create_product_returns_503_when_a_replica_is_down(gateway):
    for instance in gateway.registry.instances:
        instance.status = "UP"
    gateway.registry.instances[-1].status = "DOWN"

    client = TestClient(gateway.app)
    response = client.post(
        "/products",
        json={"name": "Pizza Teste", "description": "...", "price": 10.0},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 503


def test_create_product_writes_to_both_replicas(gateway):
    received = []

    async def handler(request):
        received.append(request.url.host)
        body = json.loads(request.content)
        return httpx.Response(201, json=body)

    _install_mock_transport(gateway, handler)
    for instance in gateway.registry.instances:
        instance.status = "UP"

    client = TestClient(gateway.app)
    response = client.post(
        "/products",
        json={"name": "Pizza Teste", "description": "...", "price": 10.0},
        headers={"Authorization": "Bearer admin-token"},
    )

    assert response.status_code == 201
    assert received == ["products-1", "products-2"]
