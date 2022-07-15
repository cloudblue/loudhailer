import asyncio
import logging
from dataclasses import asdict

import async_timeout
import msgpack
import redis.asyncio as redis

from loudhailer.dataclasses import Envelope
from loudhailer.backends.base import BackendBase
from loudhailer.backends.utils import blur_pwd


logger = logging.getLogger(__name__)


class RedisBackend(BackendBase):

    def __init__(self, url, **kwargs):
        self._url = url
        self._redis = redis.from_url(self._url)
        self._pubsub = self._redis.pubsub()
        self._consumer_task = None
        self._consumer_event = asyncio.Event()
        self._listen_queue = asyncio.Queue()

    async def connect(self):
        self._consumer_event.set()
        self._consumer_task = asyncio.create_task(self._consumer())
        logger.info(f'Connected to {blur_pwd(self._url)}')

    async def disconnect(self):
        if self._consumer_task:
            self._consumer_event.clear()
            await self._consumer_task

    async def subscribe(self, channel):
        await self._pubsub.subscribe(channel)

    async def unsubscribe(self, channel):
        await self._pubsub.unsubscribe(channel)

    async def publish(self, envelope):
        await self._redis.publish(
            envelope.recipient,
            msgpack.packb(asdict(envelope)),
        )

    async def next_published(self):
        return await self._listen_queue.get()

    async def _consumer(self):
        while self._consumer_event.is_set():
            try:
                async with async_timeout.timeout(1):
                    message = await self._pubsub.get_message(ignore_subscribe_messages=True)
                    if message is not None:
                        await self._listen_queue.put(
                            Envelope(**msgpack.unpackb(message['data'])),
                        )
                    await asyncio.sleep(0.01)
            except asyncio.CancelledError:
                logger.info(f'Disconnected from {blur_pwd(self._url)}')
                await asyncio.sleep(0.01)
            except asyncio.TimeoutError:
                await asyncio.sleep(0.01)
            except RuntimeError:
                await asyncio.sleep(0.5)
