import asyncio
import json
import logging

import pytest
import websockets

from loudhailer import Loudhailer
from loudhailer.dataclasses import RecipientType

from tests.e2e.settings import RABBITMQ_URL, REDIS_URL


logger = logging.getLogger(__name__)


@pytest.mark.asyncio
async def test_loudhailer_rabbitmq(fastapi_port):
    async with Loudhailer(RABBITMQ_URL) as loudhailer:
        url = f'ws://127.0.0.1:{fastapi_port}/ws1'
        async with websockets.connect(url) as ws1_1:
            async with websockets.connect(url) as ws1_2:
                await asyncio.sleep(0.1)
                for i in range(100):
                    await loudhailer.publish(RecipientType.GROUP, 'ws1', {'#msg': i})
                    received = json.loads(await ws1_1.recv())
                    logger.info(f'ws1_1 receive message from pid {received["pid"]}')
                    assert received['data'] == {'#msg': i}
                    received = json.loads(await ws1_2.recv())
                    logger.info(f'ws1_2 receive message from pid {received["pid"]}')
                    assert received['data'] == {'#msg': i}


@pytest.mark.asyncio
async def test_loudhailer_redis(fastapi_port):
    async with Loudhailer(REDIS_URL) as loudhailer:
        url = f'ws://127.0.0.1:{fastapi_port}/ws2'
        async with websockets.connect(url) as ws1_1:
            async with websockets.connect(url) as ws1_2:
                await asyncio.sleep(0.1)
                for i in range(100):
                    await loudhailer.publish(RecipientType.GROUP, 'ws2', {'#msg': i})
                    received = json.loads(await ws1_1.recv())
                    logger.info(f'ws1_1 receive message from pid {received["pid"]}')
                    assert received['data'] == {'#msg': i}
                    received = json.loads(await ws1_2.recv())
                    logger.info(f'ws1_2 receive message from pid {received["pid"]}')
                    assert received['data'] == {'#msg': i}
