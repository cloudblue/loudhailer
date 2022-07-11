#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import pytest

from loudhailer.backends.utils import blur_pwd


@pytest.mark.parametrize(
    ('url', 'expected'),
    (
        ('test://host:80/path', 'test://host:80/path'),
        ('test://host/path', 'test://host/path'),
        ('test://admin:password@host/path', 'test://admin:******@host/path'),
        ('test://admin:password@host:1234/path', 'test://admin:******@host:1234/path'),
    ),
)
def test_blur_pwd(url, expected):
    assert blur_pwd(url) == expected
