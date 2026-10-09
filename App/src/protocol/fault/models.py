"""Decoded power module fault code."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class FaultCode(IntEnum):
    """Fault codes defined by CHALLENGE.md."""

    OVERTEMP = 1
    OVERVOLTAGE = 2
    UNDERVOLTAGE = 3
    ISOLATION_FAULT = 4


@dataclass(frozen=True)
class FaultResult:
    """One decoded fault message; ``module_id`` comes from the payload."""

    module_id: int
    code: FaultCode
