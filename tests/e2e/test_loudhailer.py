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
async def test_loudhailer_rabbitmq_rebinds_after_connection_drop():
    """Regression for LITE-34115: when the AMQP connection drops, the
    backend must rebind previously-subscribed channels to the freshly
    declared exclusive queue so messages keep flowing.
    """
    async with Loudhailer(RABBITMQ_URL) as producer:
        async with Loudhailer(RABBITMQ_URL) as consumer:
            async with consumer.subscribe('lite_34115') as messages:
                await asyncio.sleep(0.1)
                await producer.publish(RecipientType.GROUP, 'lite_34115', {'n': 1})
                assert await asyncio.wait_for(messages.get(), timeout=2) == {'n': 1}

                old_channel = consumer._backend._consumer_channel
                await consumer._backend._connection.close()

                # Deterministic wait: the reconnect loop replaces
                # _consumer_channel with a fresh object and then sets
                # _ready_event. Polling on both guards against either the
                # stale pre-disconnect set() or a partially-reset state.
                deadline = asyncio.get_running_loop().time() + 5
                while (
                    consumer._backend._consumer_channel is old_channel
                    or not consumer._backend._ready_event.is_set()
                ):
                    if asyncio.get_running_loop().time() >= deadline:
                        raise AssertionError('reconnect did not complete in time')
                    await asyncio.sleep(0.05)

                await producer.publish(RecipientType.GROUP, 'lite_34115', {'n': 2})
                assert await asyncio.wait_for(messages.get(), timeout=5) == {'n': 2}


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
