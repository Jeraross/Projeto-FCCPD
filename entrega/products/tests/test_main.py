import importlib
import json

import pytest
from fastapi.testclient import TestClient

SEED_PRODUCTS = [
    {
        "id": "seed-1",
        "name": "Pizza Margherita",
        "description": "Molho de tomate, mussarela, manjericao fresco",
        "price": 35.0,
        "createdAt": "2026-01-01T00:00:00+00:00",
        "updatedAt": "2026-01-01T00:00:00+00:00",
    }
]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    seed_file = tmp_path / "products_seed.json"
    data_file = tmp_path / "products.json"
    seed_file.write_text(json.dumps(SEED_PRODUCTS), encoding="utf-8")

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DATA_FILE", str(data_file))
    monkeypatch.setenv("SEED_FILE", str(seed_file))

    import auth
    import main

    importlib.reload(auth)
    importlib.reload(main)

    return TestClient(main.app), auth.create_access_token


def test_health(client):
    test_client, _ = client
    response = test_client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_list_products_returns_seed_data(client):
    test_client, _ = client
    response = test_client.get("/products")
    assert response.status_code == 200
    assert response.json() == SEED_PRODUCTS


def test_get_product_by_id(client):
    test_client, _ = client
    response = test_client.get("/products/seed-1")
    assert response.status_code == 200
    assert response.json()["name"] == "Pizza Margherita"


def test_get_product_not_found_returns_404(client):
    test_client, _ = client
    response = test_client.get("/products/does-not-exist")
    assert response.status_code == 404


def test_create_product_requires_token(client):
    test_client, _ = client
    response = test_client.post(
        "/products",
        json={"name": "Pizza Teste", "description": "...", "price": 10.0},
    )
    assert response.status_code in (401, 403)


def test_create_product_requires_admin_role(client):
    test_client, create_access_token = client
    token = create_access_token("user-1", "alice@example.com", "user")

    response = test_client.post(
        "/products",
        json={"name": "Pizza Teste", "description": "...", "price": 10.0},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_create_product_as_admin_creates_and_persists(client):
    test_client, create_access_token = client
    token = create_access_token("admin-1", "admin@pizzaria.com", "admin")

    response = test_client.post(
        "/products",
        json={"name": "Pizza Teste", "description": "Sabor de teste", "price": 19.9},
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "Pizza Teste"
    assert "id" in body

    list_response = test_client.get("/products")
    names = [p["name"] for p in list_response.json()]
    assert "Pizza Teste" in names


def test_create_product_with_explicit_id_uses_given_id(client):
    test_client, create_access_token = client
    token = create_access_token("admin-1", "admin@pizzaria.com", "admin")

    response = test_client.post(
        "/products",
        json={
            "id": "fixed-id-123",
            "name": "Pizza Replicada",
            "description": "...",
            "price": 29.9,
        },
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 201
    assert response.json()["id"] == "fixed-id-123"

    get_response = test_client.get("/products/fixed-id-123")
    assert get_response.status_code == 200
