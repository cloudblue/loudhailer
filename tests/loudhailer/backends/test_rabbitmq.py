#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import asyncio
import json
import logging

import aiormq
import pytest

from loudhailer.backends.base import PublishError
from loudhailer.backends.rabbitmq import RMQBackend


def test_initialization(mocker):
    serialize_func = mocker.MagicMock()
    deserialize_func = mocker.MagicMock()
    backend = RMQBackend('test://', serialize_func, deserialize_func)

    assert backend._url == 'test://'
    assert backend._serialize_func == serialize_func
    assert backend._deserialize_func == deserialize_func
    assert len(backend._queue_name) == 19


def test_initialization_queue_name(mocker):
    mocker.patch('loudhailer.backends.rabbitmq.rand_string', return_value='suffix')
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
        queue_prefix='my_prefix',
    )
    assert backend._queue_name == 'my_prefix_suffix'


@pytest.mark.asyncio
async def test_on_message(mocker):
    mocked_msg = mocker.MagicMock(
        routing_key='group',
        body=b'{"test": "data"}',
    )
    mocked_msg.channel.basic_ack = mocker.AsyncMock()

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        lambda group, body: json.loads(body.decode('utf-8')),
    )

    await backend.on_message(mocked_msg)

    msg = await backend._listen_queue.get()
    assert msg.group == 'group'
    assert msg.data == {'test': 'data'}

    mocked_msg.channel.basic_ack.assert_awaited_once_with(mocked_msg.delivery.delivery_tag)


@pytest.mark.asyncio
async def test_connect(mocker, caplog):

    ready_event = asyncio.Event()

    async def consumer(self):
        ready_event.set()

    mocker.patch.object(RMQBackend, '_consumer', new=consumer)

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )

    backend._ready_event = ready_event

    with caplog.at_level(logging.INFO):
        await backend.connect()

    assert backend._consumer_event.is_set()
    assert 'Connected to test://' in caplog.text


@pytest.mark.asyncio
async def test_disconnect(mocker):
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )

    async def consumer():
        while backend._consumer_event.is_set():
            await asyncio.sleep(0.01)

    backend._consumer_event.set()
    backend._consumer_task = asyncio.create_task(consumer())
    backend._consumer_channel = mocker.MagicMock(close=mocker.AsyncMock())
    backend._connection = mocker.MagicMock(close=mocker.AsyncMock())

    await backend.disconnect()
    assert backend._consumer_event.is_set() is False
    backend._consumer_channel.close.assert_awaited_once()
    backend._connection.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_subscribe(mocker):
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._consumer_channel = mocker.MagicMock(queue_bind=mocker.AsyncMock())

    await backend.subscribe('my_group')
    backend._consumer_channel.queue_bind.assert_awaited_once_with(
        backend._queue_name, backend._exchange_name, 'my_group',
    )


@pytest.mark.asyncio
async def test_unsubscribe(mocker):
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._consumer_channel = mocker.MagicMock(queue_unbind=mocker.AsyncMock())

    await backend.unsubscribe('my_group')
    backend._consumer_channel.queue_unbind.assert_awaited_once_with(
        backend._queue_name, backend._exchange_name, 'my_group',
    )


@pytest.mark.asyncio
async def test_publish(mocker):
    mocked_conn = mocker.patch.object(RMQBackend, '_ensure_connection')
    mocked_chan = mocker.patch.object(RMQBackend, '_ensure_producer_channel')
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(return_value=b'serialized message'),
        mocker.MagicMock(),
    )
    backend._producer_channel = mocker.MagicMock(basic_publish=mocker.AsyncMock())

    await backend.publish('group', 'message')

    backend._producer_channel.basic_publish.assert_awaited_once_with(
        b'serialized message', exchange=backend._exchange_name, routing_key='group',
    )
    mocked_conn.assert_awaited_once()
    mocked_chan.assert_awaited_once()
    backend._serialize_func.assert_called_once_with('group', 'message')


@pytest.mark.asyncio
async def test_publish_retry(mocker):
    mocked_conn = mocker.patch.object(RMQBackend, '_ensure_connection')
    mocked_chan = mocker.patch.object(RMQBackend, '_ensure_producer_channel')
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(return_value=b'serialized message'),
        mocker.MagicMock(),
    )
    backend._producer_channel = mocker.MagicMock(basic_publish=mocker.AsyncMock(
        side_effect=[RuntimeError('publish error'), None],
    ))

    await backend.publish('group', 'message')

    assert mocked_conn.call_count == 2
    assert mocked_chan.call_count == 2


@pytest.mark.asyncio
async def test_publish_max_retries_exceeded(mocker):
    mocker.patch.object(RMQBackend, '_ensure_connection')
    mocker.patch.object(RMQBackend, '_ensure_producer_channel')
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(return_value=b'serialized message'),
        mocker.MagicMock(),
        publish_retries=2,
    )
    backend._producer_channel = mocker.MagicMock(basic_publish=mocker.AsyncMock(
        side_effect=[RuntimeError('publish error'), RuntimeError('publish error')],
    ))
    with pytest.raises(PublishError) as exc:
        await backend.publish('group', 'message')

    assert str(exc.value) == 'Max retries exceeded'


@pytest.mark.asyncio
async def test_next_published(mocker):
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(return_value=b'serialized message'),
        mocker.MagicMock(),
    )
    await backend._listen_queue.put('my message')

    assert await backend.next_published() == 'my message'


@pytest.mark.asyncio
async def test_ensure_connection(mocker):
    mocked_connect = mocker.patch.object(RMQBackend, '_connect')
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    await backend._ensure_connection()
    mocked_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_connection_already_connected(mocker):
    mocked_connect = mocker.patch.object(RMQBackend, '_connect')
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(is_closed=False)
    await backend._ensure_connection()
    mocked_connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_consumer_channel(mocker):
    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
    )
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    await backend._ensure_consumer_channel()
    mocked_channel.exchange_declare.assert_awaited_once_with(backend._exchange_name)
    mocked_channel.queue_declare.assert_awaited_once_with(backend._queue_name, exclusive=True)


@pytest.mark.asyncio
async def test_ensure_producer_channel(mocker):
    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
    )
    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    await backend._ensure_producer_channel()
    mocked_channel.exchange_declare.assert_awaited_once_with(backend._exchange_name)


@pytest.mark.asyncio
async def test_consumer(mocker):
    mocked_conn = mocker.patch.object(RMQBackend, '_ensure_connection')
    mocked_chan = mocker.patch.object(RMQBackend, '_ensure_consumer_channel')
    mocked_channel = mocker.MagicMock(
        basic_consume=mocker.AsyncMock(),
        closing=asyncio.Future(),
    )

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    backend._consumer_event.set()
    backend._consumer_channel = mocked_channel

    task = asyncio.create_task(backend._consumer())
    await asyncio.sleep(0.1)
    assert backend._ready_event.is_set()
    backend._consumer_event.clear()
    mocked_channel.closing.set_result('whatever')
    await task
    mocked_conn.assert_awaited_once()
    mocked_chan.assert_awaited_once()
    mocked_channel.basic_consume.assert_awaited_once_with(backend._queue_name, backend.on_message)


@pytest.mark.asyncio
async def test_consumer_cancelled(mocker, caplog):
    mocked_conn = mocker.patch.object(RMQBackend, '_ensure_connection')
    mocked_chan = mocker.patch.object(RMQBackend, '_ensure_consumer_channel')
    mocked_channel = mocker.MagicMock(
        basic_consume=mocker.AsyncMock(),
        closing=asyncio.Future(),
    )

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    backend._consumer_event.set()
    backend._consumer_channel = mocked_channel
    mocked_channel.closing.set_exception(asyncio.CancelledError())

    with caplog.at_level(logging.INFO):
        task = asyncio.create_task(backend._consumer())
        await asyncio.sleep(0.1)
        backend._consumer_event.clear()
        await task

    mocked_conn.assert_awaited()
    mocked_chan.assert_awaited()

    assert 'Disconnected from test://' in caplog.text


@pytest.mark.asyncio
async def test_consumer_connection_timeout(mocker, caplog):
    mocked_conn = mocker.patch.object(
        RMQBackend,
        '_ensure_connection',
        side_effect=[asyncio.TimeoutError(), None],
    )
    mocker.patch.object(RMQBackend, '_ensure_consumer_channel')
    mocked_channel = mocker.MagicMock(
        basic_consume=mocker.AsyncMock(),
        closing=asyncio.Future(),
    )

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    backend._consumer_event.set()
    backend._consumer_channel = mocked_channel

    with caplog.at_level(logging.INFO):
        task = asyncio.create_task(backend._consumer())
        await asyncio.sleep(0.1)
        mocked_channel.closing.set_result('test')
        backend._consumer_event.clear()
        await task

    mocked_conn.assert_awaited()

    assert 'Timeout while connecting to test://' in caplog.text


@pytest.mark.asyncio
async def test_consumer_generic_exception(mocker, caplog):
    mocked_conn = mocker.patch.object(
        RMQBackend,
        '_ensure_connection',
        side_effect=[aiormq.AMQPError(), None],
    )
    mocker.patch.object(RMQBackend, '_ensure_consumer_channel')
    mocked_channel = mocker.MagicMock(
        basic_consume=mocker.AsyncMock(),
        closing=asyncio.Future(),
    )

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    backend._consumer_event.set()
    backend._consumer_channel = mocked_channel

    with caplog.at_level(logging.INFO):
        task = asyncio.create_task(backend._consumer())
        await asyncio.sleep(0.1)
        mocked_channel.closing.set_result('test')
        backend._consumer_event.clear()
        await task

    mocked_conn.assert_awaited()

    assert 'Something wrong happened' in caplog.text


@pytest.mark.asyncio
async def test__connect(mocker):
    mocker.patch(
        'loudhailer.backends.rabbitmq.aiormq.connect',
        return_value=mocker.MagicMock(connected=mocker.MagicMock(wait=mocker.AsyncMock())),
    )

    backend = RMQBackend(
        'test://',
        mocker.MagicMock(),
        mocker.MagicMock(),
    )

    await backend._connect()
    backend._connection.connected.wait.assert_awaited_once()
