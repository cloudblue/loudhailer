import asyncio
import logging
import os

from fastapi import FastAPI, WebSocket
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


@app.websocket("/ws1")
async def ws1(websocket: WebSocket):
    await websocket.accept()
    async with Loudhailer(RABBITMQ_URL) as loudhailer:
        async with loudhailer.subscribe('ws1') as messages:
            while AppStatus.should_exit is False:
                try:
                    message = await asyncio.wait_for(messages.get(), 0.1)
                    await websocket.send_json({
                        'pid': os.getpid(),
                        'data': message,
                    })
                except asyncio.TimeoutError:
                    pass


@app.websocket("/ws2")
async def ws2(websocket: WebSocket):
    await websocket.accept()
    async with Loudhailer(REDIS_URL) as loudhailer:
        async with loudhailer.subscribe('ws2') as messages:
            while AppStatus.should_exit is False:
                try:
                    message = await asyncio.wait_for(messages.get(), 0.1)
                    await websocket.send_json({
                        'pid': os.getpid(),
                        'data': message,
                    })
                except asyncio.TimeoutError:
                    pass
