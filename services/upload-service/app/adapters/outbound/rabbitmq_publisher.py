"""RabbitMQ adapter for publishing upload events."""
import json

import aio_pika

from app.application.ports import MessagePublisherPort


class RabbitMQPublisher(MessagePublisherPort):
    """RabbitMQ implementation of message publisher."""

    def __init__(self, connection: aio_pika.RobustConnection) -> None:
        self._connection = connection

    async def publish_upload_event(
        self,
        upload_id: str,
        filename: str,
        file_path: str,
        content_type: str
    ) -> None:
        """Publish upload event to RabbitMQ."""
        channel = await self._connection.channel()
        
        message_body = json.dumps({
            "upload_id": upload_id,
            "filename": filename,
            "file_path": file_path,
            "content_type": content_type,
        })
        
        await channel.default_exchange.publish(
            aio_pika.Message(body=message_body.encode()),
            routing_key="diagram.upload"
        )


class NullMessagePublisher(MessagePublisherPort):
    """No-op when RabbitMQ is unavailable."""

    async def publish_upload_event(
        self,
        upload_id: str,
        filename: str,
        file_path: str,
        content_type: str
    ) -> None:
        print(f"[NullPublisher] Would publish event for upload {upload_id}")
        return None


async def connect_rabbitmq(
    host: str,
    port: int,
    user: str,
    password: str,
) -> aio_pika.RobustConnection:
    """Connect to RabbitMQ."""
    try:
        connection = await aio_pika.connect_robust(
            host=host,
            port=port,
            login=user,
            password=password,
        )
        return connection
    except Exception as e:
        print(f"RabbitMQ Error: {e}")
        return None
