"""RabbitMQ inbound adapter: consumes diagram.result queue and updates upload status."""
import json
import logging

import aio_pika

from app.application.upload_file import UpdateUploadResultUseCase

logger = logging.getLogger(__name__)

_QUEUE = "diagram.result"


async def start_diagram_result_consumer(
    connection: aio_pika.abc.AbstractRobustConnection,
    update_result: UpdateUploadResultUseCase,
) -> None:
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(_QUEUE, durable=True)

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        async with message.process():
            data = json.loads(message.body)
            upload_id = data["upload_id"]
            status = data["status"]
            logger.info("Received %s: upload_id=%s status=%s", _QUEUE, upload_id, status)
            await update_result.execute(
                upload_id=upload_id,
                status=status,
                payload_json=data.get("payload_json"),
                error_message=data.get("error_message"),
            )

    await queue.consume(on_message)
    logger.info("RabbitMQ consumer started for %s in Upload Service.", _QUEUE)
