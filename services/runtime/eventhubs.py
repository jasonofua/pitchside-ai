"""Azure Event Hubs as the message bus (Azure mode). One event hub per topic, partition key
= match_id so each match stays in order; one consumer group per subscribing service.
Authentication is the Container App's managed identity (DefaultAzureCredential)."""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from typing import Any

from azure.eventhub import EventData
from azure.eventhub.aio import EventHubConsumerClient, EventHubProducerClient
from azure.identity.aio import DefaultAzureCredential
from pydantic import BaseModel

from runtime.bus import Message, Topic, to_data

log = logging.getLogger(__name__)

BATCH_WAIT_S = 0.05  # producers batch for at most 50 ms
QUEUE_MAX = 20_000


class EventHubsBus:
    def __init__(self, namespace: str) -> None:
        if not namespace:
            raise ValueError("EVENTHUBS_NAMESPACE is required in Azure mode")
        self.namespace = namespace if "." in namespace else f"{namespace}.servicebus.windows.net"
        self.credential = DefaultAzureCredential()
        self._producers: dict[str, EventHubProducerClient] = {}
        self._consumers: list[EventHubConsumerClient] = []
        self._tasks: list[asyncio.Task[Any]] = []

    async def _on_error(self, events: Any, partition: str | None, error: Exception) -> None:
        log.error("event hubs send failed (partition %s): %s", partition, error)

    async def _on_success(self, events: Any, partition: str | None) -> None:
        return None

    def _producer(self, topic: Topic) -> EventHubProducerClient:
        producer = self._producers.get(topic)
        if producer is None:
            producer = self._producers[topic] = EventHubProducerClient(
                fully_qualified_namespace=self.namespace,
                eventhub_name=topic,
                credential=self.credential,
                buffered_mode=True,
                max_wait_time=BATCH_WAIT_S,
                on_error=self._on_error,
                on_success=self._on_success,
            )
        return producer

    async def publish(self, topic: Topic, key: str, payload: BaseModel | dict[str, Any]) -> None:
        body = json.dumps(to_data(payload), separators=(",", ":"))
        await self._producer(topic).send_event(EventData(body), partition_key=key)

    def subscribe(self, topic: Topic, group: str) -> AsyncIterator[Message]:
        queue: asyncio.Queue[Message] = asyncio.Queue(QUEUE_MAX)
        consumer = EventHubConsumerClient(
            fully_qualified_namespace=self.namespace,
            eventhub_name=topic,
            consumer_group=group,
            credential=self.credential,
        )
        self._consumers.append(consumer)

        async def on_event(partition: Any, event: EventData | None) -> None:
            if event is None:
                return
            try:
                data = json.loads(event.body_as_str())
            except ValueError:
                log.warning("dropping a non-JSON event on %s", topic)
                return
            key = (
                event.partition_key.decode()
                if isinstance(event.partition_key, bytes)
                else (event.partition_key or "")
            )
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(Message(topic, key, data))

        async def pump() -> None:
            async with consumer:
                await consumer.receive(on_event=on_event, starting_position="@latest")

        self._tasks.append(asyncio.create_task(pump(), name=f"eventhubs:{topic}:{group}"))

        async def iterate() -> AsyncIterator[Message]:
            while True:
                yield await queue.get()

        return iterate()

    async def close(self) -> None:
        for task in self._tasks:
            task.cancel()
        for producer in self._producers.values():
            await producer.close(flush=True)
        for consumer in self._consumers:
            await consumer.close()
        await self.credential.close()
