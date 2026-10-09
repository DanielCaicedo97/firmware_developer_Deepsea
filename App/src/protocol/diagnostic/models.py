"""Decoded module identification string."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DiagnosticResult:
    """One decoded identification string.

    ``message_id`` is the diagnostic ID the message arrived on and
    ``module_id`` the module it belongs to. ``text`` is the full string exactly
    as received; ``serial_number``, ``firmware_version`` and ``counter`` are
    its parsed fields (``counter`` is ``None`` when the text carries none).
    """

    message_id: int
    module_id: int
    text: str
    serial_number: str
    firmware_version: str
    counter: Optional[int] = None
