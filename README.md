# Loudhailer

![pyversions](https://img.shields.io/pypi/pyversions/loudhailer.svg) [![PyPi Status](https://img.shields.io/pypi/v/loudhailer.svg)](https://pypi.org/project/loudhailer/) [![Test Loudhailer](https://github.com/cloudblue/loudhailer/actions/workflows/test.yml/badge.svg)](https://github.com/cloudblue/loudhailer/actions/workflows/test.yml) [![Quality Gate Status](https://sonarcloud.io/api/project_badges/measure?project=loudhailer&metric=alert_status)](https://sonarcloud.io/dashboard?id=loudhailer) [![Coverage](https://sonarcloud.io/api/project_badges/measure?project=loudhailer&metric=coverage)](https://sonarcloud.io/dashboard?id=loudhailer) [![Maintainability Rating](https://sonarcloud.io/api/project_badges/measure?project=loudhailer&metric=sqale_rating)](https://sonarcloud.io/dashboard?id=loudhailer)

## Introduction

`Loudhailer` is a python library that allows to send broadcast messages to groups of consumers. It has been designed for being used in asynchronous applications.

This initial release natively supports RabbitMQ and Redis backends and can be easily extended to support more backends.

`Loudhailer` includes an extension that allows you to use in django-channels based projects.


> Please note that the current version of Loudhailer have to be considered a beta release since it is still under heavy development.




## Install

`Loudhailer` requires python 3.8 or later.


`Loudhailer` can be installed from [pypi.org](https://pypi.org/project/loudhailer/) using pip:

```
$ pip install loudhailer
```

If you plan to use it with django-channels you must install the optional channels dependency:

```
$ pip install loudhailer[channels]
```


## Basic usage

### Publishing messages

```python
from loudhailer import Loudhailer


async with Loudhailer('amqp://localhost') as loudhailer:
    await loudhailer.publish('my_group', {'message': 'data'})
```

### Subscribe to group and receive messages

```python

from loudhailer import Loudhailer


with Loudhailer('amqp://localhost') as loudhailer:
    with loudhailer.subscribe('my_group') as messages:
        message = await messages.get()
        print(f'received message: {message}')
```

## Django channels extension

The django-channels extension is an implementation of the Channel Layers specifications.

In order to properly works it need to add a ASGI lifespan handler to your channels application.


> Please note that Channel Layers specification are not yet fully implemented, only group messaging is supported in this
initial release.


### Django settings

Add the following Channel Layers configuration to your Django settings module:

```python 
CHANNEL_LAYERS = {
    'default': {
        'BACKEND': 'loudhailer.ext.channels.LoudhailerChannelLayer',
        'CONFIG': {
            'url': 'amqp://localhost',
        },
    },
}
```

### Configure the ASGI lifespan handler

Add the following configuration to your root channels routing module:

```python
from channels.routing import ProtocolTypeRouter, URLRouter
from loudhailer.ext.channels import LoudhailerChannelLifespan

application = ProtocolTypeRouter(
    {
        'lifespan': LoudhailerChannelLifespan.as_asgi(),
        'websocket': URLRouter(...),
    },
)
```

In case you already have an handler to process lifespan **startup** and **shutdown** events you can be notified of
such event by the *LoudhailerChannelLifespan* handler in two ways:

#### Using django signals

You can register your signal handler for **startup** and **shutdown** events in the following way:

```python
from django.dispatch import receiver
from loudhailer.ext.channels import asgi_application_shutdown, asgi_application_startup


@receiver(asgi_application_startup)
def handle_startup(sender, **kwargs):
    pass

@receiver(asgi_application_shutdown)
def handle_shutdown(sender, **kwargs):
    pass
```

#### Using **on_startup** and **on_shutdown** hooks

```python
from channels.routing import ProtocolTypeRouter, URLRouter
from loudhailer.ext.channels import LoudhailerChannelLifespan

async def on_startup():
    pass


async def on_shutdown():
    pass


application = ProtocolTypeRouter(
    {
        'lifespan': LoudhailerChannelLifespan.as_asgi(
            on_startup=on_startup, on_shutdown=on_shutdown,
        ),
        'websocket': URLRouter(...),
    },
)
```

Please note that the **on_startup** and **on_shutdown** hooks can be implemented both as synchronous or asynchronous functions.


## License

`Loudhailer` is released under the [Apache License Version 2.0](https://www.apache.org/licenses/LICENSE-2.0).