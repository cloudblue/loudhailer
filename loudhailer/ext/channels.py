#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import functools
import inspect
import logging
from copy import deepcopy

import msgpack
from asgiref.sync import sync_to_async
from channels.layers import BaseChannelLayer, channel_layers
from django.dispatch import Signal

from loudhailer import Loudhailer
from loudhailer.dataclasses import Envelope, RecipientType
from loudhailer.utils import rand_string


logger = logging.getLogger(__name__)

asgi_application_startup = Signal()  # noqa
asgi_application_shutdown = Signal()  # noqa


class LoudhailerChannelLifespan:

    def __init__(self, on_startup=None, on_shutdown=None):
        self.on_startup = on_startup
        self.on_shutdown = on_shutdown

    async def __call__(self, scope, receive, send):  # pragma: no cover
        if scope['type'] == 'lifespan':
            while True:
                await self.process_lifespan_event(scope, receive, send)

    async def process_lifespan_event(self, scope, receive, send):
        message = await receive()
        if message['type'] == 'lifespan.startup':
            await self.start_layers()
            await sync_to_async(asgi_application_startup.send, thread_sensitive=True)(
                sender=self.__class__, scope=scope,
            )
            if self.on_startup:
                if inspect.iscoroutinefunction(self.on_startup):
                    await self.on_startup()
                else:
                    await sync_to_async(self.on_startup, thread_sensitive=True)()
            await send({'type': 'lifespan.startup.complete'})
        elif message['type'] == 'lifespan.shutdown':
            await self.stop_layers()
            await sync_to_async(asgi_application_shutdown.send, thread_sensitive=True)(
                sender=self.__class__, scope=scope,
            )
            if self.on_shutdown:
                if inspect.iscoroutinefunction(self.on_shutdown):
                    await self.on_shutdown()
                else:
                    await sync_to_async(self.on_shutdown, thread_sensitive=True)()
            await send({'type': 'lifespan.shutdown.complete'})

    async def start_layers(self):
        for backend_name in channel_layers.configs.keys():
            backend = channel_layers[backend_name]
            if isinstance(backend, LoudhailerChannelLayer):
                await backend.connect()

    async def stop_layers(self):
        for backend in channel_layers.backends.values():
            if isinstance(backend, LoudhailerChannelLayer):
                await backend.disconnect()

    @classmethod
    def as_asgi(cls, **initkwargs):
        async def app(scope, receive, send):
            consumer = cls(**initkwargs)
            return await consumer(scope, receive, send)

        app.handler_class = cls
        app.handler_initkwargs = initkwargs

        # take name and docstring from class
        functools.update_wrapper(app, cls, updated=())
        return app


class LoudhailerChannelLayer(BaseChannelLayer):

    extensions = ['groups']

    def __init__(
        self,
        url=None,
        expiry=60,
        capacity=100,
        channel_capacity=None,
        **kwargs,
    ):
        assert url is not None, 'URL is mandatory'
        super().__init__(expiry=expiry, capacity=capacity, channel_capacity=channel_capacity)
        self._loudhailer = Loudhailer(
            url,
            serialize_func=self.serialize,
            deserialize_func=self.deserialize,
            **kwargs,
        )

    def serialize(self, envelope):
        message = deepcopy(envelope.message)
        if envelope.recipient_type == RecipientType.GROUP:
            message['__asgi_group__'] = envelope.recipient
        else:
            message['__asgi_channel__'] = envelope.recipient

        return Envelope(
            recipient_type=envelope.recipient_type,
            recipient=envelope.recipient,
            message=msgpack.packb(message),
        )

    def deserialize(self, envelope):
        message = msgpack.unpackb(envelope.message)
        message.pop('__asgi_group__', None)
        message.pop('__asgi_channel__', None)
        return Envelope(
            recipient_type=envelope.recipient_type,
            recipient=envelope.recipient,
            message=message,
        )

    async def connect(self):
        await self._loudhailer.connect()
        logger.info('Loudhailer channel layer connected.')

    async def disconnect(self):
        await self._loudhailer.disconnect()
        logger.info('Loudhailer channel layer disconnected.')

    async def send(self, channel, message):  # pragma: no cover
        pass

    async def receive(self, channel):
        return await self._loudhailer.receive_message(channel)

    async def new_channel(self, prefix='specific'):
        return f'{prefix}.loudhailer!{rand_string(12)}'

    async def group_add(self, group, channel):
        assert self.valid_group_name(group), 'Group name not valid'
        assert self.valid_channel_name(channel), 'Channel name not valid'
        await self._loudhailer.register_subscription(group, channel)

    async def group_discard(self, group, channel):
        assert self.valid_group_name(group), 'Group name not valid'
        assert self.valid_channel_name(channel), 'Channel name not valid'
        await self._loudhailer.unregister_subscription(group, channel)

    async def group_send(self, group, message):
        assert self.valid_group_name(group), 'Group name not valid'
        await self._loudhailer.publish(RecipientType.GROUP, group, message)
