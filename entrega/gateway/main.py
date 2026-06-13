import asyncio
import logging
import os
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import FileResponse, JSONResponse

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

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

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


@app.get("/dashboard")
async def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "dashboard.html"))
