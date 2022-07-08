#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import asyncio
import logging

import aiormq

from loudhailer.dataclasses import Envelope
from loudhailer.utils import rand_string
from loudhailer.backends.base import BackendBase, PublishError
from loudhailer.backends.utils import blur_pwd

logger = logging.getLogger(__name__)


class RMQBackend(BackendBase):

    def __init__(
        self,
        url,
        exchange_name='loudhailer',
        queue_prefix='rmqchn',
        connect_timeout=5,
        publish_retries=3,
    ):
        self._url = url
        self._exchange_name = exchange_name
        self._queue_name = f'{queue_prefix}_{rand_string(12)}'
        self._connect_timeout = connect_timeout
        self._publish_retries = publish_retries
        self._listen_queue = asyncio.Queue()
        self._conn_lock = asyncio.Lock()
        self._connection = None
        self._consumer_channel = None
        self._producer_channel = None
        self._consumer_task = None
        self._consumer_event = asyncio.Event()
        self._ready_event = asyncio.Event()

    async def on_message(self, message):
        await self._listen_queue.put(
            Envelope(
                recipient_type=message.header.properties.message_type,
                recipient=message.routing_key,
                message=message.body,
            ),
        )
        await message.channel.basic_ack(message.delivery.delivery_tag)

    async def connect(self):
        self._consumer_event.set()
        self._consumer_task = asyncio.create_task(self._consumer())
        await self._ready_event.wait()
        logger.info(f'Connected to {blur_pwd(self._url)}')

    async def disconnect(self):
        if self._consumer_task:
            self._consumer_event.clear()
            await self._consumer_channel.close()
            await self._consumer_task
        if self._connection:
            await self._connection.close()

    async def subscribe(self, channel):
        await self._consumer_channel.queue_bind(self._queue_name, self._exchange_name, channel)
        logger.debug(
            f'Bind channel {channel} to exchange {self._exchange_name} queue {self._queue_name}',
        )

    async def unsubscribe(self, channel):
        await self._consumer_channel.queue_unbind(self._queue_name, self._exchange_name, channel)
        logger.debug(
            f'Unbind channel {channel} to exchange {self._exchange_name} queue {self._queue_name}',
        )

    async def publish(self, envelope):
        for _ in range(self._publish_retries):
            try:
                await self._ensure_connection()
                await self._ensure_producer_channel()
                await self._producer_channel.basic_publish(
                    envelope.message,
                    exchange=self._exchange_name,
                    routing_key=envelope.recipient,
                    properties=aiormq.spec.Basic.Properties(message_type=envelope.recipient_type),
                )
                return
            except (aiormq.AMQPError, ConnectionError, RuntimeError, asyncio.TimeoutError):
                await asyncio.sleep(0.1)
        else:
            raise PublishError('Max retries exceeded')

    async def next_published(self):
        return await self._listen_queue.get()

    async def _ensure_connection(self):
        async with self._conn_lock:
            if not self._connection or self._connection.is_closed:
                await asyncio.wait_for(self._connect(), timeout=self._connect_timeout)

    async def _ensure_consumer_channel(self):
        if not self._consumer_channel or self._consumer_channel.is_closed:
            self._consumer_channel = await self._connection.channel()
            await self._consumer_channel.exchange_declare(self._exchange_name)
            await self._consumer_channel.queue_declare(self._queue_name, exclusive=True)

    async def _ensure_producer_channel(self):
        if not self._producer_channel or self._producer_channel.is_closed:
            self._producer_channel = await self._connection.channel()
            await self._producer_channel.exchange_declare(self._exchange_name)

    async def _consumer(self):
        while self._consumer_event.is_set():
            try:
                await self._ensure_connection()
                await self._ensure_consumer_channel()
                await self._consumer_channel.basic_consume(self._queue_name, self.on_message)
                self._ready_event.set()
                logger.info('Consumer started')
                await self._consumer_channel.closing
            except asyncio.CancelledError:
                logger.info(f'Disconnected from {blur_pwd(self._url)}')
            except asyncio.TimeoutError:
                logger.warning(f'Timeout while connecting to {blur_pwd(self._url)}')
            except Exception:  # noqa
                logger.exception('Something wrong happened')
            await asyncio.sleep(0.1)
            self._ready_event.clear()

        logger.info('Consumer task exited.')

    async def _connect(self):
        self._connection = await aiormq.connect(self._url)
        await self._connection.connected.wait()
