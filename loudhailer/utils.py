#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
import string
import secrets


def rand_string(length):
    return ''.join([secrets.choice(string.ascii_letters) for _ in range(length)])
