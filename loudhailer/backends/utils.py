#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
from urllib.parse import urlparse, urlunparse


def blur_pwd(url):
    if '@' not in url:
        return url
    components = urlparse(url)
    credentials, location = components[1].split('@')
    username, password = credentials.split(':')
    new_loc = f'{username}:******@{location}'
    components = components._replace(netloc=new_loc)
    return urlunparse(components)
