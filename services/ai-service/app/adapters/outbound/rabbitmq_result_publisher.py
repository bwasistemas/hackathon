"""RabbitMQ outbound adapter: publishes diagram analysis results to diagram.result queue."""
import json
import logging

import aio_pika

from app.application.ports import ResultPublisherPort

logger = logging.getLogger(__name__)

_QUEUE = "diagram.result"


class RabbitMQResultPublisher(ResultPublisherPort):
    def __init__(self, connection: aio_pika.RobustConnection) -> None:
        self._connection = connection

    async def publish_processing(self, upload_id: str) -> None:
        await self._publish({"upload_id": upload_id, "status": "PROCESSING"})

    async def publish_done(self, upload_id: str, payload_json: str) -> None:
        await self._publish({"upload_id": upload_id, "status": "DONE", "payload_json": payload_json})

    async def publish_failed(self, upload_id: str, error_message: str) -> None:
        await self._publish({"upload_id": upload_id, "status": "ERROR", "error_message": error_message})

    async def _publish(self, data: dict) -> None:
        channel = await self._connection.channel()
        await channel.declare_queue(_QUEUE, durable=True)
        await channel.default_exchange.publish(
            aio_pika.Message(
                body=json.dumps(data).encode(),
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key=_QUEUE,
        )
        logger.info("Published %s → %s status=%s", _QUEUE, data["upload_id"], data["status"])
