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
