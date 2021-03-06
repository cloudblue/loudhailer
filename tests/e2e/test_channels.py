import asyncio
import json
import logging

import pytest
import websockets

from loudhailer.ext.channels import LoudhailerChannelLayer

from tests.e2e.settings import RABBITMQ_URL, REDIS_URL


logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_channels_rabbitmq(channels_port):
    layer = LoudhailerChannelLayer(RABBITMQ_URL)
    await layer.connect()
    url = f'ws://127.0.0.1:{channels_port}/ws1'
    async with websockets.connect(url) as ws1_1:
        async with websockets.connect(url) as ws1_2:
            await asyncio.sleep(0.1)
            for i in range(100):
                await layer.group_send('ws1', {'type': 'operation', '#msg': i})
                received = json.loads(await ws1_1.recv())
                logger.info(f'ws1_1 receive message from pid {received["pid"]}')
                assert received['data'] == {'type': 'operation', '#msg': i}
                received = json.loads(await ws1_2.recv())
                logger.info(f'ws1_2 receive message from pid {received["pid"]}')
                assert received['data'] == {'type': 'operation', '#msg': i}
    await layer.disconnect()


@pytest.mark.asyncio
async def test_channels_redis(channels_port):
    layer = LoudhailerChannelLayer(REDIS_URL)
    await layer.connect()
    url = f'ws://127.0.0.1:{channels_port}/ws2'
    async with websockets.connect(url) as ws2_1:
        async with websockets.connect(url) as ws2_2:
            await asyncio.sleep(0.1)
            for i in range(100):
                await layer.group_send('ws2', {'type': 'operation', '#msg': i})
                received = json.loads(await ws2_1.recv())
                logger.info(f'ws2_1 receive message from pid {received["pid"]}')
                assert received['data'] == {'type': 'operation', '#msg': i}
                received = json.loads(await ws2_2.recv())
                logger.info(f'ws2_2 receive message from pid {received["pid"]}')
                assert received['data'] == {'type': 'operation', '#msg': i}
    await layer.disconnect()
