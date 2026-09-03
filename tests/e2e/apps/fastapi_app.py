import asyncio
import contextlib
import logging
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from uvicorn.main import Server

from loudhailer import Loudhailer

from tests.e2e.settings import RABBITMQ_URL, REDIS_URL


original_handler = Server.handle_exit

logging.basicConfig()


class AppStatus:
    should_exit = False

    @staticmethod
    def handle_exit(*args, **kwargs):
        AppStatus.should_exit = True
        original_handler(*args, **kwargs)


Server.handle_exit = AppStatus.handle_exit


app = FastAPI()


async def _forward_messages(websocket, messages):
    while AppStatus.should_exit is False:
        try:
            message = await asyncio.wait_for(messages.get(), 0.1)
            await websocket.send_json({
                'pid': os.getpid(),
                'data': message,
            })
        except asyncio.TimeoutError:
            pass


async def _watch_disconnect(websocket):
    with contextlib.suppress(WebSocketDisconnect):
        while True:
            await websocket.receive()


async def _serve(websocket, loudhailer, group):
    # AppStatus.should_exit only ever flips under a single-worker uvicorn
    # process: with --workers N, uvicorn's per-worker subprocess never
    # installs its own SIGTERM handler, so the flag never becomes true there
    # and this loop alone would run forever after the client disconnects.
    # _watch_disconnect() is what actually ends the handler in that case, by
    # detecting the client closing the connection directly.
    async with loudhailer.subscribe(group) as messages:
        forward_task = asyncio.create_task(_forward_messages(websocket, messages))
        disconnect_task = asyncio.create_task(_watch_disconnect(websocket))
        try:
            await asyncio.wait(
                {forward_task, disconnect_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
        finally:
            for task in (forward_task, disconnect_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(forward_task, disconnect_task, return_exceptions=True)


@app.websocket("/ws1")
async def ws1(websocket: WebSocket):
    await websocket.accept()
    async with Loudhailer(RABBITMQ_URL) as loudhailer:
        await _serve(websocket, loudhailer, 'ws1')


@app.websocket("/ws2")
async def ws2(websocket: WebSocket):
    await websocket.accept()
    async with Loudhailer(REDIS_URL) as loudhailer:
        await _serve(websocket, loudhailer, 'ws2')
