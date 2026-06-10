import os

os.environ["JWT_SECRET"] = "test-secret"
os.environ["JWT_EXPIRES_MINUTES"] = "60"

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from auth import (
    create_access_token,
    decode_access_token,
    get_current_user,
    hash_password,
    require_admin,
    verify_password,
)


def test_password_hash_roundtrip():
    hashed = hash_password("supersecret")
    assert hashed != "supersecret"
    assert verify_password("supersecret", hashed)
    assert not verify_password("wrongpassword", hashed)


def test_create_and_decode_token():
    token = create_access_token("user-1", "alice@example.com", "user")
    payload = decode_access_token(token)
    assert payload["userId"] == "user-1"
    assert payload["email"] == "alice@example.com"
    assert payload["role"] == "user"


def test_decode_invalid_token_raises_401():
    with pytest.raises(HTTPException) as exc_info:
        decode_access_token("not-a-valid-token")
    assert exc_info.value.status_code == 401


def _build_app():
    app = FastAPI()

    @app.get("/me")
    def me(user: dict = Depends(get_current_user)):
        return user

    @app.get("/admin")
    def admin_only(user: dict = Depends(require_admin)):
        return user

    return app


def test_get_current_user_accepts_valid_token():
    client = TestClient(_build_app())
    token = create_access_token("user-1", "alice@example.com", "user")
    response = client.get("/me", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
    assert response.json()["userId"] == "user-1"


def test_get_current_user_rejects_missing_token():
    client = TestClient(_build_app())
    response = client.get("/me")
    assert response.status_code in (401, 403)


def test_require_admin_rejects_non_admin():
    client = TestClient(_build_app())
    token = create_access_token("user-1", "alice@example.com", "user")
    response = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 403


def test_require_admin_accepts_admin():
    client = TestClient(_build_app())
    token = create_access_token("admin-1", "admin@pizzaria.com", "admin")
    response = client.get("/admin", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == 200
