"""RabbitMQ inbound adapter: consumes queue messages and runs the upload processing use case."""
import json
import logging
from typing import Awaitable, Callable, Optional

import aio_pika

from app.application.process_diagram_upload import ProcessDiagramUploadUseCase

logger = logging.getLogger(__name__)


async def start_diagram_upload_consumer(
    connection: aio_pika.abc.AbstractRobustConnection,
    process_upload: ProcessDiagramUploadUseCase,
    queue_name: str = "diagram.upload",
) -> None:
    channel = await connection.channel()
    await channel.set_qos(prefetch_count=1)
    queue = await channel.declare_queue(queue_name, durable=True)

    async def on_message(message: aio_pika.IncomingMessage) -> None:
        await _handle_message(message, process_upload)

    await queue.consume(on_message)
    logger.info("RabbitMQ Consumer started inside AI Service.")


async def _handle_message(
    message: aio_pika.IncomingMessage,
    process_upload: ProcessDiagramUploadUseCase,
) -> None:
    async with message.process():
        data = json.loads(message.body)
        upload_id = data["upload_id"]
        file_path = data.get("file_path", "")
        logger.info("AI Service processing upload %s", upload_id)
        await process_upload.execute(upload_id, file_path)


async def connect_rabbitmq(
    host: str,
    port: int,
    login: str,
    password: str,
) -> Optional[aio_pika.RobustConnection]:
    try:
        return await aio_pika.connect_robust(
            host=host,
            port=port,
            login=login,
            password=password,
        )
    except Exception as e:
        logger.exception("RabbitMQ connection failed")
        return None
