# Pizzaria Online — Microservices E-commerce Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the complete "Pizzaria Online" deliverable (`entrega/`) — three microservices (Users, Products/2 replicas, Orders) behind an API Gateway, with JWT auth, gateway-coordinated strong-consistency replication for Products, heartbeat-based failure detection, TLS, Docker Compose, a monitoring dashboard, a runnable README, and the written report — exactly as specified in `docs/superpowers/specs/2026-06-10-pizzaria-microservices-design.md`.

**Architecture:** Python 3.11 + FastAPI + Uvicorn, JSON-file storage per service, JWT (HS256) validated independently by each service, gateway proxies all client traffic and owns heartbeat + Products replication, Orders calls Products directly. TLS via one self-signed cert; Docker Compose ties all 5 instances (gateway, users, products-1, products-2, orders) together.

**Tech Stack:** FastAPI, Uvicorn, python-jose, passlib[bcrypt], httpx, pytest (+pytest-asyncio for the gateway), Docker/Docker Compose, openssl.

---

## Conventions used throughout this plan

- All paths are relative to the repo root `/mnt/c/Users/jerin/Projeto-FCCPD/`.
- A single dev virtualenv at `entrega/.venv` is used to run tests for **all** services (each service also has its own `requirements.txt` used for its Docker image).
- `auth.py` and `storage.py` are **identical** across `users/`, `products/`, `orders/` (per design decision: each service is independently deployable, so shared code is duplicated rather than imported from a shared package). They are written once (Tasks 2–3) and copied (Task 4).
- Run all commands from the repo root unless otherwise noted.
- Every `git commit` step stages only the files touched by that task.

---

## Task 1: Project scaffolding

**Files:**
- Create: `entrega/.gitignore`
- Create: `entrega/.env.example`
- Create: `entrega/requirements-dev.txt`
- Create: `entrega/users/requirements.txt`
- Create: `entrega/products/requirements.txt`
- Create: `entrega/orders/requirements.txt`
- Create: `entrega/gateway/requirements.txt`
- Create: `entrega/gateway/pytest.ini`

- [ ] **Step 1: Create the directory tree**

Run:
```bash
mkdir -p entrega/users/tests entrega/products/tests entrega/orders/tests entrega/gateway/tests entrega/gateway/static entrega/certs
```
Expected: no output, directories created.

- [ ] **Step 2: Create `entrega/.gitignore`**

```
__pycache__/
*.pyc
.pytest_cache/
.venv/
.env
certs/*.pem
certs/*.srl
users/users.json
products/products_5002.json
products/products_5012.json
orders/orders.json
gateway/gateway.log
```

- [ ] **Step 3: Create `entrega/.env.example`**

```bash
# Segredo compartilhado para assinatura/validação dos JWTs (HS256)
JWT_SECRET=troque-este-segredo-em-producao
JWT_EXPIRES_MINUTES=60

# Heartbeat (Gateway)
HEARTBEAT_INTERVAL=5
HEARTBEAT_TIMEOUT=2
HEARTBEAT_FAILURE_THRESHOLD=2

# Caminho do certificado TLS autoassinado (preenchido na Tarefa 12)
SSL_CERT_PATH=/certs/cert.pem
```

- [ ] **Step 4: Create `entrega/requirements-dev.txt`**

```
-r users/requirements.txt
-r gateway/requirements.txt
```

- [ ] **Step 5: Create `entrega/users/requirements.txt`** (identical content will be copied to `products/` and `orders/` in Task 4)

```
fastapi==0.110.0
uvicorn[standard]==0.29.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
bcrypt==4.0.1
pydantic[email]==2.6.4
httpx==0.27.0
pytest==8.1.1
```

- [ ] **Step 6: Create `entrega/products/requirements.txt` and `entrega/orders/requirements.txt`**

Run:
```bash
cp entrega/users/requirements.txt entrega/products/requirements.txt
cp entrega/users/requirements.txt entrega/orders/requirements.txt
```

- [ ] **Step 7: Create `entrega/gateway/requirements.txt`**

```
fastapi==0.110.0
uvicorn[standard]==0.29.0
httpx==0.27.0
pytest==8.1.1
pytest-asyncio==0.23.6
```

- [ ] **Step 8: Create `entrega/gateway/pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 9: Create the dev virtualenv and install dependencies**

Run:
```bash
python3 -m venv entrega/.venv
entrega/.venv/bin/pip install --upgrade pip
entrega/.venv/bin/pip install -r entrega/requirements-dev.txt
```
Expected: pip installs all packages without errors (last line: `Successfully installed ...`).

- [ ] **Step 10: Commit**

```bash
git add entrega/.gitignore entrega/.env.example entrega/requirements-dev.txt \
  entrega/users/requirements.txt entrega/products/requirements.txt \
  entrega/orders/requirements.txt entrega/gateway/requirements.txt entrega/gateway/pytest.ini
git commit -m "chore: scaffold entrega/ project structure and dependencies"
```

---

## Task 2: Shared `auth.py` (JWT + password hashing)

**Files:**
- Create: `entrega/users/auth.py`
- Test: `entrega/users/tests/test_auth.py`

- [ ] **Step 1: Write the failing tests**

Create `entrega/users/tests/__init__.py` (empty file) so pytest can import sibling modules:

```bash
touch entrega/users/tests/__init__.py
```

Create `entrega/users/tests/test_auth.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest tests/test_auth.py -v
```
Expected: collection error / `ModuleNotFoundError: No module named 'auth'` (since `auth.py` doesn't exist yet).

- [ ] **Step 3: Implement `entrega/users/auth.py`**

```python
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

JWT_SECRET = os.environ.get("JWT_SECRET", "changeme")
JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = int(os.environ.get("JWT_EXPIRES_MINUTES", "60"))

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
bearer_scheme = HTTPBearer()


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def create_access_token(user_id: str, email: str, role: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=JWT_EXPIRES_MINUTES)
    payload = {"userId": user_id, "email": email, "role": role, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalido ou expirado",
        )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    return decode_access_token(credentials.credentials)


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Acesso restrito a administradores",
        )
    return user
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest tests/test_auth.py -v
```
Expected: `7 passed`.

- [ ] **Step 5: Commit**

```bash
git add entrega/users/auth.py entrega/users/tests/test_auth.py entrega/users/tests/__init__.py
git commit -m "feat(users): add shared JWT auth and password hashing module"
```

---

## Task 3: Shared `storage.py` (JSON file storage)

**Files:**
- Create: `entrega/users/storage.py`
- Test: `entrega/users/tests/test_storage.py`

- [ ] **Step 1: Write the failing tests**

Create `entrega/users/tests/test_storage.py`:

```python
import json

from storage import load_data, save_data


def test_load_data_creates_file_from_seed_when_missing(tmp_path):
    seed_file = tmp_path / "seed.json"
    data_file = tmp_path / "data.json"
    seed_content = [{"id": "1", "name": "Pizza Margherita"}]
    seed_file.write_text(json.dumps(seed_content), encoding="utf-8")

    result = load_data(str(data_file), str(seed_file))

    assert result == seed_content
    assert data_file.exists()
    assert json.loads(data_file.read_text(encoding="utf-8")) == seed_content


def test_load_data_returns_empty_list_without_seed(tmp_path):
    data_file = tmp_path / "data.json"

    result = load_data(str(data_file))

    assert result == []
    assert data_file.exists()


def test_load_data_reads_existing_file_without_touching_seed(tmp_path):
    seed_file = tmp_path / "seed.json"
    data_file = tmp_path / "data.json"
    seed_file.write_text(json.dumps([{"id": "seed"}]), encoding="utf-8")
    data_file.write_text(json.dumps([{"id": "existing"}]), encoding="utf-8")

    result = load_data(str(data_file), str(seed_file))

    assert result == [{"id": "existing"}]


def test_save_data_writes_json(tmp_path):
    data_file = tmp_path / "nested" / "data.json"

    save_data(str(data_file), [{"id": "1", "name": "Pizza Calabresa"}])

    assert json.loads(data_file.read_text(encoding="utf-8")) == [
        {"id": "1", "name": "Pizza Calabresa"}
    ]
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest tests/test_storage.py -v
```
Expected: `ModuleNotFoundError: No module named 'storage'`.

- [ ] **Step 3: Implement `entrega/users/storage.py`**

```python
import json
from pathlib import Path
from typing import Any


def load_data(data_file: str, seed_file: str | None = None) -> list[dict[str, Any]]:
    path = Path(data_file)
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    if seed_file and Path(seed_file).exists():
        with open(seed_file, "r", encoding="utf-8") as f:
            seed = json.load(f)
    else:
        seed = []

    save_data(data_file, seed)
    return seed


def save_data(data_file: str, data: list[dict[str, Any]]) -> None:
    path = Path(data_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest tests/test_storage.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
git add entrega/users/storage.py entrega/users/tests/test_storage.py
git commit -m "feat(users): add shared JSON file storage module"
```

---

## Task 4: Duplicate `auth.py`/`storage.py` into Products and Orders

**Files:**
- Create: `entrega/products/auth.py`, `entrega/products/storage.py`
- Create: `entrega/products/tests/__init__.py`, `entrega/products/tests/test_auth.py`, `entrega/products/tests/test_storage.py`
- Create: `entrega/orders/auth.py`, `entrega/orders/storage.py`
- Create: `entrega/orders/tests/__init__.py`, `entrega/orders/tests/test_auth.py`, `entrega/orders/tests/test_storage.py`

- [ ] **Step 1: Copy the modules and tests**

Run:
```bash
for svc in products orders; do
  cp entrega/users/auth.py entrega/$svc/auth.py
  cp entrega/users/storage.py entrega/$svc/storage.py
  cp entrega/users/tests/__init__.py entrega/$svc/tests/__init__.py
  cp entrega/users/tests/test_auth.py entrega/$svc/tests/test_auth.py
  cp entrega/users/tests/test_storage.py entrega/$svc/tests/test_storage.py
done
```
Expected: no output; 10 new files created.

- [ ] **Step 2: Run the copied tests for both services**

Run:
```bash
cd entrega/products && ../.venv/bin/pytest tests/test_auth.py tests/test_storage.py -v && cd ../orders && ../.venv/bin/pytest tests/test_auth.py tests/test_storage.py -v
```
Expected: `7 passed` then `4 passed` for products, then the same `7 passed` / `4 passed` for orders (11 passed each).

- [ ] **Step 3: Commit**

```bash
git add entrega/products/auth.py entrega/products/storage.py entrega/products/tests/__init__.py \
  entrega/products/tests/test_auth.py entrega/products/tests/test_storage.py \
  entrega/orders/auth.py entrega/orders/storage.py entrega/orders/tests/__init__.py \
  entrega/orders/tests/test_auth.py entrega/orders/tests/test_storage.py
git commit -m "feat: duplicate shared auth/storage modules into products and orders services"
```

---

## Task 5: Users service (`/users/register`, `/users/login`, `/users/{id}`)

**Files:**
- Create: `entrega/users/main.py`
- Create: `entrega/users/users_seed.json`
- Test: `entrega/users/tests/test_main.py`
- Test: `entrega/users/tests/test_seed.py`

- [ ] **Step 1: Write the failing tests for the API**

Create `entrega/users/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Implement `entrega/users/main.py`**

```python
import os
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, EmailStr

from auth import create_access_token, get_current_user, hash_password, verify_password
from storage import load_data, save_data

DATA_FILE = os.environ.get("DATA_FILE", "users.json")
SEED_FILE = os.environ.get("SEED_FILE", "users_seed.json")

app = FastAPI(title="Pizzaria Online - Users Service")


class RegisterRequest(BaseModel):
    name: str
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


def _public_user(user: dict) -> dict:
    return {
        "id": user["id"],
        "name": user["name"],
        "email": user["email"],
        "role": user["role"],
    }


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/users/register", status_code=status.HTTP_201_CREATED)
def register(payload: RegisterRequest):
    users = load_data(DATA_FILE, SEED_FILE)

    if any(u["email"] == payload.email for u in users):
        raise HTTPException(status_code=409, detail="Email ja cadastrado")

    user = {
        "id": str(uuid.uuid4()),
        "name": payload.name,
        "email": payload.email,
        "passwordHash": hash_password(payload.password),
        "role": "user",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    users.append(user)
    save_data(DATA_FILE, users)

    return _public_user(user)


@app.post("/users/login")
def login(payload: LoginRequest):
    users = load_data(DATA_FILE, SEED_FILE)
    user = next((u for u in users if u["email"] == payload.email), None)

    if not user or not verify_password(payload.password, user["passwordHash"]):
        raise HTTPException(status_code=401, detail="Credenciais invalidas")

    token = create_access_token(user["id"], user["email"], user["role"])
    return {"token": token}


@app.get("/users/{user_id}")
def get_user(user_id: str, current_user: dict = Depends(get_current_user)):
    users = load_data(DATA_FILE, SEED_FILE)
    user = next((u for u in users if u["id"] == user_id), None)

    if not user:
        raise HTTPException(status_code=404, detail="Usuario nao encontrado")

    return _public_user(user)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `8 passed`.

- [ ] **Step 5: Generate the bcrypt hash for the seeded admin password**

Run:
```bash
cd entrega/users && ../.venv/bin/python -c "from auth import hash_password; print(hash_password('admin123'))"
```
Expected: a single line starting with `$2b$12$...` (60 characters). Copy this exact value — you'll paste it in the next step.

- [ ] **Step 6: Create `entrega/users/users_seed.json`**

Replace `PASTE_HASH_HERE` with the value generated in Step 5:

```json
[
  {
    "id": "11111111-1111-4111-8111-111111111111",
    "name": "Admin Pizzaria",
    "email": "admin@pizzaria.com",
    "passwordHash": "PASTE_HASH_HERE",
    "role": "admin",
    "createdAt": "2026-01-01T00:00:00+00:00"
  }
]
```

- [ ] **Step 7: Write the failing seed test**

Create `entrega/users/tests/test_seed.py`:

```python
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
```

- [ ] **Step 8: Run all users tests to verify everything passes**

Run:
```bash
cd entrega/users && ../.venv/bin/pytest -v
```
Expected: `20 passed` (7 from `test_auth.py` + 4 from `test_storage.py` + 8 from `test_main.py` + 1 from `test_seed.py`).

- [ ] **Step 9: Commit**

```bash
git add entrega/users/main.py entrega/users/users_seed.json \
  entrega/users/tests/test_main.py entrega/users/tests/test_seed.py
git commit --author="Jeronimo Rossi <jerinha2006@gmail.com>" -m "feat(users): implement register/login/get-user endpoints with seeded admin"
```

---

## Task 6: Products service (`/products`, `/products/{id}`, `POST /products`)

**Files:**
- Create: `entrega/products/main.py`
- Create: `entrega/products/products_seed.json`
- Test: `entrega/products/tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

Create `entrega/products/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/products && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Implement `entrega/products/main.py`**

```python
import os
import uuid
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from auth import require_admin
from storage import load_data, save_data

DATA_FILE = os.environ.get("DATA_FILE", "products.json")
SEED_FILE = os.environ.get("SEED_FILE", "products_seed.json")

app = FastAPI(title="Pizzaria Online - Products Service")


class ProductCreateRequest(BaseModel):
    id: str | None = None
    name: str
    description: str
    price: float = Field(gt=0)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/products")
def list_products():
    return load_data(DATA_FILE, SEED_FILE)


@app.get("/products/{product_id}")
def get_product(product_id: str):
    products = load_data(DATA_FILE, SEED_FILE)
    product = next((p for p in products if p["id"] == product_id), None)
    if not product:
        raise HTTPException(status_code=404, detail="Pizza nao encontrada")
    return product


@app.post("/products", status_code=status.HTTP_201_CREATED)
def create_product(
    payload: ProductCreateRequest, _admin: dict = Depends(require_admin)
):
    products = load_data(DATA_FILE, SEED_FILE)
    now = datetime.now(timezone.utc).isoformat()

    product = {
        "id": payload.id or str(uuid.uuid4()),
        "name": payload.name,
        "description": payload.description,
        "price": payload.price,
        "createdAt": now,
        "updatedAt": now,
    }
    products.append(product)
    save_data(DATA_FILE, products)

    return product
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/products && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `8 passed`.

- [ ] **Step 5: Create `entrega/products/products_seed.json`** (themed pizza catalog, identical seed used by both replicas)

```json
[
  {
    "id": "a1111111-1111-4111-8111-100000000001",
    "name": "Pizza Margherita",
    "description": "Molho de tomate, mussarela e manjericao fresco",
    "price": 35.0,
    "createdAt": "2026-01-01T00:00:00+00:00",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  },
  {
    "id": "a1111111-1111-4111-8111-100000000002",
    "name": "Pizza Calabresa",
    "description": "Molho de tomate, mussarela, calabresa fatiada e cebola",
    "price": 38.0,
    "createdAt": "2026-01-01T00:00:00+00:00",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  },
  {
    "id": "a1111111-1111-4111-8111-100000000003",
    "name": "Pizza Quatro Queijos",
    "description": "Mussarela, provolone, parmesao e gorgonzola",
    "price": 42.0,
    "createdAt": "2026-01-01T00:00:00+00:00",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  },
  {
    "id": "a1111111-1111-4111-8111-100000000004",
    "name": "Pizza Portuguesa",
    "description": "Presunto, ovos, cebola, azeitona e ervilha",
    "price": 40.0,
    "createdAt": "2026-01-01T00:00:00+00:00",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  },
  {
    "id": "a1111111-1111-4111-8111-100000000005",
    "name": "Pizza Frango com Catupiry",
    "description": "Frango desfiado, catupiry e milho",
    "price": 39.0,
    "createdAt": "2026-01-01T00:00:00+00:00",
    "updatedAt": "2026-01-01T00:00:00+00:00"
  }
]
```

- [ ] **Step 6: Run all products tests to verify everything passes**

Run:
```bash
cd entrega/products && ../.venv/bin/pytest -v
```
Expected: `19 passed` (7 from `test_auth.py` + 4 from `test_storage.py` + 8 from `test_main.py`).

- [ ] **Step 7: Commit**

```bash
git add entrega/products/main.py entrega/products/products_seed.json entrega/products/tests/test_main.py
git commit -m "feat(products): implement pizza catalog endpoints with admin-only creation"
```

---

## Task 7: Orders service (`POST /orders`, `GET /orders/{userId}`)

**Files:**
- Create: `entrega/orders/main.py`
- Test: `entrega/orders/tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

Create `entrega/orders/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/orders && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Implement `entrega/orders/main.py`**

```python
import os
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from auth import get_current_user
from storage import load_data, save_data

DATA_FILE = os.environ.get("DATA_FILE", "orders.json")
PRODUCTS_URL = os.environ.get("PRODUCTS_URL", "http://localhost:5002")
SSL_CERT_PATH = os.environ.get("SSL_CERT_PATH")
VERIFY = SSL_CERT_PATH if SSL_CERT_PATH else True

app = FastAPI(title="Pizzaria Online - Orders Service")


class OrderCreateRequest(BaseModel):
    productId: str
    quantity: int = Field(gt=0)


@app.get("/health")
def health():
    return {"status": "ok"}


def _fetch_product(product_id: str) -> dict:
    try:
        response = httpx.get(
            f"{PRODUCTS_URL}/products/{product_id}", timeout=5.0, verify=VERIFY
        )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="Servico de produtos indisponivel")

    if response.status_code == 404:
        raise HTTPException(status_code=404, detail="Pizza nao encontrada")
    if response.status_code != 200:
        raise HTTPException(status_code=502, detail="Servico de produtos indisponivel")

    return response.json()


@app.post("/orders", status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreateRequest, user: dict = Depends(get_current_user)):
    product = _fetch_product(payload.productId)

    order = {
        "id": str(uuid.uuid4()),
        "userId": user["userId"],
        "productId": product["id"],
        "productName": product["name"],
        "unitPrice": product["price"],
        "quantity": payload.quantity,
        "total": round(product["price"] * payload.quantity, 2),
        "status": "created",
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }

    orders = load_data(DATA_FILE)
    orders.append(order)
    save_data(DATA_FILE, orders)

    return order


@app.get("/orders/{user_id}")
def list_orders(user_id: str, user: dict = Depends(get_current_user)):
    if user["userId"] != user_id and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Acesso negado")

    orders = load_data(DATA_FILE)
    return [o for o in orders if o["userId"] == user_id]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/orders && ../.venv/bin/pytest -v
```
Expected: `20 passed` (7 from `test_auth.py` + 4 from `test_storage.py` + 9 from `test_main.py`).

- [ ] **Step 5: Commit**

```bash
git add entrega/orders/main.py entrega/orders/tests/test_main.py
git commit -m "feat(orders): implement order creation and listing with product validation"
```

---

## Task 8: Gateway — `heartbeat.py` (health registry + background loop)

**Files:**
- Create: `entrega/gateway/heartbeat.py`
- Test: `entrega/gateway/tests/test_heartbeat.py`
- Create: `entrega/gateway/tests/__init__.py`

- [ ] **Step 1: Write the failing tests**

```bash
touch entrega/gateway/tests/__init__.py
```

Create `entrega/gateway/tests/test_heartbeat.py`:

```python
import httpx

from heartbeat import HealthRegistry, ServiceInstance


async def test_instance_marked_up_after_successful_check():
    instances = [
        ServiceInstance(
            name="users", url="http://users", status="DOWN", consecutive_failures=2
        )
    ]
    registry = HealthRegistry(instances, failure_threshold=2, timeout=1.0)

    async def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await registry.check_once(client)

    assert instances[0].status == "UP"
    assert instances[0].consecutive_failures == 0


async def test_instance_marked_down_after_threshold_failures():
    instances = [ServiceInstance(name="orders", url="http://orders")]
    registry = HealthRegistry(instances, failure_threshold=2, timeout=1.0)

    async def handler(request):
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await registry.check_once(client)
        assert instances[0].status == "UP"
        assert instances[0].consecutive_failures == 1

        await registry.check_once(client)
        assert instances[0].status == "DOWN"
        assert instances[0].consecutive_failures == 2


async def test_instance_recovers_after_being_down():
    instances = [
        ServiceInstance(
            name="orders", url="http://orders", status="DOWN", consecutive_failures=2
        )
    ]
    registry = HealthRegistry(instances, failure_threshold=2, timeout=1.0)

    async def handler(request):
        return httpx.Response(200, json={"status": "ok"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await registry.check_once(client)

    assert instances[0].status == "UP"
    assert instances[0].consecutive_failures == 0


def test_healthy_returns_only_up_instances():
    instances = [
        ServiceInstance(name="products", url="http://p1", status="UP"),
        ServiceInstance(name="products", url="http://p2", status="DOWN"),
    ]
    registry = HealthRegistry(instances)

    healthy = registry.healthy("products")

    assert [i.url for i in healthy] == ["http://p1"]


def test_all_for_returns_all_instances_regardless_of_status():
    instances = [
        ServiceInstance(name="products", url="http://p1", status="UP"),
        ServiceInstance(name="products", url="http://p2", status="DOWN"),
        ServiceInstance(name="users", url="http://users", status="UP"),
    ]
    registry = HealthRegistry(instances)

    assert len(registry.all_for("products")) == 2
    assert len(registry.all_for("users")) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_heartbeat.py -v
```
Expected: `ModuleNotFoundError: No module named 'heartbeat'`.

- [ ] **Step 3: Implement `entrega/gateway/heartbeat.py`**

```python
import asyncio
import logging
import time
from dataclasses import dataclass

import httpx

logger = logging.getLogger("gateway.heartbeat")


@dataclass
class ServiceInstance:
    name: str
    url: str
    status: str = "UP"
    consecutive_failures: int = 0
    last_check: float | None = None


class HealthRegistry:
    def __init__(self, instances, failure_threshold: int = 2, timeout: float = 2.0):
        self.instances = instances
        self.failure_threshold = failure_threshold
        self.timeout = timeout

    def all_for(self, name: str) -> list[ServiceInstance]:
        return [i for i in self.instances if i.name == name]

    def healthy(self, name: str) -> list[ServiceInstance]:
        return [i for i in self.instances if i.name == name and i.status == "UP"]

    async def check_once(self, client: httpx.AsyncClient) -> None:
        for inst in self.instances:
            await self._check_instance(client, inst)

    async def _check_instance(self, client: httpx.AsyncClient, inst: ServiceInstance) -> None:
        inst.last_check = time.time()
        try:
            response = await client.get(f"{inst.url}/health", timeout=self.timeout)
            ok = response.status_code == 200 and response.json().get("status") == "ok"
        except httpx.HTTPError:
            ok = False

        if ok:
            if inst.status == "DOWN":
                logger.warning("[RECOVERY] %s (%s) back UP", inst.name, inst.url)
            inst.consecutive_failures = 0
            inst.status = "UP"
        else:
            inst.consecutive_failures += 1
            if inst.consecutive_failures >= self.failure_threshold and inst.status == "UP":
                inst.status = "DOWN"
                logger.warning(
                    "[FAILURE] %s (%s) DOWN after %d failed checks",
                    inst.name,
                    inst.url,
                    inst.consecutive_failures,
                )


async def heartbeat_loop(registry: HealthRegistry, interval: float, client: httpx.AsyncClient) -> None:
    while True:
        await registry.check_once(client)
        await asyncio.sleep(interval)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_heartbeat.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add entrega/gateway/heartbeat.py entrega/gateway/tests/test_heartbeat.py entrega/gateway/tests/__init__.py
git commit -m "feat(gateway): add heartbeat health registry with failure/recovery logging"
```

---

## Task 9: Gateway — `replication.py` (Products replica routing)

**Files:**
- Create: `entrega/gateway/replication.py`
- Test: `entrega/gateway/tests/test_replication.py`

- [ ] **Step 1: Write the failing tests**

Create `entrega/gateway/tests/test_replication.py`:

```python
import json

import httpx
import pytest

from heartbeat import HealthRegistry, ServiceInstance
from replication import ProductsReplicaError, ProductsRouter


def _make_registry(statuses):
    instances = [
        ServiceInstance(name="products", url=f"http://products-{i + 1}", status=status)
        for i, status in enumerate(statuses)
    ]
    return HealthRegistry(instances)


async def test_pick_read_replica_round_robins_among_healthy():
    registry = _make_registry(["UP", "UP"])

    async def handler(request):
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = ProductsRouter(registry, client)
        first = router.pick_read_replica()
        second = router.pick_read_replica()
        third = router.pick_read_replica()

    assert first.url != second.url
    assert first.url == third.url


def test_pick_read_replica_raises_503_when_all_down():
    registry = _make_registry(["DOWN", "DOWN"])
    router = ProductsRouter(registry, client=None)

    with pytest.raises(ProductsReplicaError) as exc_info:
        router.pick_read_replica()

    assert exc_info.value.status_code == 503


async def test_create_product_raises_503_when_any_replica_down():
    registry = _make_registry(["UP", "DOWN"])

    async def handler(request):
        return httpx.Response(201, json={"id": "x"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = ProductsRouter(registry, client)
        with pytest.raises(ProductsReplicaError) as exc_info:
            await router.create_product(
                {"name": "Pizza Teste", "description": "...", "price": 10.0}, {}
            )

    assert exc_info.value.status_code == 503


async def test_create_product_writes_to_both_replicas_with_same_id():
    registry = _make_registry(["UP", "UP"])
    received = []

    async def handler(request):
        received.append((str(request.url), json.loads(request.content)))
        return httpx.Response(201, json={"id": "ignored"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = ProductsRouter(registry, client)
        response = await router.create_product(
            {"name": "Pizza Teste", "description": "...", "price": 10.0}, {}
        )

    assert response.status_code == 201
    assert len(received) == 2
    assert "products-1" in received[0][0]
    assert "products-2" in received[1][0]
    assert received[0][1]["id"] == received[1][1]["id"]


async def test_create_product_raises_502_when_a_replica_rejects():
    registry = _make_registry(["UP", "UP"])

    async def handler(request):
        if "products-1" in str(request.url):
            return httpx.Response(201, json={"id": "ok"})
        return httpx.Response(500)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = ProductsRouter(registry, client)
        with pytest.raises(ProductsReplicaError) as exc_info:
            await router.create_product({"name": "x", "description": "y", "price": 1.0}, {})

    assert exc_info.value.status_code == 502
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_replication.py -v
```
Expected: `ModuleNotFoundError: No module named 'replication'`.

- [ ] **Step 3: Implement `entrega/gateway/replication.py`**

```python
import itertools
import logging
import uuid

import httpx

logger = logging.getLogger("gateway.replication")


class ProductsReplicaError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail
        super().__init__(detail)


class ProductsRouter:
    def __init__(self, registry, client):
        self.registry = registry
        self.client = client
        self._counter = itertools.count()

    def pick_read_replica(self):
        healthy = self.registry.healthy("products")
        if not healthy:
            raise ProductsReplicaError(503, "Servico de produtos indisponivel")
        index = next(self._counter) % len(healthy)
        return healthy[index]

    async def get(self, path: str, headers: dict) -> httpx.Response:
        replica = self.pick_read_replica()
        return await self.client.get(f"{replica.url}{path}", headers=headers, timeout=5.0)

    async def create_product(self, payload: dict, headers: dict) -> httpx.Response:
        all_replicas = self.registry.all_for("products")
        if any(r.status != "UP" for r in all_replicas):
            raise ProductsReplicaError(
                503,
                "Replicacao indisponivel: uma replica do servico de produtos esta fora do ar",
            )

        body = {**payload, "id": payload.get("id") or str(uuid.uuid4())}

        responses = []
        for replica in all_replicas:
            try:
                response = await self.client.post(
                    f"{replica.url}/products", json=body, headers=headers, timeout=5.0
                )
            except httpx.HTTPError as exc:
                raise ProductsReplicaError(
                    502, f"Falha ao escrever na replica {replica.url}: {exc}"
                )
            responses.append(response)

        if any(r.status_code >= 400 for r in responses):
            logger.error(
                "[REPLICATION] escrita inconsistente entre replicas de produtos: %s",
                body["id"],
            )
            raise ProductsReplicaError(502, "Falha ao propagar escrita para todas as replicas")

        return responses[0]
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_replication.py -v
```
Expected: `5 passed`.

- [ ] **Step 5: Commit**

```bash
git add entrega/gateway/replication.py entrega/gateway/tests/test_replication.py
git commit -m "feat(gateway): add gateway-coordinated products replication router"
```

---

## Task 10: Gateway — `main.py` (proxy routing + dashboard status API)

**Files:**
- Create: `entrega/gateway/main.py`
- Test: `entrega/gateway/tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

Create `entrega/gateway/tests/test_main.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `ModuleNotFoundError: No module named 'main'`.

- [ ] **Step 3: Implement `entrega/gateway/main.py`**

```python
import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from heartbeat import HealthRegistry, ServiceInstance, heartbeat_loop
from replication import ProductsReplicaError, ProductsRouter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(), logging.FileHandler("gateway.log")],
)
logger = logging.getLogger("gateway")

USERS_URL = os.environ.get("USERS_URL", "http://localhost:5001")
ORDERS_URL = os.environ.get("ORDERS_URL", "http://localhost:5003")
PRODUCTS_URLS = [
    u.strip()
    for u in os.environ.get(
        "PRODUCTS_URLS", "http://localhost:5002,http://localhost:5012"
    ).split(",")
]
HEARTBEAT_INTERVAL = float(os.environ.get("HEARTBEAT_INTERVAL", "5"))
HEARTBEAT_TIMEOUT = float(os.environ.get("HEARTBEAT_TIMEOUT", "2"))
HEARTBEAT_FAILURE_THRESHOLD = int(os.environ.get("HEARTBEAT_FAILURE_THRESHOLD", "2"))
SSL_CERT_PATH = os.environ.get("SSL_CERT_PATH")
VERIFY = SSL_CERT_PATH if SSL_CERT_PATH else True

instances = [
    ServiceInstance(name="users", url=USERS_URL),
    ServiceInstance(name="orders", url=ORDERS_URL),
] + [ServiceInstance(name="products", url=url) for url in PRODUCTS_URLS]

registry = HealthRegistry(
    instances, failure_threshold=HEARTBEAT_FAILURE_THRESHOLD, timeout=HEARTBEAT_TIMEOUT
)
http_client = httpx.AsyncClient(verify=VERIFY)
products_router = ProductsRouter(registry, http_client)

_heartbeat_task: asyncio.Task | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _heartbeat_task
    _heartbeat_task = asyncio.create_task(
        heartbeat_loop(registry, HEARTBEAT_INTERVAL, http_client)
    )
    yield
    _heartbeat_task.cancel()
    await http_client.aclose()


app = FastAPI(title="Pizzaria Online - API Gateway", lifespan=lifespan)


def _forward_headers(request: Request) -> dict:
    headers = {}
    auth = request.headers.get("authorization")
    if auth:
        headers["authorization"] = auth
    return headers


async def _proxy_single(name: str, base_url: str, path: str, request: Request) -> Response:
    instance = registry.all_for(name)[0]
    if instance.status == "DOWN":
        return JSONResponse(
            status_code=503,
            content={"error": f"Servico de {name} indisponivel no momento"},
        )

    body = await request.body()
    response = await http_client.request(
        request.method,
        f"{base_url}{path}",
        params=list(request.query_params.multi_items()),
        headers=_forward_headers(request),
        content=body,
        timeout=5.0,
    )
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type=response.headers.get("content-type"),
    )


@app.api_route("/users/{path:path}", methods=["GET", "POST"])
async def users_proxy(path: str, request: Request):
    return await _proxy_single("users", USERS_URL, f"/users/{path}", request)


@app.post("/orders")
async def orders_create_proxy(request: Request):
    return await _proxy_single("orders", ORDERS_URL, "/orders", request)


@app.get("/orders/{path:path}")
async def orders_get_proxy(path: str, request: Request):
    return await _proxy_single("orders", ORDERS_URL, f"/orders/{path}", request)


@app.get("/products")
async def list_products(request: Request):
    try:
        response = await products_router.get("/products", _forward_headers(request))
    except ProductsReplicaError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@app.get("/products/{product_id}")
async def get_product(product_id: str, request: Request):
    try:
        response = await products_router.get(
            f"/products/{product_id}", _forward_headers(request)
        )
    except ProductsReplicaError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@app.post("/products")
async def create_product(request: Request):
    payload = await request.json()
    try:
        response = await products_router.create_product(payload, _forward_headers(request))
    except ProductsReplicaError as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail})
    return Response(
        content=response.content,
        status_code=response.status_code,
        media_type="application/json",
    )


@app.get("/dashboard/status")
async def dashboard_status():
    return {
        "services": [
            {
                "name": inst.name,
                "url": inst.url,
                "status": inst.status,
                "lastCheck": inst.last_check,
            }
            for inst in registry.instances
        ]
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_main.py -v
```
Expected: `9 passed`.

- [ ] **Step 5: Run the full gateway test suite**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest -v
```
Expected: `19 passed` (5 from `test_heartbeat.py` + 5 from `test_replication.py` + 9 from `test_main.py`).

- [ ] **Step 6: Commit**

```bash
git add entrega/gateway/main.py entrega/gateway/tests/test_main.py
git commit -m "feat(gateway): implement proxy routing, replica routing and dashboard status API"
```

---

## Task 11: Gateway — monitoring dashboard (`/dashboard` HTML)

**Files:**
- Create: `entrega/gateway/static/dashboard.html`
- Modify: `entrega/gateway/main.py`
- Modify: `entrega/gateway/tests/test_main.py`

- [ ] **Step 1: Write the failing test**

Add the following test function to the end of `entrega/gateway/tests/test_main.py`:

```python
def test_dashboard_serves_html(gateway):
    client = TestClient(gateway.app)

    response = client.get("/dashboard")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Pizzaria Online" in response.text
```

- [ ] **Step 2: Run the test to verify it fails**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest tests/test_main.py::test_dashboard_serves_html -v
```
Expected: `404` (route does not exist yet) — assertion `response.status_code == 200` fails.

- [ ] **Step 3: Create `entrega/gateway/static/dashboard.html`**

```html
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Pizzaria Online — Painel de Monitoramento</title>
  <style>
    body {
      font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
      background: #fdf6ec;
      color: #3a2a1a;
      margin: 0;
      padding: 2rem;
    }
    h1 {
      text-align: center;
      color: #c0392b;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 1rem;
      max-width: 800px;
      margin: 2rem auto;
    }
    .card {
      background: #fff;
      border-radius: 12px;
      padding: 1.25rem;
      box-shadow: 0 2px 6px rgba(0, 0, 0, 0.1);
      text-align: center;
    }
    .card h2 {
      margin: 0 0 0.5rem;
      font-size: 1.1rem;
      text-transform: capitalize;
    }
    .status {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      font-weight: bold;
    }
    .dot {
      width: 14px;
      height: 14px;
      border-radius: 50%;
      display: inline-block;
    }
    .dot.up { background: #2ecc71; }
    .dot.down { background: #e74c3c; }
    .meta {
      margin-top: 0.5rem;
      font-size: 0.8rem;
      color: #888;
      word-break: break-all;
    }
    .updated {
      text-align: center;
      font-size: 0.85rem;
      color: #888;
    }
  </style>
</head>
<body>
  <h1>Pizzaria Online — Painel de Monitoramento</h1>
  <div class="grid" id="services"></div>
  <p class="updated" id="updated">Carregando...</p>

  <script>
    async function refresh() {
      try {
        const response = await fetch("/dashboard/status");
        const data = await response.json();
        const grid = document.getElementById("services");
        grid.innerHTML = "";

        let productsCount = 0;
        data.services.forEach((service) => {
          let label = service.name;
          if (service.name === "products") {
            productsCount += 1;
            label = `products-${productsCount}`;
          }

          const lastCheck = service.lastCheck
            ? new Date(service.lastCheck * 1000).toLocaleTimeString("pt-BR")
            : "nunca";

          const card = document.createElement("div");
          card.className = "card";
          card.innerHTML = `
            <h2>${label}</h2>
            <span class="status">
              <span class="dot ${service.status === "UP" ? "up" : "down"}"></span>
              ${service.status}
            </span>
            <div class="meta">${service.url}</div>
            <div class="meta">ultimo check: ${lastCheck}</div>
          `;
          grid.appendChild(card);
        });

        document.getElementById("updated").textContent =
          "Atualizado em " + new Date().toLocaleTimeString("pt-BR");
      } catch (err) {
        document.getElementById("updated").textContent =
          "Falha ao consultar /dashboard/status: " + err;
      }
    }

    refresh();
    setInterval(refresh, 2000);
  </script>
</body>
</html>
```

- [ ] **Step 4: Add the `/dashboard` route to `entrega/gateway/main.py`**

In `entrega/gateway/main.py`, change the import line:

```python
from fastapi.responses import JSONResponse
```

to:

```python
from fastapi.responses import FileResponse, JSONResponse
```

Then add this constant near the top, right after the `VERIFY` assignment:

```python
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
```

Finally, add this route at the end of the file:

```python
@app.get("/dashboard")
async def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
cd entrega/gateway && ../.venv/bin/pytest -v
```
Expected: `20 passed`.

- [ ] **Step 6: Commit**

```bash
git add entrega/gateway/main.py entrega/gateway/static/dashboard.html entrega/gateway/tests/test_main.py
git commit -m "feat(gateway): add HTML monitoring dashboard"
```

---

## Task 12: Self-signed TLS certificate generation script

**Files:**
- Create: `entrega/certs/generate_certs.sh`

- [ ] **Step 1: Create `entrega/certs/generate_certs.sh`**

```bash
#!/bin/bash
set -e

CERT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

openssl req -x509 -newkey rsa:2048 -nodes \
  -keyout "$CERT_DIR/key.pem" \
  -out "$CERT_DIR/cert.pem" \
  -days 365 \
  -subj "/CN=pizzaria-online" \
  -addext "subjectAltName=DNS:localhost,DNS:gateway,DNS:users,DNS:products-1,DNS:products-2,DNS:orders,IP:127.0.0.1"

echo "Certificado gerado em: $CERT_DIR/cert.pem"
echo "Chave privada gerada em: $CERT_DIR/key.pem"
```

- [ ] **Step 2: Make the script executable and run it**

Run:
```bash
chmod +x entrega/certs/generate_certs.sh
./entrega/certs/generate_certs.sh
```
Expected: two lines printed confirming `cert.pem` and `key.pem` were created in `entrega/certs/`.

- [ ] **Step 3: Verify the certificate's Subject Alternative Names**

Run:
```bash
openssl x509 -in entrega/certs/cert.pem -noout -text | grep -A1 "Subject Alternative Name"
```
Expected: a line listing `DNS:localhost, DNS:gateway, DNS:users, DNS:products-1, DNS:products-2, DNS:orders, IP Address:127.0.0.1`.

- [ ] **Step 4: Commit**

`entrega/certs/cert.pem` and `entrega/certs/key.pem` are gitignored (per `entrega/.gitignore`, `certs/*.pem`) — only the generator script is versioned.

```bash
git add entrega/certs/generate_certs.sh
git commit -m "chore: add self-signed TLS certificate generation script"
```

---

## Task 13: Dockerfiles + Docker Compose orchestration

**Files:**
- Create: `entrega/users/Dockerfile`
- Create: `entrega/products/Dockerfile`
- Create: `entrega/orders/Dockerfile`
- Create: `entrega/gateway/Dockerfile`
- Create: `entrega/users/.dockerignore`
- Create: `entrega/products/.dockerignore`
- Create: `entrega/orders/.dockerignore`
- Create: `entrega/gateway/.dockerignore`
- Modify: `entrega/.env.example`
- Create: `entrega/docker-compose.yml`

- [ ] **Step 1: Create `entrega/users/Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD uvicorn main:app --host 0.0.0.0 --port ${PORT} --ssl-certfile ${SSL_CERT_PATH} --ssl-keyfile ${SSL_KEY_PATH}
```

- [ ] **Step 2: Copy the Dockerfile to `products/`, `orders/` and `gateway/`**

The same image recipe (install `requirements.txt`, copy source, run Uvicorn with TLS using env vars) works for every service.

Run:
```bash
cp entrega/users/Dockerfile entrega/products/Dockerfile
cp entrega/users/Dockerfile entrega/orders/Dockerfile
cp entrega/users/Dockerfile entrega/gateway/Dockerfile
```

- [ ] **Step 3: Create `entrega/users/.dockerignore`**

```
__pycache__/
*.pyc
.pytest_cache/
tests/
.venv/
users.json
products_5002.json
products_5012.json
orders.json
```

- [ ] **Step 4: Copy the `.dockerignore` to `products/`, `orders/` and `gateway/`**

Run:
```bash
cp entrega/users/.dockerignore entrega/products/.dockerignore
cp entrega/users/.dockerignore entrega/orders/.dockerignore
cp entrega/users/.dockerignore entrega/gateway/.dockerignore
```

- [ ] **Step 5: Add `SSL_KEY_PATH` to `entrega/.env.example`**

Append this line right after `SSL_CERT_PATH=/certs/cert.pem`:

```bash
SSL_KEY_PATH=/certs/key.pem
```

The full file now reads:

```bash
# Segredo compartilhado para assinatura/validação dos JWTs (HS256)
JWT_SECRET=troque-este-segredo-em-producao
JWT_EXPIRES_MINUTES=60

# Heartbeat (Gateway)
HEARTBEAT_INTERVAL=5
HEARTBEAT_TIMEOUT=2
HEARTBEAT_FAILURE_THRESHOLD=2

# Caminho do certificado TLS autoassinado (preenchido na Tarefa 12)
SSL_CERT_PATH=/certs/cert.pem
SSL_KEY_PATH=/certs/key.pem
```

- [ ] **Step 6: Create `entrega/docker-compose.yml`**

```yaml
services:
  gateway:
    build: ./gateway
    ports:
      - "8443:8443"
    environment:
      JWT_SECRET: ${JWT_SECRET}
      PORT: "8443"
      USERS_URL: https://users:5001
      ORDERS_URL: https://orders:5003
      PRODUCTS_URLS: https://products-1:5002,https://products-2:5012
      HEARTBEAT_INTERVAL: ${HEARTBEAT_INTERVAL:-5}
      HEARTBEAT_TIMEOUT: ${HEARTBEAT_TIMEOUT:-2}
      HEARTBEAT_FAILURE_THRESHOLD: ${HEARTBEAT_FAILURE_THRESHOLD:-2}
      SSL_CERT_PATH: /certs/cert.pem
      SSL_KEY_PATH: /certs/key.pem
    volumes:
      - ./certs:/certs:ro
    depends_on:
      - users
      - orders
      - products-1
      - products-2

  users:
    build: ./users
    ports:
      - "5001:5001"
    environment:
      JWT_SECRET: ${JWT_SECRET}
      JWT_EXPIRES_MINUTES: ${JWT_EXPIRES_MINUTES:-60}
      PORT: "5001"
      DATA_FILE: users.json
      SEED_FILE: users_seed.json
      SSL_CERT_PATH: /certs/cert.pem
      SSL_KEY_PATH: /certs/key.pem
    volumes:
      - ./certs:/certs:ro

  products-1:
    build: ./products
    ports:
      - "5002:5002"
    environment:
      JWT_SECRET: ${JWT_SECRET}
      PORT: "5002"
      DATA_FILE: products_5002.json
      SEED_FILE: products_seed.json
      SSL_CERT_PATH: /certs/cert.pem
      SSL_KEY_PATH: /certs/key.pem
    volumes:
      - ./certs:/certs:ro

  products-2:
    build: ./products
    ports:
      - "5012:5012"
    environment:
      JWT_SECRET: ${JWT_SECRET}
      PORT: "5012"
      DATA_FILE: products_5012.json
      SEED_FILE: products_seed.json
      SSL_CERT_PATH: /certs/cert.pem
      SSL_KEY_PATH: /certs/key.pem
    volumes:
      - ./certs:/certs:ro

  orders:
    build: ./orders
    ports:
      - "5003:5003"
    environment:
      JWT_SECRET: ${JWT_SECRET}
      PORT: "5003"
      DATA_FILE: orders.json
      PRODUCTS_URL: https://products-1:5002
      SSL_CERT_PATH: /certs/cert.pem
      SSL_KEY_PATH: /certs/key.pem
    volumes:
      - ./certs:/certs:ro
```

- [ ] **Step 7: Create the `.env` file used by Docker Compose**

`docker compose` automatically loads `entrega/.env` for `${VAR}` substitution. It is gitignored (per Task 1), so each developer creates their own copy:

```bash
cp entrega/.env.example entrega/.env
```

- [ ] **Step 8: Make sure the TLS certificate exists**

If you haven't run Task 12 yet (or the files were removed):

```bash
./entrega/certs/generate_certs.sh
```
Expected: `entrega/certs/cert.pem` and `entrega/certs/key.pem` exist.

- [ ] **Step 9: Build and start the full stack**

Run from `entrega/`:
```bash
cd entrega && docker compose up --build -d
```
Expected: 5 images build successfully and 5 containers start (`gateway`, `users`, `products-1`, `products-2`, `orders`).

- [ ] **Step 10: Verify all containers are running**

Run:
```bash
cd entrega && docker compose ps
```
Expected: all 5 services show state `running` (or `Up`).

- [ ] **Step 11: Smoke-test the gateway over HTTPS**

Run:
```bash
curl -k https://localhost:8443/dashboard/status
```
Expected: a JSON body with `"services"` containing 4 entries (`users`, `orders`, `products`, `products`), each `"status": "UP"` (heartbeat needs up to `HEARTBEAT_INTERVAL` seconds to run the first check — retry after a few seconds if any show `"DOWN"`).

- [ ] **Step 12: Tear down**

Run:
```bash
cd entrega && docker compose down
```

- [ ] **Step 13: Commit**

```bash
git add entrega/users/Dockerfile entrega/products/Dockerfile entrega/orders/Dockerfile entrega/gateway/Dockerfile \
  entrega/users/.dockerignore entrega/products/.dockerignore entrega/orders/.dockerignore entrega/gateway/.dockerignore \
  entrega/.env.example entrega/docker-compose.yml
git commit -m "chore: add Dockerfiles and Docker Compose orchestration with TLS"
```

---

## Task 14: `README_execucao.md`

**Files:**
- Create: `entrega/README_execucao.md`

- [ ] **Step 1: Create `entrega/README_execucao.md`**

```markdown
# Pizzaria Online — Instruções de Execução

Sistema de e-commerce de pizzaria composto por 4 serviços (Gateway, Usuários,
Produtos com 2 réplicas, Pedidos), com replicação coordenada, heartbeat,
autenticação JWT, TLS autoassinado e dashboard de monitoramento.

## Pré-requisitos

- **Via Docker (recomendado):** Docker + Docker Compose v2 (`docker compose version`).
- **Manual (sem Docker):** Python 3.11+ e `openssl` (apenas se quiser gerar o
  certificado TLS também no modo manual).

Credenciais do administrador semeado (usadas para criar pizzas):

```
email: admin@pizzaria.com
senha: admin123
```

---

## Opção 1: Docker Compose (recomendado)

1. Gere o certificado TLS autoassinado (uma vez):

   ```bash
   ./entrega/certs/generate_certs.sh
   ```

2. Crie o arquivo de variáveis de ambiente:

   ```bash
   cp entrega/.env.example entrega/.env
   ```

3. Suba toda a stack:

   ```bash
   cd entrega
   docker compose up --build -d
   ```

4. Verifique que os 5 containers estão rodando:

   ```bash
   docker compose ps
   ```

5. Acesse o dashboard de monitoramento:

   ```
   https://localhost:8443/dashboard
   ```

   (o navegador vai alertar sobre o certificado autoassinado — aceite o risco
   para visualizar).

6. Use os exemplos de `curl` da seção [Exemplos de uso](#exemplos-de-uso)
   abaixo, trocando a base URL para `https://localhost:8443` e adicionando a
   flag `-k` (ignora a verificação do certificado autoassinado a partir do host).

7. Para encerrar:

   ```bash
   docker compose down
   ```

---

## Opção 2: Execução manual (sem Docker)

Cada serviço roda em um terminal separado, sem TLS (HTTP simples). Todos os
terminais precisam da **mesma** `JWT_SECRET`.

### 1. Criar o virtualenv e instalar dependências (uma vez)

```bash
cd entrega
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -r products/requirements.txt
.venv/bin/pip install -r orders/requirements.txt
```

### 2. Terminal 1 — Serviço de Usuários (porta 5001)

```bash
cd entrega/users
JWT_SECRET=segredo-pizzaria JWT_EXPIRES_MINUTES=60 \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5001
```

### 3. Terminal 2 — Serviço de Produtos, réplica 1 (porta 5002)

```bash
cd entrega/products
JWT_SECRET=segredo-pizzaria DATA_FILE=products_5002.json SEED_FILE=products_seed.json \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5002
```

### 4. Terminal 3 — Serviço de Produtos, réplica 2 (porta 5012)

```bash
cd entrega/products
JWT_SECRET=segredo-pizzaria DATA_FILE=products_5012.json SEED_FILE=products_seed.json \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5012
```

### 5. Terminal 4 — Serviço de Pedidos (porta 5003)

```bash
cd entrega/orders
JWT_SECRET=segredo-pizzaria DATA_FILE=orders.json PRODUCTS_URL=http://localhost:5002 \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 5003
```

### 6. Terminal 5 — API Gateway (porta 8000)

```bash
cd entrega/gateway
USERS_URL=http://localhost:5001 \
ORDERS_URL=http://localhost:5003 \
PRODUCTS_URLS=http://localhost:5002,http://localhost:5012 \
HEARTBEAT_INTERVAL=5 HEARTBEAT_TIMEOUT=2 HEARTBEAT_FAILURE_THRESHOLD=2 \
  ../.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Acesse o dashboard em `http://localhost:8000/dashboard`. Use os exemplos de
`curl` abaixo com a base URL `http://localhost:8000` (sem `-k`).

---

## Exemplos de uso

Os exemplos abaixo usam `http://localhost:8000` (modo manual). No modo Docker,
troque para `https://localhost:8443 -k`.

### 1. Registrar um novo usuário

```bash
curl -X POST http://localhost:8000/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Cliente Teste","email":"cliente@example.com","password":"senha123"}'
```

### 2. Login (cliente)

```bash
curl -X POST http://localhost:8000/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"cliente@example.com","password":"senha123"}'
```

Resposta: `{"token": "<JWT>"}`. Exporte para uso nos próximos comandos:

```bash
TOKEN="<cole o token aqui>"
```

### 3. Consultar dados do usuário (requer JWT)

```bash
curl http://localhost:8000/users/<userId> \
  -H "Authorization: Bearer $TOKEN"
```

### 4. Listar pizzas

```bash
curl http://localhost:8000/products
```

### 5. Detalhar uma pizza

```bash
curl http://localhost:8000/products/<productId>
```

### 6. Criar uma nova pizza (requer JWT de admin)

Faça login com o admin semeado:

```bash
curl -X POST http://localhost:8000/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pizzaria.com","password":"admin123"}'
```

```bash
ADMIN_TOKEN="<cole o token do admin aqui>"

curl -X POST http://localhost:8000/products \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Pizza Vegetariana","description":"Tomate, pimentao, cebola, azeitona","price":37.50}'
```

Tentar o mesmo comando com `$TOKEN` (usuário comum) deve retornar `403`.

### 7. Criar um pedido (requer JWT)

```bash
curl -X POST http://localhost:8000/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"productId":"<productId>","quantity":2}'
```

### 8. Listar pedidos de um usuário (requer JWT)

```bash
curl http://localhost:8000/orders/<userId> \
  -H "Authorization: Bearer $TOKEN"
```

---

## Simulando falha de um serviço (heartbeat)

### Modo Docker

1. Derrube o serviço de pedidos:

   ```bash
   docker compose stop orders
   ```

2. Aguarde ~10s (2 ciclos de heartbeat) e verifique o log do gateway:

   ```bash
   docker compose logs gateway | grep FAILURE
   ```

3. Tente criar um pedido — o gateway responde `503`:

   ```bash
   curl -k https://localhost:8443/orders \
     -X POST -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"productId":"<productId>","quantity":1}'
   ```

4. Verifique que `/users` e `/products` continuam funcionando normalmente
   (`curl -k https://localhost:8443/products`).

5. Verifique o dashboard (`https://localhost:8443/dashboard`) — o card
   `orders` aparece em vermelho (`DOWN`).

6. Suba o serviço novamente:

   ```bash
   docker compose start orders
   ```

7. Aguarde ~10s e verifique a recuperação:

   ```bash
   docker compose logs gateway | grep RECOVERY
   ```

   O dashboard volta a mostrar `orders` em verde (`UP`).

### Modo manual

Pressione `Ctrl+C` no Terminal 4 (Pedidos) para derrubá-lo, observe os logs
`[FAILURE]` no terminal do Gateway após ~10s, repita os passos 3–5 acima com
`http://localhost:8000`, depois reinicie o Terminal 4 com o mesmo comando da
seção "Execução manual" e observe o log `[RECOVERY]`.
```

- [ ] **Step 2: Commit**

```bash
git add entrega/README_execucao.md
git commit -m "docs: add README with execution instructions and curl examples"
```

---

## Task 15: `relatorio.md`

**Files:**
- Create: `entrega/relatorio.md`

- [ ] **Step 1: Create `entrega/relatorio.md`**

```markdown
# Relatório — Pizzaria Online (Microsserviços)

## 1. Como a comunicação entre os microsserviços foi implementada?

Toda a comunicação é **REST/HTTP com payloads JSON**, usando `httpx` como
cliente HTTP assíncrono.

- **Cliente → Gateway:** o cliente externo (curl/Postman) fala apenas com o
  API Gateway (`:8443` com TLS via Docker Compose, `:8000` sem TLS no modo
  manual). O Gateway expõe `/users/*`, `/products*`, `/orders*`,
  `/dashboard` e `/dashboard/status`.
- **Gateway → serviços:** o Gateway repassa requisições de `/users/*` e
  `/orders/*` por proxy transparente (`entrega/gateway/main.py`,
  `_proxy_single`), encaminhando o header `Authorization` e o corpo/query
  string originais. Para `/products*`, o Gateway usa `ProductsRouter`
  (`entrega/gateway/replication.py`) para escolher a réplica de leitura
  (round-robin) ou propagar a escrita para as duas réplicas.
- **Orders → Products (leste-oeste, direto):** ao criar um pedido, o serviço
  de Pedidos chama `GET {PRODUCTS_URL}/products/{id}` diretamente em uma das
  réplicas de Produtos (sem passar pelo Gateway), para validar a existência
  da pizza e obter nome/preço atuais (`entrega/orders/main.py`,
  `_fetch_product`).
- **Autenticação entre camadas:** o token JWT (`Authorization: Bearer <token>`)
  é emitido pelo serviço de Usuários no login e validado **de forma
  independente** por cada serviço (`auth.py` duplicado em
  `users/`, `products/`, `orders/`), todos compartilhando o mesmo
  `JWT_SECRET`. O Gateway não decodifica o token — apenas o repassa.
- **Heartbeat:** o Gateway faz `GET /health` periodicamente em cada instância
  de backend (`entrega/gateway/heartbeat.py`) para manter o estado
  UP/DOWN usado no roteamento e no dashboard.

## 2. Qual estratégia de consistência foi adotada na replicação? Forte ou eventual? Por quê?

Foi adotada **consistência forte (CP, no espectro do teorema CAP)** para as
escritas no serviço de Produtos.

- `POST /products` só é aceito pelo Gateway se **as duas réplicas** estiverem
  `UP` no momento da requisição (`ProductsRouter.create_product`). Se alguma
  réplica estiver `DOWN`, o Gateway responde `503` imediatamente, **sem
  escrever em nenhuma réplica**.
- Quando ambas estão `UP`, o Gateway gera um `id` (UUID4) único, monta o
  payload com esse `id` e envia o **mesmo payload em sequência para as duas
  réplicas**. Só retorna sucesso ao cliente se **ambas** responderem `2xx`;
  caso uma rejeite, é registrado um log `[REPLICATION]` de inconsistência e o
  Gateway responde `502`.
- **Justificativa:** essa escolha garante que, sempre que uma réplica está
  acessível, seu conteúdo de produtos é idêntico ao da outra — não é
  necessário nenhum mecanismo de reconciliação ao recuperar uma réplica que
  caiu. O trade-off é a **disponibilidade de escrita**: durante uma falha
  parcial (uma réplica `DOWN`), `POST /products` fica indisponível até a
  réplica voltar, mesmo que a outra réplica esteja saudável.
- As **leituras** (`GET /products`, `GET /products/{id}`) são distribuídas
  por **round-robin simples** entre as réplicas que estão `UP`
  (`ProductsRouter.pick_read_replica`). Se ambas estiverem `DOWN`, o Gateway
  responde `503`.

## 3. O que acontece com o sistema se o Serviço de Pedidos cair? O restante continua funcionando?

Sim. Os microsserviços são independentes e o Gateway trata cada um
isoladamente:

- O heartbeat do Gateway (`entrega/gateway/heartbeat.py`) faz `GET
  {ORDERS_URL}/health` a cada `HEARTBEAT_INTERVAL` segundos (padrão 5s). Após
  `HEARTBEAT_FAILURE_THRESHOLD` falhas consecutivas (padrão 2, ou seja, ~10s),
  a instância `orders` é marcada `DOWN` e o Gateway registra
  `[FAILURE] orders (<url>) DOWN after 2 failed checks`.
- A partir desse momento, **qualquer requisição para `/orders/*`** recebe
  `503 {"error": "Servico de orders indisponivel no momento"}` do Gateway,
  sem tentar contatar o serviço (`_proxy_single`).
- **Usuários e Produtos continuam funcionando normalmente**: `POST
  /users/register`, `POST /users/login`, `GET /users/{id}`, `GET /products`,
  `GET /products/{id}` e `POST /products` não dependem do serviço de Pedidos
  e seguem respondendo normalmente, pois cada serviço é monitorado e roteado
  de forma independente.
- Quando o serviço de Pedidos volta a responder `GET /health` com
  `{"status": "ok"}`, o Gateway registra
  `[RECOVERY] orders (<url>) back UP` e volta a encaminhar requisições
  normalmente — sem necessidade de reiniciar o Gateway.
- O dashboard (`/dashboard`) reflete essa transição em tempo real (polling de
  `/dashboard/status` a cada 2s), mostrando o card `orders` em vermelho
  durante a indisponibilidade e em verde após a recuperação.

## 4. Como o JWT garante que um usuário comum não consiga criar produtos?

- No login (`POST /users/login`), o serviço de Usuários gera um JWT
  (`create_access_token` em `auth.py`) cujo payload contém `userId`, `email`,
  `role` e `exp`. O valor de `role` vem **diretamente do registro do usuário
  em `users.json`** — nunca de um campo enviado pelo cliente na requisição de
  login.
- `POST /users/register` **sempre** cria o usuário com `role: "user"`
  (`entrega/users/main.py`). Não existe nenhum endpoint que permita a um
  usuário comum alterar seu próprio `role`. O único usuário com
  `role: "admin"` é o administrador semeado em `users_seed.json`
  (`admin@pizzaria.com`).
- O endpoint `POST /products`, em **cada réplica** do serviço de Produtos,
  depende de `require_admin` (definida em `auth.py`): essa dependency chama
  `get_current_user` (decodifica e valida o JWT com o `JWT_SECRET`
  compartilhado) e, em seguida, verifica `payload["role"] == "admin"`. Se o
  token for de um usuário comum (`role: "user"`), a dependency levanta
  `HTTPException(403)` — a requisição é rejeitada **antes** de qualquer
  lógica de criação de produto ser executada.
- Como o `role` é assinado dentro do JWT (HS256) com um segredo que o cliente
  não possui, e a verificação ocorre no próprio serviço de Produtos (não
  apenas no Gateway), um usuário comum **não tem como** forjar um token com
  `role: "admin"` nem burlar a checagem chamando o serviço diretamente.

## 5. Quais limitações a implementação possui em relação a um sistema real de produção?

- **Persistência em arquivos JSON**: não há transações atômicas nem locking
  concorrente robusto. Escritas concorrentes no mesmo arquivo (`save_data`)
  podem, em teoria, causar condições de corrida sob alta concorrência — em um
  sistema real seria substituído por um banco de dados (relacional ou NoSQL)
  com controle transacional.
- **TLS autoassinado, sem CA**: o certificado gerado por
  `certs/generate_certs.sh` não é validado por uma autoridade certificadora
  pública; clientes precisam confiar manualmente nele (`curl -k` ou
  `verify=<caminho-do-cert>`). Em produção seria necessário um certificado
  emitido por uma CA confiável (ex: Let's Encrypt).
- **Sem reconciliação de réplicas após partição prolongada**: a estratégia CP
  evita divergência ao **rejeitar escritas** quando uma réplica está `DOWN`,
  mas não há um processo de sincronização automática caso uma réplica fique
  fora do ar por muito tempo e seja substituída/reiniciada com dados
  desatualizados — seria necessário um mecanismo de reconciliação (ex:
  versionamento, snapshots, ou um log de operações a ser reaplicado).
- **Sem fila de mensagens / retry assíncrono**: a propagação de escrita para
  as réplicas de Produtos e a validação de pedidos via Products são chamadas
  HTTP síncronas. Falhas transitórias de rede não têm retry automático; um
  sistema real usaria filas (ex: RabbitMQ/Kafka) e padrões como outbox para
  garantir entrega.
- **Sem rate limiting / proteção contra abuso**: o Gateway não limita a taxa
  de requisições por cliente, o que o deixa vulnerável a abuso ou negação de
  serviço acidental.
- **Segredo JWT compartilhado em texto plano**: `JWT_SECRET` é distribuído via
  `.env`/variáveis de ambiente, sem rotação ou cofre de segredos (ex:
  Vault/KMS). Em produção seria necessário gerenciamento centralizado e
  rotação periódica de segredos.
- **Heartbeat simples**: o mecanismo de heartbeat detecta falhas de
  disponibilidade (serviço não responde a `/health`), mas não detecta
  degradação parcial (ex: serviço lento, porém respondendo `200`).
```

- [ ] **Step 2: Commit**

```bash
git add entrega/relatorio.md
git commit -m "docs: add written report answering the required design questions"
```

---

## Task 16: End-to-end verification (Docker Compose)

This task does not add new files — it exercises the whole running system to
confirm every requirement from `REQUISITOS.md` actually works together. No
commit at the end (verification only); if any step fails, fix the relevant
file from a prior task and re-run from Step 1 of this task.

- [ ] **Step 1: Start the stack**

```bash
./entrega/certs/generate_certs.sh   # skip if already generated
cp entrega/.env.example entrega/.env   # skip if already created
cd entrega && docker compose up --build -d
```

- [ ] **Step 2: Wait for heartbeat and confirm all instances are UP**

```bash
sleep 8
curl -sk https://localhost:8443/dashboard/status | python3 -m json.tool
```
Expected: 4 entries (`users`, `orders`, `products` x2), all with
`"status": "UP"`.

- [ ] **Step 3: Register and log in as a regular user**

```bash
curl -sk -X POST https://localhost:8443/users/register \
  -H "Content-Type: application/json" \
  -d '{"name":"Cliente E2E","email":"e2e@example.com","password":"senha123"}' | python3 -m json.tool
```
Expected: `201` with the created user (`role: "user"`, no `passwordHash`).

```bash
TOKEN=$(curl -sk -X POST https://localhost:8443/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e@example.com","password":"senha123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")
echo $TOKEN
```
Expected: a non-empty JWT string.

- [ ] **Step 4: Confirm `/users/{id}` requires and accepts the JWT**

```bash
USER_ID=$(curl -sk https://localhost:8443/users/login -X POST \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e@example.com","password":"senha123"}' | python3 -c "import sys,json,base64; t=json.load(sys.stdin)['token']; p=t.split('.')[1]; p+='='*(-len(p)%4); print(json.loads(base64.urlsafe_b64decode(p))['userId'])")

curl -sk https://localhost:8443/users/$USER_ID -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
curl -sk https://localhost:8443/users/$USER_ID
```
Expected: first call `200` with the user's data; second call (no header)
`401` or `403`.

- [ ] **Step 5: List the seeded pizzas**

```bash
curl -sk https://localhost:8443/products | python3 -m json.tool
```
Expected: `200` with an array of 5 pizzas (Margherita, Calabresa, Quatro
Queijos, Portuguesa, Frango com Catupiry).

```bash
PRODUCT_ID=$(curl -sk https://localhost:8443/products | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
curl -sk https://localhost:8443/products/$PRODUCT_ID | python3 -m json.tool
```
Expected: `200` with the detail of that single pizza.

- [ ] **Step 6: Confirm a regular user cannot create products**

```bash
curl -sk -X POST https://localhost:8443/products \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Pizza Hacker","description":"nao deveria existir","price":1.0}'
```
Expected: `403`.

- [ ] **Step 7: Create a product as admin and confirm it is replicated**

```bash
ADMIN_TOKEN=$(curl -sk -X POST https://localhost:8443/users/login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@pizzaria.com","password":"admin123"}' | python3 -c "import sys,json;print(json.load(sys.stdin)['token'])")

curl -sk -X POST https://localhost:8443/products \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Pizza Vegetariana","description":"Tomate, pimentao, cebola, azeitona","price":37.50}' | python3 -m json.tool
```
Expected: `201` with the new pizza, including a generated `id`.

```bash
docker compose exec products-1 python3 -c "import json;print([p['name'] for p in json.load(open('products_5002.json'))])"
docker compose exec products-2 python3 -c "import json;print([p['name'] for p in json.load(open('products_5012.json'))])"
```
Expected: both lists include `"Pizza Vegetariana"` — confirming the write was
propagated to **both** replicas.

- [ ] **Step 8: Create an order and verify the total**

```bash
ORDER_PRODUCT_ID=$(curl -sk https://localhost:8443/products | python3 -c "import sys,json; ps=json.load(sys.stdin); print(next(p['id'] for p in ps if p['name']=='Pizza Margherita'))")

curl -sk -X POST https://localhost:8443/orders \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"productId\":\"$ORDER_PRODUCT_ID\",\"quantity\":2}" | python3 -m json.tool
```
Expected: `201` with `productName: "Pizza Margherita"`, `unitPrice: 35.0`,
`quantity: 2`, `total: 70.0`, `status: "created"`.

```bash
curl -sk https://localhost:8443/orders/$USER_ID -H "Authorization: Bearer $TOKEN" | python3 -m json.tool
```
Expected: `200` with an array containing the order just created.

- [ ] **Step 9: Simulate Orders going down**

```bash
docker compose stop orders
sleep 12
docker compose logs gateway | grep FAILURE
```
Expected: a line like `[FAILURE] orders (https://orders:5003) DOWN after 2 failed checks`.

```bash
curl -sk https://localhost:8443/orders/$USER_ID -H "Authorization: Bearer $TOKEN"
```
Expected: `503` with `{"error": "Servico de orders indisponivel no momento"}`.

```bash
curl -sk https://localhost:8443/products | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
curl -sk https://localhost:8443/users/$USER_ID -H "Authorization: Bearer $TOKEN"
```
Expected: both still return `200` — Users and Products are unaffected.

```bash
curl -sk https://localhost:8443/dashboard/status | python3 -m json.tool
```
Expected: the `orders` entry shows `"status": "DOWN"`.

- [ ] **Step 10: Simulate Orders recovering**

```bash
docker compose start orders
sleep 12
docker compose logs gateway | grep RECOVERY
curl -sk https://localhost:8443/dashboard/status | python3 -c "import sys,json; s=json.load(sys.stdin)['services']; print(next(x['status'] for x in s if x['name']=='orders'))"
```
Expected: a `[RECOVERY] orders (...) back UP` log line, and the dashboard
status query prints `UP`.

- [ ] **Step 11: Simulate a Products replica going down (CP write rejection)**

```bash
docker compose stop products-2
sleep 12

curl -sk -X POST https://localhost:8443/products \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Pizza Indisponivel","description":"nao deve ser criada","price":10.0}'
```
Expected: `503` with `{"error": "Replicacao indisponivel: uma replica do servico de produtos esta fora do ar"}`.

```bash
curl -sk https://localhost:8443/products | python3 -c "import sys,json;print(len(json.load(sys.stdin)))"
```
Expected: `200` — reads still work via the remaining healthy replica
(`products-1`).

```bash
docker compose start products-2
sleep 12
curl -sk https://localhost:8443/dashboard/status | python3 -m json.tool
```
Expected: both `products` entries show `"status": "UP"` again.

- [ ] **Step 12: Open the dashboard in a browser (visual check)**

Navigate to `https://localhost:8443/dashboard` (accept the self-signed
certificate warning). Expected: a page titled "Pizzaria Online — Painel de
Monitoramento" with 4 cards (`users`, `orders`, `products-1`, `products-2`),
each showing a green `UP` indicator and refreshing every ~2 seconds.

- [ ] **Step 13: Tear down**

```bash
cd entrega && docker compose down
```

---

## Final review

- [ ] **Spec coverage check**: re-read
  `docs/superpowers/specs/2026-06-10-pizzaria-microservices-design.md`
  section by section and confirm every section (1–15) maps to at least one
  task above (architecture → Tasks 1–13; data models/seed → Tasks 5–6;
  endpoints → Tasks 5–7, 10; heartbeat → Task 8; replication → Task 9;
  routing → Task 10; TLS → Tasks 12–13; Docker Compose → Task 13; dashboard →
  Task 11; README → Task 14; relatorio → Task 15; out-of-scope items are not
  implemented anywhere).
- [ ] **Placeholder scan**: confirm no task contains `TBD`, `TODO`, or
  "implement later" — the only intentional placeholder
  (`PASTE_HASH_HERE` in Task 5) is filled in by Task 5 Step 5/6 itself.
- [ ] **Type/signature consistency**: confirm field names match across
  services — `userId`/`role`/`email`/`exp` in JWT payloads (Tasks 2, 5, 6,
  7); `productId`/`quantity`/`productName`/`unitPrice`/`total`/`status` in
  orders (Task 7); `id`/`name`/`description`/`price`/`createdAt`/`updatedAt`
  in products (Tasks 6, 9); `ServiceInstance`/`HealthRegistry` fields used
  identically in Tasks 8, 9, 10; `ProductsRouter`/`ProductsReplicaError` used
  identically in Tasks 9, 10.
