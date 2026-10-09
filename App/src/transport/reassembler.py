"""ISO 15765-2-style segmented message reassembly with one context per source.

State machine per source context::

    IDLE --valid FF--> RECEIVING --CF ok--> RECEIVING
                       RECEIVING --last CF--> IDLE (message completed)
                       RECEIVING --bad seq / malformed CF--> IDLE (abandoned)
                       RECEIVING --any FF--> previous attempt abandoned, FF re-evaluated
    IDLE --CF--> IDLE (orphan, ignored)

Contexts are created once, one per configured source, and reset in place, so
the number of contexts and the size of each buffer are fixed by configuration.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Iterable, Mapping, Optional

from config.constants import (
    CAN_MAX_DATA_LENGTH,
    CONSECUTIVE_FRAME_HEADER_SIZE,
    FIRST_FRAME_HEADER_SIZE,
    FIRST_FRAME_LENGTH_HIGH_MASK,
    FIRST_SEQUENCE_NUMBER,
    MIN_SEGMENTED_MESSAGE_LENGTH,
    PCI_CONSECUTIVE_FRAME,
    PCI_FIRST_FRAME,
    PCI_TYPE_MASK,
    SEQUENCE_NUMBER_MASK,
)
from models.can_frame import CANFrame

logger = logging.getLogger(__name__)


class ContextState(Enum):
    """Reassembly state of one source context."""

    IDLE = "idle"
    RECEIVING = "receiving"


class ReassemblyOutcome(Enum):
    """Result of feeding one frame to the reassembler."""

    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ORPHAN_CONSECUTIVE_FRAME = "orphan_consecutive_frame"
    SEQUENCE_ERROR = "sequence_error"
    OVERSIZED = "oversized"
    INVALID_LENGTH = "invalid_length"
    MALFORMED_FRAME = "malformed_frame"
    UNSUPPORTED_FRAME_TYPE = "unsupported_frame_type"
    UNKNOWN_SOURCE = "unknown_source"


@dataclass(frozen=True)
class ReassemblyResult:
    """Outcome of one frame; ``payload`` is set only when ``COMPLETED``."""

    outcome: ReassemblyOutcome
    payload: Optional[bytes] = None
    frame_count: int = 0


class ReassemblyContext:
    """Reassembly state for a single source. Holds at most ``max_length`` bytes."""

    def __init__(self, source_id: int, max_length: int) -> None:
        self.source_id = source_id
        self.max_length = max_length
        self.state = ContextState.IDLE
        self.expected_length = 0
        self.expected_sequence = FIRST_SEQUENCE_NUMBER
        self.frame_count = 0
        self._buffer = bytearray()

    @property
    def received_length(self) -> int:
        """Number of payload bytes accumulated so far."""
        return len(self._buffer)

    def start(self, declared_length: int, first_data: bytes) -> None:
        """Begin a new message, discarding anything previously held."""
        self.reset()
        self.state = ContextState.RECEIVING
        self.expected_length = declared_length
        self.frame_count = 1
        self._buffer += first_data[:declared_length]

    def append(self, data: bytes) -> bool:
        """Append Consecutive Frame data; return True once the message is complete.

        Bytes past the declared length (final-frame padding) are discarded.
        """
        remaining = self.expected_length - len(self._buffer)
        self._buffer += data[:remaining]
        self.frame_count += 1
        self.expected_sequence = (self.expected_sequence + 1) & SEQUENCE_NUMBER_MASK
        return len(self._buffer) >= self.expected_length

    def take_payload(self) -> ReassemblyResult:
        """Return the completed message and reset the context."""
        result = ReassemblyResult(ReassemblyOutcome.COMPLETED, bytes(self._buffer), self.frame_count)
        self.reset()
        return result

    def reset(self) -> None:
        """Return to IDLE and release the payload buffer."""
        self.state = ContextState.IDLE
        self.expected_length = 0
        self.expected_sequence = FIRST_SEQUENCE_NUMBER
        self.frame_count = 0
        # A fresh buffer guarantees no reference to abandoned data survives.
        self._buffer = bytearray()


class SegmentedReassembler:
    """Reassembles First/Consecutive Frame sequences independently per source."""

    def __init__(self, source_ids: Iterable[int], max_message_length: int) -> None:
        self.max_message_length = max_message_length
        self._contexts = {source_id: ReassemblyContext(source_id, max_message_length) for source_id in source_ids}

    @property
    def contexts(self) -> Mapping[int, ReassemblyContext]:
        """Read-only view of the per-source contexts (fixed set)."""
        return MappingProxyType(self._contexts)

    def process(self, frame: CANFrame) -> ReassemblyResult:
        """Feed one frame to its source's context and report the outcome."""
        context = self._contexts.get(frame.can_id)
        if context is None:
            return ReassemblyResult(ReassemblyOutcome.UNKNOWN_SOURCE)
        if frame.length == 0:
            return ReassemblyResult(ReassemblyOutcome.MALFORMED_FRAME)
        frame_type = frame.data[0] & PCI_TYPE_MASK
        if frame_type == PCI_FIRST_FRAME:
            return self._handle_first_frame(context, frame)
        if frame_type == PCI_CONSECUTIVE_FRAME:
            return self._handle_consecutive_frame(context, frame)
        return ReassemblyResult(ReassemblyOutcome.UNSUPPORTED_FRAME_TYPE)

    def reset_all(self) -> None:
        """Abandon every in-progress message."""
        for context in self._contexts.values():
            context.reset()

    def _handle_first_frame(self, context: ReassemblyContext, frame: CANFrame) -> ReassemblyResult:
        """Start a new message; any First Frame ends the previous attempt."""
        if context.state is ContextState.RECEIVING:
            logger.debug("source %#x: First Frame restarts unfinished message", context.source_id)
        context.reset()
        if frame.length < CAN_MAX_DATA_LENGTH:
            return ReassemblyResult(ReassemblyOutcome.MALFORMED_FRAME)
        declared_length = ((frame.data[0] & FIRST_FRAME_LENGTH_HIGH_MASK) << 8) | frame.data[1]
        if declared_length > self.max_message_length:
            return ReassemblyResult(ReassemblyOutcome.OVERSIZED)
        if declared_length < MIN_SEGMENTED_MESSAGE_LENGTH:
            return ReassemblyResult(ReassemblyOutcome.INVALID_LENGTH)
        context.start(declared_length, frame.data[FIRST_FRAME_HEADER_SIZE:])
        return ReassemblyResult(ReassemblyOutcome.IN_PROGRESS)

    def _handle_consecutive_frame(self, context: ReassemblyContext, frame: CANFrame) -> ReassemblyResult:
        """Append to an active message after validating its sequence number."""
        if context.state is ContextState.IDLE:
            return ReassemblyResult(ReassemblyOutcome.ORPHAN_CONSECUTIVE_FRAME)
        if frame.length <= CONSECUTIVE_FRAME_HEADER_SIZE:
            context.reset()
            return ReassemblyResult(ReassemblyOutcome.MALFORMED_FRAME)
        sequence_number = frame.data[0] & SEQUENCE_NUMBER_MASK
        if sequence_number != context.expected_sequence:
            context.reset()
            return ReassemblyResult(ReassemblyOutcome.SEQUENCE_ERROR)
        if not context.append(frame.data[CONSECUTIVE_FRAME_HEADER_SIZE:]):
            return ReassemblyResult(ReassemblyOutcome.IN_PROGRESS)
        return context.take_payload()
