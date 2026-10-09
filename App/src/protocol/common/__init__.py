"""Error type and validation helpers shared by every protocol domain."""

from __future__ import annotations

from config.constants import MODULE_COUNT
from models.message import Message


class ProtocolDecodeError(ValueError):
    """Raised when a complete message cannot be decoded by its protocol.

    It signals invalid input from the bus, so callers catch it and drop the
    message; it must not stop the receive loop.
    """


def require_payload_length(message: Message, expected_length: int) -> None:
    """Reject ``message`` unless its payload is exactly ``expected_length`` bytes."""
    if len(message.payload) != expected_length:
        raise ProtocolDecodeError(
            f"message {message.message_id:#x}: payload is {len(message.payload)} bytes, expected {expected_length}"
        )


def module_id_from_message_id(message_id: int, base_id: int) -> int:
    """Return the module index for a per-module ID ``base_id + module``.

    Raises ``ProtocolDecodeError`` if ``message_id`` is outside the
    ``MODULE_COUNT`` IDs starting at ``base_id``.
    """
    module_id = message_id - base_id
    if not 0 <= module_id < MODULE_COUNT:
        raise ProtocolDecodeError(f"message {message_id:#x} is not in the range starting at {base_id:#x}")
    return module_id
