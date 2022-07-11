import os

import django
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from channels.routing import ProtocolTypeRouter, URLRouter
from django.conf import settings
from django.urls import path

from loudhailer.ext.channels import LoudhailerChannelLifespan


from tests.e2e.settings import RABBITMQ_URL, REDIS_URL


settings.configure(
    CHANNEL_LAYERS={
        'rabbitmq': {
            'BACKEND': 'loudhailer.ext.channels.LoudhailerChannelLayer',
            'CONFIG': {
                'url': RABBITMQ_URL,
            },
        },
        'redis': {
            'BACKEND': 'loudhailer.ext.channels.LoudhailerChannelLayer',
            'CONFIG': {
                'url': REDIS_URL,
            },
        },
    },
    LOGGING={
        'version': 1,
        'disable_existing_loggers': False,
        'formatters': {
            'verbose': {
                'format': '%(asctime)s %(name)s %(levelname)s PID_%(process)d %(message)s',
            },
        },
        'filters': {},
        'handlers': {
            'console': {
                'class': 'logging.StreamHandler',
                'formatter': 'verbose',
            },
            'null': {
                'class': 'logging.NullHandler',
            },
        },
        'loggers': {
            'loudhailer': {
                'handlers': ['console'],
                'level': 'INFO',
            },
        },
    },
)

django.setup()


class WS1(AsyncJsonWebsocketConsumer):
    channel_layer_alias = 'rabbitmq'
    groups = ['ws1']

    async def operation(self, data):
        await self.send_json({
            'pid': os.getpid(),
            'data': data,
        })


class WS2(AsyncJsonWebsocketConsumer):
    channel_layer_alias = 'redis'
    groups = ['ws2']

    async def operation(self, data):
        await self.send_json({
            'pid': os.getpid(),
            'data': data,
        })


app = ProtocolTypeRouter({
    'lifespan': LoudhailerChannelLifespan.as_asgi(),
    'websocket': URLRouter(
        [
            path('ws1', WS1.as_asgi(), name='ws1'),
            path('ws2', WS2.as_asgi(), name='ws2'),
        ],
    ),
})
