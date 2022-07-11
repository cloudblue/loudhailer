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

from loudhailer.backends import RMQBackend


logger = logging.getLogger(__name__)


def default_serialize(group, data):
    return json.dumps(data).encode('utf-8')


def default_deserialize(group, data):
    return json.loads(data.decode('utf-8'))


class Loudhailer:

    BACKENDS = {
        'amqp': RMQBackend,
    }

    def __init__(
        self,
        url,
        serialize_func=default_serialize,
        deserialize_func=default_deserialize,
    ):
        parsed_url = urlparse(url)
        error_msg = f"No backend available for schema '{parsed_url.scheme}'"
        assert parsed_url.scheme in self.BACKENDS, error_msg

        backend_class = self.BACKENDS[parsed_url.scheme]
        self._backend = backend_class(
            url,
            serialize_func,
            deserialize_func,
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

    async def publish(self, group, message):
        await self._backend.publish(group, message)

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
        subscriptions = self._subscriptions.get(group, set())
        if subscriber in subscriptions:
            subscriptions.remove(subscriber)
        if subscriber in self._subscribers:
            del self._subscribers[subscriber]
        if not subscriptions:
            await self._backend.unsubscribe(group)

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
            event = await self._backend.next_published()
            subscription = self._subscriptions.get(event.group, [])
            for subscriber in subscription:
                await self._subscribers[subscriber].put(event.data)


class MessageIterator:
    def __init__(self, queue):
        self._queue = queue

    async def __aiter__(self):
        while True:
            yield await self.get()

    async def get(self):
        return await self._queue.get()
