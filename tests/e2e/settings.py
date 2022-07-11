import os


RABBITMQ_URL = os.getenv(
    'RABBITMQ_URL',
    'amqp://admin:1q2w3e@localhost/loudhailer',
)

REDIS_URL = os.getenv(
    'REDIS_URL',
    'redis://localhost',
)
