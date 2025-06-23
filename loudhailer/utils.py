#
# This file is part of the CloudBlue Loudhailer.
#
# Copyright (c) 2025 CloudBlue. All Rights Reserved.
#
import string
import secrets


def rand_string(length):
    return ''.join([secrets.choice(string.ascii_letters) for _ in range(length)])
