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
