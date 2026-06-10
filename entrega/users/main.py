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
