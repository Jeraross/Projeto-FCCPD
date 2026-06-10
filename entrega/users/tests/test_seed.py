import importlib
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def seeded_client(tmp_path, monkeypatch):
    data_file = tmp_path / "users.json"
    seed_file = os.path.join(os.path.dirname(__file__), "..", "users_seed.json")

    monkeypatch.setenv("JWT_SECRET", "test-secret")
    monkeypatch.setenv("DATA_FILE", str(data_file))
    monkeypatch.setenv("SEED_FILE", seed_file)

    import auth
    import main

    importlib.reload(auth)
    importlib.reload(main)

    return TestClient(main.app)


def test_seeded_admin_can_login_and_has_admin_role(seeded_client):
    response = seeded_client.post(
        "/users/login", json={"email": "admin@pizzaria.com", "password": "admin123"}
    )
    assert response.status_code == 200
    token = response.json()["token"]

    user_response = seeded_client.get(
        "/users/11111111-1111-4111-8111-111111111111",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert user_response.status_code == 200
    assert user_response.json()["role"] == "admin"
