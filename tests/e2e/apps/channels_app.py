import os

import django
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings
from django.urls import path

from loudhailer.ext.channels import LoudhailerChannelLifespan


from tests.e2e.settings import RABBITMQ_URL


settings.configure(
    CHANNEL_LAYERS={
        'default': {
            'BACKEND': 'loudhailer.ext.channels.LoudhailerChannelLayer',
            'CONFIG': {
                'url': RABBITMQ_URL,
            },
        },
    },
)

django.setup()


class WS(AsyncJsonWebsocketConsumer):
    groups = ['ws1']

    async def operation(self, data):
        await self.send_json({
            'pid': os.getpid(),
            'data': data,
        })


app = ProtocolTypeRouter({
    'lifespan': LoudhailerChannelLifespan.as_asgi(),
    'websocket': URLRouter(
        [path('ws1', WS.as_asgi(), name='ws1')],
    ),
})
