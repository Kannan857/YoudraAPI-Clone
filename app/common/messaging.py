import aio_pika
from app.config.config import settings
import structlog
import json
import uuid
from app.common.exception import GeneralDataException
logger = structlog.get_logger()


class RabbitMQConnectionManager:
    def __init__(self, url: str):
        self.url = url
        self.connection: aio_pika.RobustConnection | None = None

    async def connect(self):
        try:
            self.connection = await aio_pika.connect_robust(self.url)
            logger.info("Connected to RabbitMQ")
        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            raise

    async def disconnect(self):
        if self.connection and not self.connection.is_closed:
            await self.connection.close()
            logger.info("RabbitMQ connection closed")

    async def get_connection(self) -> aio_pika.RobustConnection:
        if self.connection is None or self.connection.is_closed:
            await self.connect()
        return self.connection


# Initialize with your URL
rabbitmq_manager = RabbitMQConnectionManager(
    url=f"amqps://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASSWORD}@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/{settings.RABBITMQ_VHOST}"
)

async def get_rabbitmq_connection() -> aio_pika.RobustConnection:
    return await rabbitmq_manager.get_connection()

'''
async def get_rabbitmq_connection():
    try:
        
        url = f"amqps://{settings.RABBITMQ_USER}:{settings.RABBITMQ_PASSWORD}@{settings.RABBITMQ_HOST}:{settings.RABBITMQ_PORT}/{settings.RABBITMQ_VHOST}"
        connection = aio_pika.connect_robust(url)
        return connection
    except aio_pika.exceptions.AMQPError as e:
        logger.error(f"RabbitMQ connection error: {e}")
        raise
'''
async def publish_message(message: dict, connection: aio_pika.RobustConnection):
    try:
        queue_name = settings.RABBITMQ_QUEUE
        message["mid"] = str(uuid.uuid4())
        task_message = json.dumps(message)

        # Establish connection
        # connection = await get_rabbitmq_connection()
        async with connection:
            channel = await connection.channel()

            # Make queue durable
            queue = await channel.declare_queue(queue_name, durable=True)

            # Publish message
            await channel.default_exchange.publish(
                aio_pika.Message(
                    body=task_message.encode(),
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    content_type='application/json'
                ),
                routing_key=queue_name,
            )
    except aio_pika.exceptions.AMQPError as e:
        logger.error(f"RabbitMQ connection error: {e}")
        raise GeneralDataException(
            f"RabbitMQ connection error: {e}",
            context={"detail": f"RabbitMQ connection error: {e}"}
        )
    except Exception as e:
        logger.error(f"Unexpected error when sending message: {str(e)}")
        raise GeneralDataException(
            f"Unexpected error when sending message: {str(e)}",
            context={"detail": f"Unexpected error when sending message: {str(e)}"}
        )