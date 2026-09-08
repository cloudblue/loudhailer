#
# This file is part of the CloudBlue Loudhailer.
#
# Copyright (c) 2025 CloudBlue. All Rights Reserved.
#
import shlex
import socket
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


def _wait_for_port(port, timeout=10):
    # A fixed sleep here is a race, not a wait: how long uvicorn takes to
    # actually bind and accept connections varies with interpreter/import
    # overhead (a 3s sleep silently stopped being enough on Python 3.12,
    # producing spurious ConnectionRefusedError in every e2e test). Poll the
    # actual socket instead so this only ever waits as long as it needs to.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            if sock.connect_ex(('127.0.0.1', port)) == 0:
                return
        time.sleep(0.05)
    raise RuntimeError(f'Nothing is listening on 127.0.0.1:{port} after {timeout}s')


@pytest.fixture(scope='session')
def fastapi_port():
    port = 18002
    proc = subprocess.Popen(
        shlex.split(
            f'uvicorn --host 127.0.0.1 --port {port} '
            '--workers 3 tests.e2e.apps.fastapi_app:app',
        ),
    )
    _wait_for_port(port)
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
    _wait_for_port(port)
    yield port
    proc.terminate()
    proc.wait()


@pytest.fixture(scope='session', autouse=True)
def django_setup():
    settings.configure(
        LOGGING_CONFIG={},
    )
    django.setup()
