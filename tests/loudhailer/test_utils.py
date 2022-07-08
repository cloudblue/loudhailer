#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
from loudhailer.utils import rand_string


def test_rand_string():
    for i in range(30):
        assert len(rand_string(i)) == i
