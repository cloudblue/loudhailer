#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2025 CloudBlue. All Rights Reserved.
#
from loudhailer.utils import rand_string


def test_rand_string():
    for i in range(30):
        assert len(rand_string(i)) == i
