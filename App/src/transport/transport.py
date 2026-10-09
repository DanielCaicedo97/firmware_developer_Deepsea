"""Transport interface: turns received units into complete messages."""

from __future__ import annotations

from abc import ABC, abstractmethod
from enum import Enum
from typing import Generic, List, Optional, TypeVar

from communication.interface import CommunicationInterface
from models.message import Message
from transport.listener import TransportListener

UnitT = TypeVar("UnitT")


class FrameOutcome(Enum):
    """What the transport did with one received unit.

    ``IGNORED`` means the unit does not belong to any supported source (for
    example bus noise). Every other outcome means the unit was on a supported
    source, which is what upper layers need for frame accounting.
    """

    IGNORED = "ignored"
    ACCEPTED = "accepted"
    COMPLETED = "completed"
    REJECTED = "rejected"


class Transport(ABC, Generic[UnitT]):
    """Base transport: owns listener registration and message delivery."""

    def __init__(self) -> None:
        self._listeners: List[TransportListener] = []

    def add_listener(self, listener: TransportListener) -> None:
        """Register a listener for complete messages. Duplicates are ignored."""
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: TransportListener) -> None:
        """Unregister a listener if registered."""
        if listener in self._listeners:
            self._listeners.remove(listener)

    @abstractmethod
    def process(self, unit: UnitT) -> FrameOutcome:
        """Process one received unit and deliver any message it completes."""

    def receive_from(self, communication: CommunicationInterface[UnitT]) -> Optional[FrameOutcome]:
        """Consume one unit from ``communication`` and process it.

        Returns ``None`` when nothing valid arrived before the communication
        timeout, otherwise the unit's ``FrameOutcome`` (which upper layers use
        for frame accounting). ``CommunicationError`` propagates.
        """
        unit = communication.receive()
        if unit is None:
            return None
        return self.process(unit)

    def _deliver(self, message: Message) -> None:
        """Notify every registered listener of a complete message."""
        for listener in self._listeners:
            listener.on_message(message)
