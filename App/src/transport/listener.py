"""Listener interface through which a transport delivers complete messages."""

from __future__ import annotations

from abc import ABC, abstractmethod

from models.message import Message


class TransportListener(ABC):
    """Receives complete messages from a transport.

    Called only after a message has been fully and successfully reconstructed;
    never with raw frames or abandoned attempts.
    """

    @abstractmethod
    def on_message(self, message: Message) -> None:
        """Handle one complete message."""
