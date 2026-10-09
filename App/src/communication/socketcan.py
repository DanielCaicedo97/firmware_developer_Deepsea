"""SocketCAN implementation of the communication interface (receive only)."""

from __future__ import annotations

import logging
import socket
import time
from typing import Callable, Optional

from communication.frame import CAN_FRAME_SIZE, decode_can_frame
from communication.interface import CommunicationError, CommunicationInterface
from config.settings import CommunicationConfig
from models.can_frame import CANFrame, InvalidFrameError

logger = logging.getLogger(__name__)

SocketFactory = Callable[[], socket.socket]


def create_raw_can_socket() -> socket.socket:
    """Create a raw SocketCAN socket. Raises ``CommunicationError`` if unsupported."""
    if not hasattr(socket, "AF_CAN"):
        raise CommunicationError("SocketCAN is not available on this platform")
    try:
        return socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    except OSError as exc:
        raise CommunicationError(f"cannot create CAN socket: {exc}") from exc


class SocketCanInterface(CommunicationInterface[CANFrame]):
    """Receives classic CAN frames from a SocketCAN interface such as ``vcan0``.

    The socket is only ever read. Frames are timestamped with
    ``time.monotonic_ns()`` as soon as they are read and validated before being
    returned. Invalid frames are dropped, counted and logged, never raised.
    """

    def __init__(self, config: CommunicationConfig, socket_factory: SocketFactory = create_raw_can_socket) -> None:
        self._config = config
        self._socket_factory = socket_factory
        self._socket: Optional[socket.socket] = None
        self.invalid_frames = 0

    @property
    def is_open(self) -> bool:
        """Whether the socket is currently open."""
        return self._socket is not None

    def open(self) -> None:
        """Create the raw CAN socket and bind it to the configured interface."""
        if self._socket is not None:
            return
        sock = self._socket_factory()
        try:
            self._configure_socket(sock)
            sock.bind((self._config.interface,))
        except OSError as exc:
            sock.close()
            raise CommunicationError(f"cannot bind to CAN interface {self._config.interface!r}: {exc}") from exc
        self._socket = sock
        logger.debug("SocketCAN opened on %s", self._config.interface)

    def receive(self) -> Optional[CANFrame]:
        """Return the next valid frame, or ``None`` on timeout or invalid frame."""
        if self._socket is None:
            raise CommunicationError("receive called on a closed CAN interface")
        try:
            raw = self._socket.recv(CAN_FRAME_SIZE)
        except socket.timeout:
            return None
        except OSError as exc:
            raise CommunicationError(f"CAN receive failed on {self._config.interface!r}: {exc}") from exc
        timestamp_ns = time.monotonic_ns()
        try:
            return decode_can_frame(raw, timestamp_ns)
        except InvalidFrameError as exc:
            self.invalid_frames += 1
            logger.debug("dropped invalid CAN frame: %s", exc)
            return None

    def close(self) -> None:
        """Close the socket if open."""
        if self._socket is None:
            return
        self._socket.close()
        self._socket = None
        logger.debug("SocketCAN closed on %s", self._config.interface)

    def _configure_socket(self, sock: socket.socket) -> None:
        """Apply timeout and optional receive buffer size before binding."""
        sock.settimeout(self._config.receive_timeout_s)
        if self._config.socket_receive_buffer_bytes is not None:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, self._config.socket_receive_buffer_bytes)
