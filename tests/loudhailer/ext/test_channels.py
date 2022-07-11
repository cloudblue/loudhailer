#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import logging

import msgpack
import pytest

from loudhailer.ext.channels import LoudhailerChannelLayer, LoudhailerChannelLifespan


def test_layer_initialization_url_mandatory():
    with pytest.raises(AssertionError) as exc:
        LoudhailerChannelLayer()

    assert str(exc.value) == 'URL is mandatory'


def test_layer_initialization(mocker):
    mocked_loudhailer = mocker.patch('loudhailer.ext.channels.Loudhailer')

    layer = LoudhailerChannelLayer(url='test://')

    mocked_loudhailer.assert_called_once_with(
        'test://',
        serialize_func=layer.serialize,
        deserialize_func=layer.deserialize,
    )


def test_layer_serialize(mocker):
    mocker.patch('loudhailer.ext.channels.Loudhailer')

    layer = LoudhailerChannelLayer(url='test://')
    message = {'test': 'message'}
    expected_message = msgpack.packb({
        **message,
        '__asgi_group__': 'my_group',
    })
    assert layer.serialize('my_group', message) == expected_message


def test_layer_deserialize(mocker):
    mocker.patch('loudhailer.ext.channels.Loudhailer')

    layer = LoudhailerChannelLayer(url='test://')
    message = {'test': 'message'}
    message_bytes = msgpack.packb({
        '__asgi_group__': 'my_group',
        **message,
    })
    assert layer.deserialize('my_group', message_bytes) == message


@pytest.mark.asyncio
async def test_layer_new_channel(mocker):
    mocker.patch('loudhailer.ext.channels.Loudhailer')
    mocker.patch('loudhailer.ext.channels.rand_string', return_value='a1b2c3d4')

    layer = LoudhailerChannelLayer(url='test://')
    assert await layer.new_channel() == 'specific.loudhailer!a1b2c3d4'


@pytest.mark.asyncio
async def test_layer_connect(mocker, caplog):
    mocked_loudhailer = mocker.MagicMock(
        connect=mocker.AsyncMock(),
    )
    mocker.patch('loudhailer.ext.channels.Loudhailer', return_value=mocked_loudhailer)
    layer = LoudhailerChannelLayer(url='test://')

    with caplog.at_level(logging.INFO):
        await layer.connect()

    mocked_loudhailer.connect.assert_awaited_once()

    assert 'Loudhailer channel layer connected.' in caplog.text


@pytest.mark.asyncio
async def test_layer_disconnect(mocker, caplog):
    mocked_loudhailer = mocker.MagicMock(
        disconnect=mocker.AsyncMock(),
    )
    mocker.patch('loudhailer.ext.channels.Loudhailer', return_value=mocked_loudhailer)
    layer = LoudhailerChannelLayer(url='test://')

    with caplog.at_level(logging.INFO):
        await layer.disconnect()

    mocked_loudhailer.disconnect.assert_awaited_once()

    assert 'Loudhailer channel layer disconnected.' in caplog.text


@pytest.mark.asyncio
async def test_layer_receive(mocker):
    mocked_loudhailer = mocker.MagicMock(
        receive_message=mocker.AsyncMock(return_value={'a': 'message'}),
    )
    mocker.patch('loudhailer.ext.channels.Loudhailer', return_value=mocked_loudhailer)
    layer = LoudhailerChannelLayer(url='test://')

    assert await layer.receive('my_channel') == {'a': 'message'}

    mocked_loudhailer.receive_message.assert_awaited_once_with('my_channel')


@pytest.mark.asyncio
async def test_layer_group_add(mocker):
    mocked_loudhailer = mocker.MagicMock(
        register_subscription=mocker.AsyncMock(),
    )
    mocker.patch('loudhailer.ext.channels.Loudhailer', return_value=mocked_loudhailer)
    layer = LoudhailerChannelLayer(url='test://')

    await layer.group_add('my_group', 'my_channel')

    mocked_loudhailer.register_subscription.assert_awaited_once_with('my_group', 'my_channel')


@pytest.mark.asyncio
async def test_layer_group_discard(mocker):
    mocked_loudhailer = mocker.MagicMock(
        unregister_subscription=mocker.AsyncMock(),
    )
    mocker.patch('loudhailer.ext.channels.Loudhailer', return_value=mocked_loudhailer)
    layer = LoudhailerChannelLayer(url='test://')

    await layer.group_discard('my_group', 'my_channel')

    mocked_loudhailer.unregister_subscription.assert_awaited_once_with('my_group', 'my_channel')


@pytest.mark.asyncio
async def test_layer_group_send(mocker):
    mocked_loudhailer = mocker.MagicMock(
        publish=mocker.AsyncMock(),
    )
    mocker.patch('loudhailer.ext.channels.Loudhailer', return_value=mocked_loudhailer)
    layer = LoudhailerChannelLayer(url='test://')

    await layer.group_send('my_group', {'a': 'message'})

    mocked_loudhailer.publish.assert_awaited_once_with('my_group', {'a': 'message'})


@pytest.mark.asyncio
async def test_lifespan_startup(mocker):
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=None)
    mocked_send = mocker.patch('loudhailer.ext.channels.asgi_application_startup.send')
    handler = LoudhailerChannelLifespan()
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.startup'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    mocked_send.assert_called()
    send.assert_awaited_once_with({'type': 'lifespan.startup.complete'})


@pytest.mark.asyncio
async def test_lifespan_startup_with_async_hook(mocker, capsys):
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=None)
    mocker.patch('loudhailer.ext.channels.asgi_application_startup.send')

    async def on_startup():
        print('on startup hook invoked')

    handler = LoudhailerChannelLifespan(on_startup=on_startup)
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.startup'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    send.assert_awaited_once_with({'type': 'lifespan.startup.complete'})
    captured = capsys.readouterr()
    assert 'on startup hook invoked' in captured.out


@pytest.mark.asyncio
async def test_lifespan_startup_with_sync_hook(mocker, capsys):
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=None)
    mocker.patch('loudhailer.ext.channels.asgi_application_startup.send')

    def on_startup():
        print('on startup hook invoked')

    handler = LoudhailerChannelLifespan(on_startup=on_startup)
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.startup'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    send.assert_awaited_once_with({'type': 'lifespan.startup.complete'})
    captured = capsys.readouterr()
    assert 'on startup hook invoked' in captured.out


@pytest.mark.asyncio
async def test_lifespan_startup_with_layer(mocker):
    mocked_layer = mocker.MagicMock(connect=mocker.AsyncMock())
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=mocked_layer)
    mocked_send = mocker.patch('loudhailer.ext.channels.asgi_application_startup.send')
    handler = LoudhailerChannelLifespan()
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.startup'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    mocked_send.assert_called()
    send.assert_awaited_once_with({'type': 'lifespan.startup.complete'})
    mocked_layer.connect.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_shutdown(mocker):
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=None)
    mocked_send = mocker.patch('loudhailer.ext.channels.asgi_application_shutdown.send')
    handler = LoudhailerChannelLifespan()
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.shutdown'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    mocked_send.assert_called()
    send.assert_awaited_once_with({'type': 'lifespan.shutdown.complete'})


@pytest.mark.asyncio
async def test_lifespan_shutdown_with_async_hook(mocker, capsys):
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=None)
    mocker.patch('loudhailer.ext.channels.asgi_application_shutdown.send')

    async def on_shutdown():
        print('on shutdown hook invoked')

    handler = LoudhailerChannelLifespan(on_shutdown=on_shutdown)
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.shutdown'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    send.assert_awaited_once_with({'type': 'lifespan.shutdown.complete'})
    captured = capsys.readouterr()
    assert 'on shutdown hook invoked' in captured.out


@pytest.mark.asyncio
async def test_lifespan_shutdown_with_sync_hook(mocker, capsys):
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=None)
    mocker.patch('loudhailer.ext.channels.asgi_application_shutdown.send')

    def on_shutdown():
        print('on shutdown hook invoked')

    handler = LoudhailerChannelLifespan(on_shutdown=on_shutdown)
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.shutdown'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    send.assert_awaited_once_with({'type': 'lifespan.shutdown.complete'})
    captured = capsys.readouterr()
    assert 'on shutdown hook invoked' in captured.out


@pytest.mark.asyncio
async def test_lifespan_shutdown_with_layer(mocker):
    mocked_layer = mocker.MagicMock(disconnect=mocker.AsyncMock())
    mocker.patch('loudhailer.ext.channels.get_channel_layer', return_value=mocked_layer)
    mocked_send = mocker.patch('loudhailer.ext.channels.asgi_application_shutdown.send')
    handler = LoudhailerChannelLifespan()
    send = mocker.AsyncMock()
    receive = mocker.AsyncMock(return_value={'type': 'lifespan.shutdown'})
    await handler.process_lifespan_event({'type': 'lifespan'}, receive, send)
    mocked_send.assert_called()
    send.assert_awaited_once_with({'type': 'lifespan.shutdown.complete'})
    mocked_layer.disconnect.assert_awaited_once()


@pytest.mark.asyncio
async def test_lifespan_as_asgi(mocker):
    mocked_on_startup = mocker.MagicMock()
    mocked_on_shutdown = mocker.MagicMock()

    mocked_call = mocker.patch.object(LoudhailerChannelLifespan, '__call__')

    app = LoudhailerChannelLifespan.as_asgi(
        on_startup=mocked_on_startup,
        on_shutdown=mocked_on_shutdown,
    )

    await app('scope', 'receive', 'send')

    mocked_call.assert_awaited_once_with('scope', 'receive', 'send')

    assert app.handler_class == LoudhailerChannelLifespan
    assert app.handler_initkwargs == {
        'on_startup': mocked_on_startup,
        'on_shutdown': mocked_on_shutdown,
    }