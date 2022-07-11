#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
from abc import ABC, abstractmethod


class PublishError(Exception):
    pass


class BackendBase(ABC):
    def __init__(self, url, serialize_func, deserialize_func):
        raise NotImplementedError()

    @abstractmethod
    async def connect(self):
        raise NotImplementedError()

    @abstractmethod
    async def disconnect(self):
        raise NotImplementedError()

    @abstractmethod
    async def subscribe(self, group):
        raise NotImplementedError()

    @abstractmethod
    async def unsubscribe(self, group):
        raise NotImplementedError()

    @abstractmethod
    async def publish(self, channel, message):
        raise NotImplementedError()

    @abstractmethod
    async def next_published(self):
        raise NotImplementedError()
