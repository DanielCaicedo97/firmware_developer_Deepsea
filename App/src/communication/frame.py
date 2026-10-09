"""Conversion from the raw SocketCAN ``struct can_frame`` to ``CANFrame``."""

from __future__ import annotations

import struct
from typing import Optional

from config.constants import (
    CAN_FLAGS_MASK,
    CAN_FRAME_FORMAT,
    CAN_MAX_DATA_LENGTH,
    CAN_STANDARD_ID_MASK,
)
from models.can_frame import CANFrame, InvalidFrameError

CAN_FRAME_SIZE = struct.calcsize(CAN_FRAME_FORMAT)


def decode_can_frame(raw: bytes, timestamp_ns: Optional[int] = None) -> CANFrame:
    """Decode one raw classic CAN frame read from a ``CAN_RAW`` socket.

    Only standard 11-bit data frames are accepted. Extended, remote and error
    frames, wrong-sized reads and DLC values above 8 raise ``InvalidFrameError``.
    """
    if len(raw) != CAN_FRAME_SIZE:
        raise InvalidFrameError(f"expected {CAN_FRAME_SIZE} bytes, got {len(raw)}")
    raw_id, dlc, data = struct.unpack(CAN_FRAME_FORMAT, raw)
    if raw_id & CAN_FLAGS_MASK:
        raise InvalidFrameError(f"unsupported CAN frame flags in ID {raw_id:#010x}")
    if dlc > CAN_MAX_DATA_LENGTH:
        raise InvalidFrameError(f"invalid DLC {dlc}")
    return CANFrame(can_id=raw_id & CAN_STANDARD_ID_MASK, data=data[:dlc], timestamp_ns=timestamp_ns)
