"""Fault code decoder (ID ``FAULT_ID``)."""

from __future__ import annotations

from config.constants import (
    FAULT_CODE_OFFSET,
    FAULT_ID,
    FAULT_MODULE_OFFSET,
    FAULT_PAYLOAD_LENGTH,
    FAULT_RESERVED_OFFSET,
    MODULE_COUNT,
)
from models.message import Message
from protocol.common import ProtocolDecodeError, require_payload_length
from protocol.fault.models import FaultCode, FaultResult


def decode_fault(message: Message) -> FaultResult:
    """Decode one complete fault message.

    CHALLENGE.md layout: byte0 module_id, byte1 fault_code (1-4), bytes 2-7
    zero. Raises ``ProtocolDecodeError`` for a wrong ID or length, an unknown
    module or fault code, or non-zero reserved bytes.
    """
    if message.message_id != FAULT_ID:
        raise ProtocolDecodeError(f"message {message.message_id:#x} is not a fault message")
    require_payload_length(message, FAULT_PAYLOAD_LENGTH)
    payload = message.payload
    if any(payload[FAULT_RESERVED_OFFSET:]):
        raise ProtocolDecodeError(f"fault reserved bytes are not zero: {payload.hex()}")
    return FaultResult(
        module_id=_decode_module_id(payload[FAULT_MODULE_OFFSET]),
        code=_decode_fault_code(payload[FAULT_CODE_OFFSET]),
    )


def _decode_module_id(raw_module_id: int) -> int:
    """Validate the payload's module index."""
    if raw_module_id >= MODULE_COUNT:
        raise ProtocolDecodeError(f"fault module id out of range: {raw_module_id}")
    return raw_module_id


def _decode_fault_code(raw_code: int) -> FaultCode:
    """Map the payload's fault code to a documented ``FaultCode``."""
    try:
        return FaultCode(raw_code)
    except ValueError:
        raise ProtocolDecodeError(f"unknown fault code: {raw_code}") from None
