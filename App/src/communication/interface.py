"""Generic, receive-only communication abstraction.

A communication implementation (SocketCAN today; UART or SPI later) only moves
raw units off the medium.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from types import TracebackType
from typing import Generic, Optional, Type, TypeVar

UnitT = TypeVar("UnitT")


class CommunicationError(Exception):
    """A real communication failure (channel cannot be opened or read).

    Distinct from malformed traffic, which is a normal runtime condition and
    never raises this error.
    """


class CommunicationInterface(ABC, Generic[UnitT]):
    """Receive-only channel producing raw units of type ``UnitT``."""

    @abstractmethod
    def open(self) -> None:
        """Acquire the underlying resource. Raises ``CommunicationError``."""

    @abstractmethod
    def receive(self) -> Optional[UnitT]:
        """Return the next valid unit, or ``None`` if none is available in time.

        Raises ``CommunicationError`` on a communication failure.
        """

    @abstractmethod
    def close(self) -> None:
        """Release the underlying resource. Safe to call more than once."""

    def __enter__(self) -> "CommunicationInterface[UnitT]":
        self.open()
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        self.close()
