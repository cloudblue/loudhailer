#
# This file is part of the Ingram Micro CloudBlue Loudhailer.
#
# Copyright (c) 2022 Ingram Micro. All Rights Reserved.
#
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Envelope:
    recipient: str
    recipient_type: Optional[str]
    message: Optional[Any]


class RecipientType:
    DIRECT = 'direct'
    GROUP = 'group'
