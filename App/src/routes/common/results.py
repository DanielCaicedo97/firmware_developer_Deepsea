"""Dispatch outcomes shared by every router."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from models.message import Message


class DispatchStatus(Enum):
    """What happened to one dispatched message.

    ``ROUTE_NOT_FOUND`` means the root router has no subrouter for the ID;
    ``HANDLER_NOT_FOUND`` means a subrouter was reached but has no handler for
    it. ``HANDLER_FAILED`` means the handler raised one of its subrouter's
    expected errors (for the challenge routes, ``ProtocolDecodeError``).
    """

    SUCCESS = "success"
    ROUTE_NOT_FOUND = "route_not_found"
    HANDLER_NOT_FOUND = "handler_not_found"
    HANDLER_FAILED = "handler_failed"


@dataclass(frozen=True)
class DispatchResult:
    """The outcome of dispatching one complete message.

    ``router_name`` is the subrouter that handled the message, or ``None``
    when no subrouter matched. ``result`` is the handler's return value (a
    ``ControllerResult`` for the challenge routes) and is set only on
    ``SUCCESS``; ``error`` is the expected exception on ``HANDLER_FAILED``.
    """

    status: DispatchStatus
    message: Message
    router_name: Optional[str] = None
    result: Any = None
    error: Optional[Exception] = None

    @property
    def succeeded(self) -> bool:
        """True when a handler ran and returned a result."""
        return self.status is DispatchStatus.SUCCESS
