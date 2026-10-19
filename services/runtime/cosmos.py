"""Azure Cosmos DB as the store (Azure mode): the event log, match records and agent
documents, all partitioned by match_id. The database and containers are created by the
Bicep templates; the app's managed identity has data-plane access only."""

from __future__ import annotations

import time
from typing import Any

from azure.cosmos import exceptions
from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from contracts import MatchEvent, MatchInfo
from runtime.store import DocKind

SYSTEM_FIELDS = ("_rid", "_self", "_etag", "_attachments", "_ts")


def _clean(item: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k not in SYSTEM_FIELDS}


class CosmosStore:
    def __init__(self, endpoint: str, database: str) -> None:
        if not endpoint:
            raise ValueError("COSMOS_ENDPOINT is required in Azure mode")
        self.credential = DefaultAzureCredential()
        self.client = CosmosClient(endpoint, credential=self.credential)
        db = self.client.get_database_client(database)
        self.events_c = db.get_container_client("events")
        self.matches_c = db.get_container_client("matches")
        self.docs_c = db.get_container_client("docs")

    async def append_event(self, event: MatchEvent) -> bool:
        item = {"id": event.event_id, **event.model_dump(mode="json", exclude_none=True)}
        try:
            await self.events_c.create_item(item)
        except exceptions.CosmosResourceExistsError:
            return False
        return True

    async def events(
        self, match_id: str, since_seq: int = -1, limit: int | None = None
    ) -> list[MatchEvent]:
        query = "SELECT * FROM c WHERE c.match_id = @m AND c.seq > @s ORDER BY c.seq"
        params: list[dict[str, Any]] = [
            {"name": "@m", "value": match_id},
            {"name": "@s", "value": since_seq},
        ]
        if limit is not None:
            query += " OFFSET 0 LIMIT @l"
            params.append({"name": "@l", "value": limit})
        out = []
        async for item in self.events_c.query_items(query, parameters=params,
                                                    partition_key=match_id):  # fmt: skip
            body = _clean(item)
            body.pop("id", None)
            out.append(MatchEvent.model_validate(body))
        return out

    async def put_match(self, info: MatchInfo) -> None:
        item = {"id": info.match_id, "updated": time.time_ns(),
                **info.model_dump(mode="json", exclude_none=True)}  # fmt: skip
        await self.matches_c.upsert_item(item)

    async def get_match(self, match_id: str) -> MatchInfo | None:
        try:
            item = await self.matches_c.read_item(match_id, partition_key=match_id)
        except exceptions.CosmosResourceNotFoundError:
            return None
        return _to_info(item)

    async def list_matches(self, limit: int = 20) -> list[MatchInfo]:
        query = "SELECT * FROM c ORDER BY c.updated DESC OFFSET 0 LIMIT @l"
        params: list[dict[str, Any]] = [{"name": "@l", "value": limit}]
        items = self.matches_c.query_items(query, parameters=params)
        return [_to_info(item) async for item in items]

    async def put_doc(self, kind: DocKind, match_id: str, doc_id: str, doc: dict[str, Any]) -> None:
        await self.docs_c.upsert_item({
            "id": f"{kind}:{doc_id}"[:255].replace("/", "_").replace("\\", "_").replace("#", "_")
            .replace("?", "_"),
            "kind": kind, "match_id": match_id, "n": time.time_ns(), "body": doc,
        })  # fmt: skip

    async def docs(self, kind: DocKind, match_id: str, limit: int = 200) -> list[dict[str, Any]]:
        query = (
            "SELECT c.body FROM c WHERE c.match_id = @m AND c.kind = @k "
            "ORDER BY c.n DESC OFFSET 0 LIMIT @l"
        )
        params: list[dict[str, Any]] = [
            {"name": "@m", "value": match_id},
            {"name": "@k", "value": kind},
            {"name": "@l", "value": limit},
        ]
        items = self.docs_c.query_items(query, parameters=params, partition_key=match_id)
        rows = [item["body"] async for item in items]
        rows.reverse()
        return rows

    async def close(self) -> None:
        await self.client.close()
        await self.credential.close()


def _to_info(item: dict[str, Any]) -> MatchInfo:
    body = _clean(item)
    for key in ("id", "updated"):
        body.pop(key, None)
    return MatchInfo.model_validate(body)
