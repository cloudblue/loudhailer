#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import asyncio

import pytest

from loudhailer import Loudhailer
from loudhailer.dataclasses import Message
from loudhailer.loudhailer import default_deserialize, default_serialize, MessageIterator


def test_initialization(mocker, test_backend):
    mocked_backend = test_backend()
    Loudhailer('test://')

    mocked_backend.assert_called_once_with(
        'test://',
        default_serialize,
        default_deserialize,
    )


def test_initialization_custom_serialization(mocker, test_backend):
    mocked_backend = test_backend()
    mocked_serialize = mocker.MagicMock()
    mocked_deserialize = mocker.MagicMock()
    Loudhailer(
        'test://',
        serialize_func=mocked_serialize,
        deserialize_func=mocked_deserialize,
    )

    mocked_backend.assert_called_once_with(
        'test://',
        mocked_serialize,
        mocked_deserialize,
    )


def test_initialization_unsupported_backend():
    with pytest.raises(AssertionError) as exc:
        Loudhailer('test://')
    assert str(exc.value) == "No backend available for schema 'test'"


@pytest.mark.asyncio
async def test_context_manager(mocker, test_backend):
    test_backend()
    mocked_connect = mocker.patch.object(Loudhailer, 'connect')
    mocked_disconnect = mocker.patch.object(Loudhailer, 'disconnect')

    loudhailer = Loudhailer('test://')

    async with loudhailer as lh:
        assert lh == loudhailer
        mocked_connect.assert_awaited_once()

    mocked_disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_connect(mocker, test_backend):
    test_backend()
    mocked_connect = mocker.AsyncMock()
    mocked_listener = mocker.patch.object(Loudhailer, '_listener')

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(connect=mocked_connect)
    await loudhailer.connect()

    mocked_connect.assert_awaited_once()

    tasks = [
        t for t in asyncio.all_tasks() if t is not asyncio.current_task()
    ]

    assert len(tasks) == 1
    await asyncio.gather(*tasks)

    mocked_listener.assert_awaited_once()


@pytest.mark.asyncio
async def test_disconnect(mocker, test_backend):
    test_backend()
    mocked_disconnect = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(disconnect=mocked_disconnect)
    loudhailer._listener_task = mocker.MagicMock()
    loudhailer._listener_task.done.return_value = True

    await loudhailer.disconnect()

    mocked_disconnect.assert_awaited_once()
    loudhailer._listener_task.result.assert_called_once()


@pytest.mark.asyncio
async def test_disconnect_listner_working(mocker, test_backend):
    test_backend()
    mocked_disconnect = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(disconnect=mocked_disconnect)
    loudhailer._listener_task = mocker.MagicMock()
    loudhailer._listener_task.done.return_value = False

    await loudhailer.disconnect()

    mocked_disconnect.assert_awaited_once()
    loudhailer._listener_task.cancel.assert_called_once()


@pytest.mark.asyncio
async def test_publish(mocker, test_backend):
    test_backend()
    mocked_publish = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(publish=mocked_publish)

    await loudhailer.publish('group', 'message')

    mocked_publish.assert_awaited_once_with('group', 'message')


@pytest.mark.asyncio
async def test_register_subscription(mocker, test_backend):
    test_backend()
    mocked_subscribe = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(subscribe=mocked_subscribe)

    subscriber = await loudhailer.register_subscription('group', subscriber='my_subscriber')
    assert subscriber == 'my_subscriber'
    mocked_subscribe.assert_awaited_once_with('group')
    assert loudhailer._subscriptions['group'] == set(['my_subscriber'])
    assert isinstance(loudhailer._subscribers['my_subscriber'], asyncio.Queue)


@pytest.mark.asyncio
async def test_register_subscription_group_exists(mocker, test_backend):
    test_backend()
    mocked_subscribe = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(subscribe=mocked_subscribe)
    loudhailer._subscriptions['group'] = set(['another_subscriber'])

    subscriber = await loudhailer.register_subscription('group', subscriber='my_subscriber')
    assert subscriber == 'my_subscriber'
    mocked_subscribe.assert_not_awaited()
    assert loudhailer._subscriptions['group'] == set(['my_subscriber', 'another_subscriber'])
    assert isinstance(loudhailer._subscribers['my_subscriber'], asyncio.Queue)


@pytest.mark.asyncio
async def test_unregister_subscription(mocker, test_backend):
    test_backend()
    mocked_unsubscribe = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(unsubscribe=mocked_unsubscribe)
    loudhailer._subscriptions['group'] = set(['my_subscriber'])
    loudhailer._subscribers['my_subscriber'] = 'whatever'

    await loudhailer.unregister_subscription('group', 'my_subscriber')
    assert loudhailer._subscriptions['group'] == set()
    assert 'my_subscriber' not in loudhailer._subscribers
    mocked_unsubscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_unregister_subscription_multiple_subscribers(mocker, test_backend):
    test_backend()
    mocked_unsubscribe = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(unsubscribe=mocked_unsubscribe)
    loudhailer._subscriptions['group'] = set(['my_subscriber', 'another_subscriber'])
    loudhailer._subscribers['my_subscriber'] = 'whatever'

    await loudhailer.unregister_subscription('group', 'my_subscriber')
    assert loudhailer._subscriptions['group'] == set(['another_subscriber'])
    assert 'my_subscriber' not in loudhailer._subscribers
    mocked_unsubscribe.assert_not_awaited()


@pytest.mark.asyncio
async def test_unregister_subscription_no_group(mocker, test_backend):
    test_backend()
    mocked_unsubscribe = mocker.AsyncMock()

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(unsubscribe=mocked_unsubscribe)

    await loudhailer.unregister_subscription('group', 'my_subscriber')

    mocked_unsubscribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_receive_message(mocker, test_backend):
    test_backend()

    loudhailer = Loudhailer('test://')
    queue = asyncio.Queue()
    await queue.put('an_item')
    loudhailer._subscribers['my_subscriber'] = queue

    assert await loudhailer.receive_message('my_subscriber') == 'an_item'


@pytest.mark.asyncio
async def test_subscribe(mocker, test_backend):
    test_backend()
    mocked_register = mocker.patch.object(
        Loudhailer, 'register_subscription', return_value='my_subscriber',
    )
    mocked_unregister = mocker.patch.object(Loudhailer, 'unregister_subscription')

    loudhailer = Loudhailer('test://')
    queue = asyncio.Queue()
    await queue.put('an_item')
    loudhailer._subscribers['my_subscriber'] = queue

    async with loudhailer.subscribe('group', subscriber='my_subscriber') as msgiter:
        assert isinstance(msgiter, MessageIterator)
        assert await msgiter.get() == 'an_item'
        mocked_register.assert_awaited_once_with('group', 'my_subscriber')

    mocked_unregister.assert_awaited_once_with('group', 'my_subscriber')


@pytest.mark.asyncio
async def test_listener(mocker, test_backend):
    test_backend()

    queue = asyncio.Queue()
    await queue.put(Message('my_group', 'an_item'))

    loudhailer = Loudhailer('test://')
    loudhailer._backend = mocker.MagicMock(next_published=queue.get)
    loudhailer._subscriptions['my_group'] = set(['subscriber1', 'subscriber2'])
    loudhailer._subscribers['subscriber1'] = asyncio.Queue()
    loudhailer._subscribers['subscriber2'] = asyncio.Queue()
    task = asyncio.create_task(loudhailer._listener())
    await asyncio.sleep(0.01)
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    assert await loudhailer.receive_message('subscriber1') == 'an_item'
    assert await loudhailer.receive_message('subscriber2') == 'an_item'
