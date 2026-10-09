"""Processing outcome shared by the per-domain controllers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from models.application_event import ApplicationEvent


class ControllerStatus(Enum):
    """What a controller did with one decoded result.

    ``PROCESSED``: the result was valid, state was updated and ``event`` was
    published. ``REJECTED``: the result failed validation, so state was left
    untouched and nothing was published; ``reason`` says why.
    """

    PROCESSED = "processed"
    REJECTED = "rejected"


@dataclass(frozen=True)
class ControllerResult:
    """The outcome of one ``BaseController.handle`` call.

    ``decoded`` is the decoder result the controller received, unchanged.
    """

    status: ControllerStatus
    decoded: Any
    event: Optional[ApplicationEvent] = None
    reason: Optional[str] = None

    @property
    def succeeded(self) -> bool:
        """True when the result was applied and its event published."""
        return self.status is ControllerStatus.PROCESSED
