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


async def test_create_product_passes_through_uniform_rejection_response():
    registry = _make_registry(["UP", "UP"])

    async def handler(request):
        return httpx.Response(403, json={"detail": "Acesso restrito a administradores"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        router = ProductsRouter(registry, client)
        response = await router.create_product(
            {"name": "x", "description": "y", "price": 1.0}, {}
        )

    assert response.status_code == 403
