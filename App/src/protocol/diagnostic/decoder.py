"""Identification string decoder (IDs ``DIAGNOSTIC_BASE_ID`` + module).

The payload is an already reassembled message; segmentation is the transport
layer's job.
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from config.constants import (
    COUNTER_PREFIX,
    DIAGNOSTIC_BASE_ID,
    DIAGNOSTIC_FIELD_SEPARATOR,
    DIAGNOSTIC_TEXT_ENCODING,
    FIRMWARE_VERSION_PREFIX,
    MAX_DIAGNOSTIC_LENGTH,
    MIN_SEGMENTED_MESSAGE_LENGTH,
    SERIAL_NUMBER_PREFIX,
)
from models.message import Message
from protocol.common import ProtocolDecodeError, module_id_from_message_id
from protocol.diagnostic.models import DiagnosticResult


def decode_diagnostic(message: Message) -> DiagnosticResult:
    """Decode one complete identification string.

    Accepted text is ``SN:<serial> FW:<firmware>``, optionally followed by
    `` #<counter>`` as the supplied generator sends it. Raises
    ``ProtocolDecodeError`` for a wrong ID, a length outside CHALLENGE.md's
    8-64 bytes, non-ASCII or non-printable text, or text in another format.
    """
    module_id = module_id_from_message_id(message.message_id, DIAGNOSTIC_BASE_ID)
    text = _decode_text(message.payload)
    serial_number, firmware_version, counter = _parse_fields(text)
    return DiagnosticResult(
        message_id=message.message_id,
        module_id=module_id,
        text=text,
        serial_number=serial_number,
        firmware_version=firmware_version,
        counter=counter,
    )


def _decode_text(payload: bytes) -> str:
    """Validate the payload length and decode it as printable ASCII."""
    if not MIN_SEGMENTED_MESSAGE_LENGTH <= len(payload) <= MAX_DIAGNOSTIC_LENGTH:
        raise ProtocolDecodeError(f"identification string length out of range: {len(payload)}")
    try:
        text = payload.decode(DIAGNOSTIC_TEXT_ENCODING)
    except UnicodeDecodeError:
        raise ProtocolDecodeError(f"identification string is not ASCII: {payload.hex()}") from None
    if not text.isprintable():
        raise ProtocolDecodeError(f"identification string has control characters: {text!r}")
    return text


def _parse_fields(text: str) -> Tuple[str, str, Optional[int]]:
    """Split ``text`` into (serial number, firmware version, counter or None)."""
    fields = text.split(DIAGNOSTIC_FIELD_SEPARATOR)
    if len(fields) not in (2, 3):
        raise ProtocolDecodeError(f"unsupported identification string format: {text!r}")
    serial_number = _field_value(fields[0], SERIAL_NUMBER_PREFIX, text)
    firmware_version = _field_value(fields[1], FIRMWARE_VERSION_PREFIX, text)
    counter = _parse_counter(fields[2:], text)
    return serial_number, firmware_version, counter


def _field_value(field: str, prefix: str, text: str) -> str:
    """Return the non-empty value after ``prefix`` in ``field``."""
    value = field[len(prefix):]
    if not field.startswith(prefix) or not value:
        raise ProtocolDecodeError(f"missing {prefix!r} field in identification string: {text!r}")
    return value


def _parse_counter(fields: List[str], text: str) -> Optional[int]:
    """Parse the optional ``#<counter>`` field; ``None`` when absent."""
    if not fields:
        return None
    digits = fields[0][len(COUNTER_PREFIX):]
    if not fields[0].startswith(COUNTER_PREFIX) or not digits.isdigit():
        raise ProtocolDecodeError(f"invalid counter in identification string: {text!r}")
    return int(digits)
