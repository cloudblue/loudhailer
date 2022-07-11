#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
from dataclasses import dataclass
from typing import Optional


@dataclass
class Message:
    group: str
    data: Optional[dict]
