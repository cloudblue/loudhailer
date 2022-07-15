#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
from abc import ABC, abstractmethod


class PublishError(Exception):
    pass


class BackendBase(ABC):

    @abstractmethod
    def __init__(self, url, **kwargs):
        raise NotImplementedError()

    @abstractmethod
    async def connect(self):
        raise NotImplementedError()

    @abstractmethod
    async def disconnect(self):
        raise NotImplementedError()

    @abstractmethod
    async def subscribe(self, channel):
        raise NotImplementedError()

    @abstractmethod
    async def unsubscribe(self, channel):
        raise NotImplementedError()

    @abstractmethod
    async def publish(self, envelope):
        raise NotImplementedError()

    @abstractmethod
    async def next_published(self):
        raise NotImplementedError()
