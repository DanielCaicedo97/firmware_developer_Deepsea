"""CAN transport: single-frame passthrough plus segmented reassembly."""

from __future__ import annotations

import logging
import time
from typing import Callable

from config.settings import TransportConfig
from models.can_frame import CANFrame
from models.message import FramingMode, Message, TransportMetadata
from transport.reassembler import ReassemblyOutcome, ReassemblyResult, SegmentedReassembler
from transport.transport import FrameOutcome, Transport

logger = logging.getLogger(__name__)

Clock = Callable[[], int]


class CanTransport(Transport[CANFrame]):
    """Turns validated CAN frames into complete messages.

    The framing map (from configuration) says how each CAN ID is framed, not
    what it carries. Frames on IDs outside the map, such as noise, are ignored.
    ``clock`` stamps each message's ``completed_at_ns`` when it completes.
    """

    def __init__(self, config: TransportConfig, clock: Clock = time.monotonic_ns) -> None:
        super().__init__()
        self._clock = clock
        self._framing = config.framing
        segmented_ids = [can_id for can_id, mode in config.framing.items() if mode is FramingMode.SEGMENTED]
        self._reassembler = SegmentedReassembler(segmented_ids, config.max_message_length)

    @property
    def reassembler(self) -> SegmentedReassembler:
        """The segmented reassembler (exposed for inspection and tests)."""
        return self._reassembler

    def process(self, unit: CANFrame) -> FrameOutcome:
        """Classify one frame, reassemble if needed, and deliver complete messages."""
        framing = self._framing.get(unit.can_id)
        if framing is None:
            return FrameOutcome.IGNORED
        if framing is FramingMode.SINGLE_FRAME:
            self._deliver(self._build_message(unit, FramingMode.SINGLE_FRAME, unit.data, 1))
            return FrameOutcome.COMPLETED
        return self._process_segmented(unit)

    def _process_segmented(self, frame: CANFrame) -> FrameOutcome:
        """Feed a segmented-source frame to the reassembler and map the outcome."""
        result = self._reassembler.process(frame)
        if result.outcome is ReassemblyOutcome.COMPLETED:
            self._deliver_reassembled(frame, result)
            return FrameOutcome.COMPLETED
        if result.outcome is ReassemblyOutcome.IN_PROGRESS:
            return FrameOutcome.ACCEPTED
        logger.debug("source %#x: frame rejected (%s)", frame.can_id, result.outcome.value)
        return FrameOutcome.REJECTED

    def _deliver_reassembled(self, frame: CANFrame, result: ReassemblyResult) -> None:
        """Wrap a completed reassembly in a message and notify listeners."""
        payload = result.payload if result.payload is not None else b""
        self._deliver(self._build_message(frame, FramingMode.SEGMENTED, payload, result.frame_count))

    def _build_message(self, frame: CANFrame, framing: FramingMode, payload: bytes, frame_count: int) -> Message:
        """Build the protocol-independent message for a CAN source, stamped as complete now."""
        metadata = TransportMetadata(
            framing=framing,
            frame_count=frame_count,
            received_at_ns=frame.timestamp_ns,
            completed_at_ns=self._clock(),
        )
        return Message(message_id=frame.can_id, payload=payload, metadata=metadata, source_id=frame.can_id)
