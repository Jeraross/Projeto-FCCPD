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
