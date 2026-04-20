#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import asyncio
import logging

import aiormq
import pytest

from loudhailer.backends.base import PublishError
from loudhailer.backends.rabbitmq import RMQBackend
from loudhailer.dataclasses import Envelope


def test_initialization(mocker):
    backend = RMQBackend('test://')
    assert backend._url == 'test://'
    assert len(backend._queue_name) == 19


def test_initialization_queue_name(mocker):
    mocker.patch('loudhailer.backends.rabbitmq.rand_string', return_value='suffix')
    backend = RMQBackend(
        'test://',
        queue_prefix='my_prefix',
    )
    assert backend._queue_name == 'my_prefix_suffix'


@pytest.mark.asyncio
async def test_on_message(mocker):
    mocked_msg = mocker.MagicMock(
        routing_key='group',
        body=b'{"test": "data"}',
    )
    mocked_msg.header.properties.message_type = 'group'
    mocked_msg.channel.basic_ack = mocker.AsyncMock()

    backend = RMQBackend('test://')

    await backend.on_message(mocked_msg)

    msg = await backend._listen_queue.get()
    assert msg.recipient_type == 'group'
    assert msg.recipient == 'group'
    assert msg.message == b'{"test": "data"}'

    mocked_msg.channel.basic_ack.assert_awaited_once_with(mocked_msg.delivery.delivery_tag)


@pytest.mark.asyncio
async def test_connect(mocker, caplog):

    ready_event = asyncio.Event()

    async def consumer(self):
        ready_event.set()

    mocker.patch.object(RMQBackend, '_consumer', new=consumer)

    backend = RMQBackend('test://')
    backend._ready_event = ready_event

    with caplog.at_level(logging.INFO):
        await backend.connect()

    assert backend._consumer_event.is_set()
    assert 'Connected to test://' in caplog.text


@pytest.mark.asyncio
async def test_disconnect(mocker):
    backend = RMQBackend('test://')

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
    )
    backend._consumer_channel = mocker.MagicMock(queue_bind=mocker.AsyncMock())

    await backend.subscribe('my_group')
    backend._consumer_channel.queue_bind.assert_awaited_once_with(
        backend._queue_name, backend._exchange_name, 'my_group',
    )
    assert 'my_group' in backend._subscribed_channels


@pytest.mark.asyncio
async def test_unsubscribe(mocker):
    backend = RMQBackend(
        'test://',
    )
    backend._consumer_channel = mocker.MagicMock(queue_unbind=mocker.AsyncMock())
    backend._subscribed_channels.add('my_group')
    
    await backend.unsubscribe('my_group')
    backend._consumer_channel.queue_unbind.assert_awaited_once_with(
        backend._queue_name, backend._exchange_name, 'my_group',
    )
    assert 'my_group' not in backend._subscribed_channels


@pytest.mark.asyncio
async def test_unsubscribe_unknown_channel_is_noop_on_set(mocker):
    """Regression for LITE-34115: discarding a channel that was never
    subscribed must not crash, must leave the tracking set empty, and
    must still forward the queue_unbind call to the broker — guarding
    against a future optimization that skips the AMQP call when the
    channel is unknown locally.
    """
    backend = RMQBackend('test://')
    backend._consumer_channel = mocker.MagicMock(queue_unbind=mocker.AsyncMock())

    await backend.unsubscribe('never_subscribed')

    assert backend._subscribed_channels == set()
    backend._consumer_channel.queue_unbind.assert_awaited_once_with(
        backend._queue_name, backend._exchange_name, 'never_subscribed',
    )


@pytest.mark.asyncio
async def test_publish(mocker):
    mocked_conn = mocker.patch.object(RMQBackend, '_ensure_connection')
    mocked_chan = mocker.patch.object(RMQBackend, '_ensure_producer_channel')
    backend = RMQBackend('test://')
    backend._producer_channel = mocker.MagicMock(basic_publish=mocker.AsyncMock())

    await backend.publish(
        Envelope(
            recipient_type='group',
            recipient='group',
            message=b'message',
        ),
    )

    backend._producer_channel.basic_publish.assert_awaited_once_with(
        b'message',
        exchange=backend._exchange_name,
        routing_key='group',
        properties=mocker.ANY,  # TODO check properties
    )
    mocked_conn.assert_awaited_once()
    mocked_chan.assert_awaited_once()


@pytest.mark.asyncio
async def test_publish_retry(mocker):
    mocked_conn = mocker.patch.object(RMQBackend, '_ensure_connection')
    mocked_chan = mocker.patch.object(RMQBackend, '_ensure_producer_channel')
    backend = RMQBackend('test://')
    backend._producer_channel = mocker.MagicMock(basic_publish=mocker.AsyncMock(
        side_effect=[RuntimeError('publish error'), None],
    ))

    await backend.publish(
        Envelope(
            recipient_type='group',
            recipient='group',
            message=b'message',
        ),
    )

    assert mocked_conn.call_count == 2
    assert mocked_chan.call_count == 2


@pytest.mark.asyncio
async def test_publish_max_retries_exceeded(mocker):
    mocker.patch.object(RMQBackend, '_ensure_connection')
    mocker.patch.object(RMQBackend, '_ensure_producer_channel')
    backend = RMQBackend(
        'test://',
        publish_retries=2,
    )
    backend._producer_channel = mocker.MagicMock(basic_publish=mocker.AsyncMock(
        side_effect=[RuntimeError('publish error'), RuntimeError('publish error')],
    ))
    with pytest.raises(PublishError) as exc:
        await backend.publish(
            Envelope(
                recipient_type='group',
                recipient='group',
                message=b'message',
            ),
        )

    assert str(exc.value) == 'Max retries exceeded'


@pytest.mark.asyncio
async def test_next_published(mocker):
    backend = RMQBackend('test://')
    await backend._listen_queue.put('my message')
    assert await backend.next_published() == 'my message'


@pytest.mark.asyncio
async def test_ensure_connection(mocker):
    mocked_connect = mocker.patch.object(RMQBackend, '_connect')
    backend = RMQBackend('test://')
    await backend._ensure_connection()
    mocked_connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_connection_already_connected(mocker):
    mocked_connect = mocker.patch.object(RMQBackend, '_connect')
    backend = RMQBackend('test://')
    backend._connection = mocker.MagicMock(is_closed=False)
    await backend._ensure_connection()
    mocked_connect.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_consumer_channel(mocker):
    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
    )
    backend = RMQBackend('test://')
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    await backend._ensure_consumer_channel()
    mocked_channel.exchange_declare.assert_awaited_once_with(backend._exchange_name)
    mocked_channel.queue_declare.assert_awaited_once_with(backend._queue_name, exclusive=True)


@pytest.mark.asyncio
async def test_ensure_consumer_channel_rebinds_tracked_channels(mocker):
    """Regression for LITE-34115: on a fresh consumer channel, every
    tracked channel must be re-bound to the new exclusive queue.
    """
    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
        queue_bind=mocker.AsyncMock(),
    )
    backend = RMQBackend('test://')
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    backend._subscribed_channels = {'group_a', 'group_b'}

    await backend._ensure_consumer_channel()

    assert mocked_channel.queue_bind.await_count == 2
    bound = {call.args[2] for call in mocked_channel.queue_bind.await_args_list}
    assert bound == {'group_a', 'group_b'}


@pytest.mark.asyncio
async def test_ensure_consumer_channel_no_rebind_when_empty(mocker):
    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
        queue_bind=mocker.AsyncMock(),
    )
    backend = RMQBackend('test://')
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))

    await backend._ensure_consumer_channel()

    mocked_channel.queue_bind.assert_not_awaited()


@pytest.mark.asyncio
async def test_ensure_consumer_channel_rebind_lock_blocks_concurrent_subscribe(mocker):
    """Regression for LITE-34115 review feedback: the rebind loop holds
    ``_sub_lock`` so a concurrent ``subscribe()`` blocks until rebind
    finishes — no ``RuntimeError: Set changed size during iteration``,
    no ghost bindings.
    """
    first_bind_started = asyncio.Event()
    release_first_bind = asyncio.Event()

    async def slow_queue_bind(*args, **kwargs):
        first_bind_started.set()
        await release_first_bind.wait()

    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
        queue_bind=mocker.AsyncMock(side_effect=slow_queue_bind),
    )
    backend = RMQBackend('test://')
    backend._connection = mocker.MagicMock(channel=mocker.AsyncMock(return_value=mocked_channel))
    backend._subscribed_channels = {'existing'}

    rebind_task = asyncio.create_task(backend._ensure_consumer_channel())
    await asyncio.wait_for(first_bind_started.wait(), timeout=1)

    subscribe_task = asyncio.create_task(backend.subscribe('new'))
    await asyncio.sleep(0.05)
    assert not subscribe_task.done(), 'subscribe must block while rebind holds the lock'

    release_first_bind.set()
    await asyncio.wait_for(rebind_task, timeout=1)
    await asyncio.wait_for(subscribe_task, timeout=1)

    assert backend._subscribed_channels == {'existing', 'new'}


@pytest.mark.asyncio
async def test_ensure_producer_channel(mocker):
    mocked_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
    )
    backend = RMQBackend('test://')
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

    backend = RMQBackend('test://')
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

    backend = RMQBackend('test://')
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

    backend = RMQBackend('test://')
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

    backend = RMQBackend('test://')
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
async def test_consumer_rebinds_subscriptions_after_reconnect(mocker):
    """Regression for LITE-34115: after the consumer channel closes and a
    new one is opened, every previously-subscribed channel is rebound to
    the new queue.
    """
    mocker.patch.object(RMQBackend, '_ensure_connection', new=mocker.AsyncMock())

    first_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
        queue_bind=mocker.AsyncMock(),
        basic_consume=mocker.AsyncMock(),
        closing=asyncio.Future(),
        is_closed=False,
    )
    second_channel = mocker.MagicMock(
        exchange_declare=mocker.AsyncMock(),
        queue_declare=mocker.AsyncMock(),
        queue_bind=mocker.AsyncMock(),
        basic_consume=mocker.AsyncMock(),
        closing=asyncio.Future(),
        is_closed=False,
    )

    backend = RMQBackend('test://')
    backend._connection = mocker.MagicMock(
        channel=mocker.AsyncMock(side_effect=[first_channel, second_channel]),
    )
    backend._consumer_event.set()
    backend._subscribed_channels = {'group_a'}

    task = asyncio.create_task(backend._consumer())
    await asyncio.sleep(0.05)

    first_channel.is_closed = True
    first_channel.closing.set_result(None)

    deadline = asyncio.get_running_loop().time() + 2
    while second_channel.queue_bind.await_count == 0:
        if asyncio.get_running_loop().time() >= deadline:
            raise AssertionError('second channel was not set up in time')
        await asyncio.sleep(0.01)

    backend._consumer_event.clear()
    second_channel.closing.set_result(None)
    await task

    second_channel.queue_bind.assert_awaited_once_with(
        backend._queue_name, backend._exchange_name, 'group_a',
    )


@pytest.mark.asyncio
async def test__connect(mocker):
    mocker.patch(
        'loudhailer.backends.rabbitmq.aiormq.connect',
        return_value=mocker.MagicMock(connected=mocker.MagicMock(wait=mocker.AsyncMock())),
    )

    backend = RMQBackend('test://')

    await backend._connect()
    backend._connection.connected.wait.assert_awaited_once()
