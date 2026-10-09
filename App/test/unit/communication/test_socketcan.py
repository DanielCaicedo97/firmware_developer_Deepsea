"""Unit tests for SocketCanInterface using a fake socket (no bus, no transmission)."""

import socket
import unittest

from communication.interface import CommunicationError
from communication.socketcan import SocketCanInterface
from config.constants import CAN_EXTENDED_FRAME_FLAG
from config.settings import CommunicationConfig
from helpers import FakeCanSocket, raw_can_frame


class SocketCanInterfaceTest(unittest.TestCase):
    """Open/receive/close behaviour of the SocketCAN implementation."""

    def make(self, fake: FakeCanSocket, **config_overrides) -> SocketCanInterface:
        config = CommunicationConfig(interface="vcan0", **config_overrides)
        return SocketCanInterface(config, socket_factory=lambda: fake)

    def test_open_binds_configured_interface_and_sets_timeout(self) -> None:
        fake = FakeCanSocket()
        interface = self.make(fake, receive_timeout_s=0.25)
        interface.open()
        self.assertEqual(fake.bound_to, ("vcan0",))
        self.assertEqual(fake.timeout, 0.25)
        self.assertEqual(fake.options, [])
        self.assertTrue(interface.is_open)

    def test_optional_receive_buffer_size(self) -> None:
        fake = FakeCanSocket()
        self.make(fake, socket_receive_buffer_bytes=65536).open()
        self.assertEqual(fake.options, [(socket.SOL_SOCKET, socket.SO_RCVBUF, 65536)])

    def test_receives_and_decodes_frame_with_timestamp(self) -> None:
        fake = FakeCanSocket([raw_can_frame(0x101, b"\x01\x02\x03\x04\x05\x06\x07\x08")])
        with self.make(fake) as interface:
            frame = interface.receive()
        self.assertIsNotNone(frame)
        self.assertEqual(frame.can_id, 0x101)
        self.assertEqual(frame.data, b"\x01\x02\x03\x04\x05\x06\x07\x08")
        self.assertIsInstance(frame.timestamp_ns, int)
        self.assertTrue(fake.closed)

    def test_timeout_returns_none(self) -> None:
        with self.make(FakeCanSocket()) as interface:
            self.assertIsNone(interface.receive())

    def test_invalid_frame_is_dropped_and_counted(self) -> None:
        fake = FakeCanSocket([raw_can_frame(0x100 | CAN_EXTENDED_FRAME_FLAG, bytes(8)), b"\x00\x01"])
        with self.make(fake) as interface:
            self.assertIsNone(interface.receive())
            self.assertIsNone(interface.receive())
            self.assertEqual(interface.invalid_frames, 2)

    def test_receive_error_raises_communication_error(self) -> None:
        fake = FakeCanSocket([OSError("network is down")])
        with self.make(fake) as interface, self.assertRaises(CommunicationError):
            interface.receive()

    def test_receive_on_closed_interface_raises(self) -> None:
        with self.assertRaises(CommunicationError):
            self.make(FakeCanSocket()).receive()

    def test_bind_failure_closes_socket_and_raises(self) -> None:
        fake = FakeCanSocket(bind_error=OSError("No such device"))
        interface = self.make(fake)
        with self.assertRaises(CommunicationError):
            interface.open()
        self.assertTrue(fake.closed)
        self.assertFalse(interface.is_open)

    def test_close_is_idempotent(self) -> None:
        interface = self.make(FakeCanSocket())
        interface.open()
        interface.close()
        interface.close()
        self.assertFalse(interface.is_open)


if __name__ == "__main__":
    unittest.main()
