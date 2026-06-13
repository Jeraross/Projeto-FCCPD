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
