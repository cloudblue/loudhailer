import asyncio
import logging
from dataclasses import asdict

import msgpack
import pytest

from loudhailer.backends.redis import RedisBackend
from loudhailer.dataclasses import Envelope


def test_initialization(mocker):
    mocked_pubsub = mocker.MagicMock(return_value='a value')
    mocked_redis = mocker.MagicMock(pubsub=mocked_pubsub)
    mocked_from_url = mocker.patch(
        'loudhailer.backends.redis.redis.from_url',
        return_value=mocked_redis,
    )

    backend = RedisBackend('redis://localhost')
    mocked_from_url.assert_called_once_with('redis://localhost')
    mocked_redis.pubsub.assert_called_once()
    assert backend._redis == mocked_redis
    assert backend._pubsub == 'a value'
    assert isinstance(backend._consumer_event, asyncio.Event)
    assert isinstance(backend._listen_queue, asyncio.Queue)


@pytest.mark.asyncio
async def test_connect(mocker, caplog):
    mocker.patch('loudhailer.backends.redis.redis.from_url')

    async def consumer(self):
        pass

    mocker.patch.object(RedisBackend, '_consumer', new=consumer)

    backend = RedisBackend('test://')

    with caplog.at_level(logging.INFO):
        await backend.connect()

    assert backend._consumer_event.is_set()
    assert 'Connected to test://' in caplog.text


@pytest.mark.asyncio
async def test_disconnect(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')

    async def consumer():
        while backend._consumer_event.is_set():
            await asyncio.sleep(0.01)

    backend._consumer_event.set()
    backend._consumer_task = asyncio.create_task(consumer())

    await backend.disconnect()
    assert backend._consumer_event.is_set() is False


@pytest.mark.asyncio
async def test_subscribe(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._pubsub = mocker.AsyncMock()

    await backend.subscribe('my_group')
    backend._pubsub.subscribe.assert_awaited_once_with('my_group')


@pytest.mark.asyncio
async def test_unsubscribe(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._pubsub = mocker.AsyncMock()

    await backend.unsubscribe('my_group')
    backend._pubsub.unsubscribe.assert_awaited_once_with('my_group')


@pytest.mark.asyncio
async def test_publish(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._redis = mocker.AsyncMock()

    envelope = Envelope(
        recipient_type='group',
        recipient='group',
        message=b'message',
    )

    await backend.publish(envelope)

    assert backend._redis.publish.call_count == 1
    assert backend._redis.publish.mock_calls[0].args[0] == 'group'
    msg = msgpack.unpackb(backend._redis.publish.mock_calls[0].args[1])
    assert msg == asdict(envelope)


@pytest.mark.asyncio
async def test_next_published(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    await backend._listen_queue.put('my message')
    assert await backend.next_published() == 'my message'


@pytest.mark.asyncio
async def test_consumer(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._pubsub = mocker.AsyncMock()

    envelope = Envelope(
        recipient_type='group',
        recipient='group',
        message=b'message',
    )

    backend._pubsub.get_message.return_value = {
        'data': msgpack.packb(asdict(envelope)),
    }
    backend._consumer_event.set()

    task = asyncio.create_task(backend._consumer())
    await asyncio.sleep(0.1)
    backend._consumer_event.clear()
    await task

    received_message = await backend.next_published()

    assert isinstance(received_message, Envelope)
    assert asdict(received_message) == asdict(envelope)


@pytest.mark.asyncio
async def test_consumer_cancelled(mocker, caplog):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._pubsub = mocker.AsyncMock()

    backend._pubsub.get_message.side_effect = asyncio.CancelledError
    backend._consumer_event.set()

    with caplog.at_level(logging.INFO):
        task = asyncio.create_task(backend._consumer())
        await asyncio.sleep(0.01)
        backend._consumer_event.clear()
        await task

    assert 'Disconnected from test://' in caplog.text


@pytest.mark.asyncio
async def test_consumer_runtime_error(mocker, caplog):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._pubsub = mocker.AsyncMock()

    backend._pubsub.get_message.side_effect = [RuntimeError, None]
    backend._consumer_event.set()

    task = asyncio.create_task(backend._consumer())
    await asyncio.sleep(0.502)
    backend._consumer_event.clear()
    await task

    backend._pubsub.get_message.assert_awaited()


@pytest.mark.asyncio
async def test_consumer_timeout(mocker):
    mocker.patch('loudhailer.backends.redis.redis.from_url')
    backend = RedisBackend('test://')
    backend._pubsub = mocker.AsyncMock()

    mocked_ctx_manager = mocker.AsyncMock()
    mocked_ctx_manager.__aenter__.side_effect = [asyncio.TimeoutError, None]

    envelope = Envelope(
        recipient_type='group',
        recipient='group',
        message=b'message',
    )
    mocker.patch(
        'loudhailer.backends.redis.msgpack.unpackb',
        return_value=asdict(envelope),
    )
    mocker.patch(
        'loudhailer.backends.redis.async_timeout.timeout',
        return_value=mocked_ctx_manager,
    )

    backend._consumer_event.set()

    task = asyncio.create_task(backend._consumer())
    await asyncio.sleep(0.02)
    backend._consumer_event.clear()
    await task

    backend._pubsub.get_message.assert_awaited()
