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
