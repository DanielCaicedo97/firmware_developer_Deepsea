"""Shared builders and test doubles for every test type.

Nothing here transmits on a CAN bus: frames are built in memory and the fake
socket has no send method.
"""

from __future__ import annotations

import socket
import struct
from typing import Any, List, Optional, Tuple, Union

from config.constants import (
    CAN_FRAME_FORMAT,
    CAN_MAX_DATA_LENGTH,
    FIRST_FRAME_LENGTH_HIGH_MASK,
    PCI_CONSECUTIVE_FRAME,
    PCI_FIRST_FRAME,
    SEQUENCE_NUMBER_MASK,
)
from controllers.base_controller import BaseController
from controllers.results import ControllerResult, ControllerStatus
from models.application_event import ApplicationEvent, EventType
from models.can_frame import CANFrame
from models.message import FramingMode, Message, TransportMetadata
from services.application_state import ApplicationState
from services.event_publisher import EventConsumer, EventPublisher
from services.stats_service import StatsService
from transport.listener import TransportListener

FIRST_FRAME_DATA_SIZE = 6
CONSECUTIVE_FRAME_DATA_SIZE = 7
STATS_INTERVAL_NS = 1_000

ReceiveItem = Union[bytes, BaseException]


# --- CANFrame builders --------------------------------------------------------


def first_frame(can_id: int, declared_length: int, first_data: bytes) -> CANFrame:
    """Build a First Frame declaring ``declared_length`` total bytes."""
    header = bytes([PCI_FIRST_FRAME | ((declared_length >> 8) & FIRST_FRAME_LENGTH_HIGH_MASK), declared_length & 0xFF])
    data = (header + first_data[:FIRST_FRAME_DATA_SIZE]).ljust(CAN_MAX_DATA_LENGTH, b"\x00")
    return CANFrame(can_id=can_id, data=data)


def consecutive_frame(can_id: int, sequence_number: int, chunk: bytes) -> CANFrame:
    """Build a padded Consecutive Frame with the given sequence nibble."""
    header = bytes([PCI_CONSECUTIVE_FRAME | (sequence_number & SEQUENCE_NUMBER_MASK)])
    data = (header + chunk[:CONSECUTIVE_FRAME_DATA_SIZE]).ljust(CAN_MAX_DATA_LENGTH, b"\x00")
    return CANFrame(can_id=can_id, data=data)


def segment_message(can_id: int, message: bytes) -> List[CANFrame]:
    """Split ``message`` into a First Frame followed by its Consecutive Frames."""
    frames = [first_frame(can_id, len(message), message[:FIRST_FRAME_DATA_SIZE])]
    rest = message[FIRST_FRAME_DATA_SIZE:]
    sequence_number = 1
    for offset in range(0, len(rest), CONSECUTIVE_FRAME_DATA_SIZE):
        frames.append(consecutive_frame(can_id, sequence_number, rest[offset:offset + CONSECUTIVE_FRAME_DATA_SIZE]))
        sequence_number = (sequence_number + 1) & SEQUENCE_NUMBER_MASK
    return frames


def interleave(*frame_lists: List[CANFrame]) -> List[CANFrame]:
    """Round-robin interleave several frame sequences, like the generator does."""
    interleaved: List[CANFrame] = []
    longest = max(len(frames) for frames in frame_lists)
    for index in range(longest):
        for frames in frame_lists:
            if index < len(frames):
                interleaved.append(frames[index])
    return interleaved


# --- Complete-message builder -------------------------------------------------


def complete_message(
    message_id: int,
    payload: bytes,
    framing: FramingMode = FramingMode.SINGLE_FRAME,
    completed_at_ns: Optional[int] = None,
) -> Message:
    """Build a complete message as the transport would deliver it."""
    metadata = TransportMetadata(framing=framing, frame_count=1, received_at_ns=None, completed_at_ns=completed_at_ns)
    return Message(message_id=message_id, payload=payload, metadata=metadata, source_id=message_id)


# --- Raw SocketCAN bytes --------------------------------------------------------


def raw_can_frame(raw_id: int, data: bytes, dlc: Optional[int] = None) -> bytes:
    """Lay out bytes exactly as the kernel returns a ``struct can_frame``."""
    length = len(data) if dlc is None else dlc
    return struct.pack(CAN_FRAME_FORMAT, raw_id, length, data.ljust(CAN_MAX_DATA_LENGTH, b"\x00"))


def to_raw(frame: CANFrame) -> bytes:
    """Convert a ``CANFrame`` back into raw socket bytes."""
    return raw_can_frame(frame.can_id, frame.data)


# --- Test doubles -----------------------------------------------------------------


class FakeCanSocket:
    """Receive-only stand-in for a raw CAN socket. It has no send method.

    ``recv`` returns queued raw frames in order, raises queued exceptions, and
    raises ``socket.timeout`` once the queue is empty.
    """

    def __init__(self, items: Optional[List[ReceiveItem]] = None, bind_error: Optional[OSError] = None) -> None:
        self.items = list(items or [])
        self.bind_error = bind_error
        self.bound_to: Optional[Tuple[str]] = None
        self.timeout: Optional[float] = None
        self.options: List[Tuple[int, int, int]] = []
        self.closed = False

    def settimeout(self, timeout: float) -> None:
        """Record the timeout."""
        self.timeout = timeout

    def setsockopt(self, level: int, option: int, value: int) -> None:
        """Record a socket option."""
        self.options.append((level, option, value))

    def bind(self, address: Tuple[str]) -> None:
        """Record the address, or raise the configured bind error."""
        if self.bind_error is not None:
            raise self.bind_error
        self.bound_to = address

    def recv(self, size: int) -> bytes:
        """Return the next queued frame, or raise the next queued exception."""
        item = self.items.pop(0) if self.items else socket.timeout()
        if isinstance(item, BaseException):
            raise item
        return item

    def close(self) -> None:
        """Mark the socket closed."""
        self.closed = True


class RecordingListener(TransportListener):
    """Collects every complete message delivered by a transport."""

    def __init__(self) -> None:
        self.messages: List[Message] = []

    def on_message(self, message: Message) -> None:
        """Record a delivered message."""
        self.messages.append(message)


class RecordingConsumer(EventConsumer):
    """Collects every application event delivered to it."""

    def __init__(self) -> None:
        self.events: List[ApplicationEvent] = []

    def on_event(self, event: ApplicationEvent) -> None:
        """Record a delivered event."""
        self.events.append(event)


class RecordingPublisher(EventPublisher):
    """A real ``EventPublisher`` with one ``RecordingConsumer`` registered."""

    def __init__(self) -> None:
        super().__init__()
        self.consumer = RecordingConsumer()
        self.register(self.consumer)

    @property
    def events(self) -> List[ApplicationEvent]:
        """Every event published so far."""
        return self.consumer.events


class RecordingController(BaseController[Any]):
    """Controller double that records each (result, message) it handles and accepts it."""

    event_type = EventType.TELEMETRY

    def __init__(self) -> None:
        super().__init__(ApplicationState(), StatsService(STATS_INTERVAL_NS), RecordingPublisher())
        self.handled: List[Tuple[Any, Message]] = []

    def handle(self, result: Any, message: Message) -> ControllerResult:
        """Record a handled result and its message."""
        self.handled.append((result, message))
        return ControllerResult(ControllerStatus.PROCESSED, result)


class FakeClock:
    """Monotonic nanosecond clock double; ``now`` is set by the test."""

    def __init__(self, now: int = 0) -> None:
        self.now = now

    def __call__(self) -> int:
        """Return the current fake time."""
        return self.now
