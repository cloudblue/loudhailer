#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import shlex
import subprocess
import time

import django
import pytest
from django.conf import settings

from loudhailer import Loudhailer


@pytest.fixture
def test_backend(mocker):
    def _test_backend(schema='test'):
        mocked_backend = mocker.MagicMock()
        mocker.patch.object(
            Loudhailer, 'BACKENDS', {schema: mocked_backend},
        )
        return mocked_backend
    return _test_backend


@pytest.fixture(scope='session')
def fastapi_port():
    port = 18002
    proc = subprocess.Popen(
        shlex.split(
            f'uvicorn --host 127.0.0.1 --port {port} '
            '--workers 3 tests.e2e.apps.fastapi_app:app',
        ),
    )
    time.sleep(3)
    yield port
    proc.terminate()
    proc.wait()


@pytest.fixture(scope='session')
def channels_port():
    port = 18001
    proc = subprocess.Popen(
        shlex.split(
            f'uvicorn --host 127.0.0.1 --port {port} '
            '--workers 3 tests.e2e.apps.channels_app:app',
        ),
    )
    time.sleep(3)
    yield port
    proc.terminate()
    proc.wait()


@pytest.fixture(scope='session', autouse=True)
def django_setup():
    settings.configure(
        LOGGING_CONFIG={},
    )
    django.setup()
