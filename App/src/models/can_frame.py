"""Internal representation of one received classic CAN frame."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from config.constants import CAN_MAX_DATA_LENGTH, CAN_STANDARD_ID_MASK


class InvalidFrameError(ValueError):
    """Raised when a frame does not have a valid basic CAN structure."""


@dataclass(frozen=True)
class CANFrame:
    """A validated standard (11-bit) CAN frame.

    ``timestamp_ns`` is ``time.monotonic_ns()`` captured at the communication
    boundary when the frame was received, or ``None`` when not captured.
    The model carries no telemetry, fault or diagnostic meaning.
    """

    can_id: int
    data: bytes
    timestamp_ns: Optional[int] = None

    def __post_init__(self) -> None:
        if not 0 <= self.can_id <= CAN_STANDARD_ID_MASK:
            raise InvalidFrameError(f"CAN ID out of 11-bit range: {self.can_id:#x}")
        if len(self.data) > CAN_MAX_DATA_LENGTH:
            raise InvalidFrameError(f"payload longer than {CAN_MAX_DATA_LENGTH} bytes: {len(self.data)}")

    @property
    def length(self) -> int:
        """Payload length in bytes (the frame's DLC)."""
        return len(self.data)
