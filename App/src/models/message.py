"""Protocol-independent complete message delivered by a transport."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional


class FramingMode(Enum):
    """How a source's messages are framed on the medium."""

    SINGLE_FRAME = "single_frame"
    SEGMENTED = "segmented"


@dataclass(frozen=True)
class TransportMetadata:
    """Transport-level facts about how a message was obtained.

    ``received_at_ns`` is the communication-boundary timestamp of the frame that
    completed the message. ``completed_at_ns`` is the transport clock
    (``time.monotonic_ns()``) read at the moment the message became complete,
    i.e. when reassembly finished for a segmented message. It is the grader's
    ``diag_complete.ts_ns`` and every later layer carries it unchanged.
    """

    framing: FramingMode
    frame_count: int
    received_at_ns: Optional[int] = None
    completed_at_ns: Optional[int] = None


@dataclass(frozen=True)
class Message:
    """A complete message, independent of the medium it arrived on.

    ``message_id`` identifies what was received (the CAN ID on CAN).
    ``source_id`` identifies the transport source/context that produced it; on
    this CAN bus each module uses its own IDs, so it equals the CAN ID. The
    payload is opaque: the transport never interprets it.
    """

    message_id: int
    payload: bytes
    metadata: TransportMetadata
    source_id: Optional[int] = None
