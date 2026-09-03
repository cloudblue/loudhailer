#
# This file is part of the CloudBlue Loudhailer.
#
# Copyright (c) 2025 CloudBlue. All Rights Reserved.
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
