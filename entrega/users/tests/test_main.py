import importlib

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    seed_file = tmp_path / "users_seed.json"
    data_file = tmp_path / "users.json"
    seed_file.write_text("[]", encoding="utf-8")

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DATA_FILE", str(data_file))
    monkeypatch.setenv("SEED_FILE", str(seed_file))

    import auth
    import main

    importlib.reload(auth)
    importlib.reload(main)

    return TestClient(main.app)


def test_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_register_creates_user_with_role_user(client):
    response = client.post(
        "/users/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "secret123"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "user"
    assert body["email"] == "alice@example.com"
    assert "passwordHash" not in body


def test_register_duplicate_email_returns_409(client):
    payload = {"name": "Alice", "email": "alice@example.com", "password": "secret123"}
    client.post("/users/register", json=payload)

    response = client.post("/users/register", json=payload)

    assert response.status_code == 409


def test_login_with_valid_credentials_returns_token(client):
    client.post(
        "/users/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "secret123"},
    )

    response = client.post(
        "/users/login", json={"email": "alice@example.com", "password": "secret123"}
    )

    assert response.status_code == 200
    assert "token" in response.json()


def test_login_with_invalid_password_returns_401(client):
    client.post(
        "/users/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "secret123"},
    )

    response = client.post(
        "/users/login", json={"email": "alice@example.com", "password": "wrong"}
    )

    assert response.status_code == 401


def test_get_user_requires_token(client):
    register = client.post(
        "/users/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "secret123"},
    )
    user_id = register.json()["id"]

    response = client.get(f"/users/{user_id}")

    assert response.status_code in (401, 403)


def test_get_user_returns_user_data_with_valid_token(client):
    register = client.post(
        "/users/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "secret123"},
    )
    user_id = register.json()["id"]
    login = client.post(
        "/users/login", json={"email": "alice@example.com", "password": "secret123"}
    )
    token = login.json()["token"]

    response = client.get(
        f"/users/{user_id}", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 200
    assert response.json()["email"] == "alice@example.com"


def test_get_user_not_found_returns_404(client):
    client.post(
        "/users/register",
        json={"name": "Alice", "email": "alice@example.com", "password": "secret123"},
    )
    login = client.post(
        "/users/login", json={"email": "alice@example.com", "password": "secret123"}
    )
    token = login.json()["token"]

    response = client.get(
        "/users/does-not-exist", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 404
