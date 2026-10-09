"""Power module telemetry decoder (IDs ``TELEMETRY_BASE_ID`` + module)."""

from __future__ import annotations

import struct

from config.constants import (
    CURRENT_SCALE_A,
    STATUS_DERATED_MASK,
    STATUS_ENABLED_MASK,
    STATUS_FAULT_MASK,
    TELEMETRY_BASE_ID,
    TELEMETRY_PAYLOAD_FORMAT,
    TELEMETRY_PAYLOAD_LENGTH,
    TEMPERATURE_OFFSET_C,
    VOLTAGE_SCALE_V,
)
from models.message import Message
from protocol.common import module_id_from_message_id, require_payload_length
from protocol.telemetry.models import TelemetryResult


def decode_telemetry(message: Message) -> TelemetryResult:
    """Decode one complete telemetry message.

    The module comes from the message ID and every other field from the
    8-byte payload, as laid out in CHALLENGE.md. Status bits other than
    enabled, fault and derated are undocumented and ignored. Raises
    ``ProtocolDecodeError`` for a wrong ID or payload length.
    """
    module_id = module_id_from_message_id(message.message_id, TELEMETRY_BASE_ID)
    require_payload_length(message, TELEMETRY_PAYLOAD_LENGTH)
    voltage_raw, current_raw, temperature_raw, status, sequence = struct.unpack(
        TELEMETRY_PAYLOAD_FORMAT, message.payload
    )
    return TelemetryResult(
        module_id=module_id,
        sequence=sequence,
        voltage_v=voltage_raw * VOLTAGE_SCALE_V,
        current_a=current_raw * CURRENT_SCALE_A,
        temperature_c=temperature_raw - TEMPERATURE_OFFSET_C,
        enabled=bool(status & STATUS_ENABLED_MASK),
        fault=bool(status & STATUS_FAULT_MASK),
        derated=bool(status & STATUS_DERATED_MASK),
    )
