#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import asyncio
import json
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse
from uuid import uuid4

from loudhailer.backends import RedisBackend, RMQBackend
from loudhailer.dataclasses import Envelope, RecipientType


logger = logging.getLogger(__name__)


def default_serialize(envelope):
    return Envelope(
        recipient_type=envelope.recipient_type,
        recipient=envelope.recipient,
        message=json.dumps(envelope.message).encode('utf-8'),
    )


def default_deserialize(envelope):
    return Envelope(
        recipient_type=envelope.recipient_type,
        recipient=envelope.recipient,
        message=json.loads(envelope.message.decode('utf-8')),
    )


class MessageIterator:
    def __init__(self, queue):
        self._queue = queue

    async def __aiter__(self):
        while True:
            yield await self.get()

    async def get(self):
        return await self._queue.get()


class Loudhailer:

    BACKENDS = {
        'amqp': RMQBackend,
        'amqps': RMQBackend,
        'redis': RedisBackend,
        'rediss': RedisBackend,
    }

    def __init__(
        self,
        url,
        extra_backends=None,
        serialize_func=None,
        deserialize_func=None,
        **backend_kwargs,
    ):
        self.url = url
        assert serialize_func is None or callable(serialize_func), (
            'Serialize func must be a callable'
        )
        assert deserialize_func is None or callable(deserialize_func), (
            'Deserialize func must be a callable'
        )
        self._serialize_func = serialize_func or default_serialize
        self._deserialize_func = deserialize_func or default_deserialize

        backends = {**self.BACKENDS}
        backends.update(extra_backends or {})

        parsed_url = urlparse(url)
        assert parsed_url.scheme in backends, (
            f"No backend available for schema '{parsed_url.scheme}'"
        )

        backend_class = backends[parsed_url.scheme]
        self._backend = backend_class(
            url,
            **backend_kwargs,
        )

        self._subscriptions = {}
        self._subscribers = {}
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self.disconnect()

    async def connect(self):
        await self._backend.connect()
        self._listener_task = asyncio.create_task(self._listener())

    async def disconnect(self):
        if self._listener_task.done():
            self._listener_task.result()
        else:
            self._listener_task.cancel()
        await self._backend.disconnect()

    async def publish(self, recipient_type, recipient, message):
        envelope = self._serialize_func(
            Envelope(
                recipient_type=recipient_type,
                recipient=recipient,
                message=message,
            ),
        )
        await self._backend.publish(envelope)

    async def register_subscription(self, group, subscriber=None):
        subscriber = subscriber or str(uuid4())
        async with self._lock:
            if group not in self._subscriptions:
                await self._backend.subscribe(group)
                self._subscriptions[group] = set([subscriber])
            else:
                self._subscriptions[group].add(subscriber)

            self._subscribers.setdefault(subscriber, asyncio.Queue())

        return subscriber

    async def unregister_subscription(self, group, subscriber):
        if group not in self._subscriptions:
            return
        subscriptions = self._subscriptions.get(group, set())
        if subscriber in subscriptions:
            subscriptions.remove(subscriber)
        if subscriber in self._subscribers:
            del self._subscribers[subscriber]
        if not subscriptions:
            await self._backend.unsubscribe(group)
            del self._subscriptions[group]

    async def receive_message(self, subscriber):
        queue = self._subscribers.setdefault(subscriber, asyncio.Queue())
        return await queue.get()

    @asynccontextmanager
    async def subscribe(self, group, subscriber=None):
        subscriber = await self.register_subscription(group, subscriber)
        yield MessageIterator(self._subscribers[subscriber])
        await self.unregister_subscription(group, subscriber)

    async def _listener(self):
        while True:
            envelope = await self._backend.next_published()
            envelope = self._deserialize_func(envelope)
            if envelope.recipient_type == RecipientType.GROUP:
                subscription = self._subscriptions.get(envelope.recipient, [])
                for subscriber in subscription:
                    await self._subscribers[subscriber].put(envelope.message)
            else:
                await self._subscribers[envelope.recipient].put(envelope.message)
