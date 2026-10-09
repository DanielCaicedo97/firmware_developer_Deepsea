"""Unit tests for raw SocketCAN frame decoding."""

import unittest

from communication.frame import CAN_FRAME_SIZE, decode_can_frame
from config.constants import CAN_ERROR_FRAME_FLAG, CAN_EXTENDED_FRAME_FLAG, CAN_REMOTE_FRAME_FLAG
from helpers import raw_can_frame
from models.can_frame import InvalidFrameError


class DecodeCanFrameTest(unittest.TestCase):
    """Raw struct can_frame to CANFrame conversion."""

    def test_frame_size_matches_struct_can_frame(self) -> None:
        self.assertEqual(CAN_FRAME_SIZE, 16)

    def test_decodes_valid_frame_and_trims_to_dlc(self) -> None:
        frame = decode_can_frame(raw_can_frame(0x6F2, b"\x10\x16ABCxyz", dlc=5), timestamp_ns=42)
        self.assertEqual(frame.can_id, 0x6F2)
        self.assertEqual(frame.data, b"\x10\x16ABC")
        self.assertEqual(frame.length, 5)
        self.assertEqual(frame.timestamp_ns, 42)

    def test_decodes_zero_length_frame(self) -> None:
        self.assertEqual(decode_can_frame(raw_can_frame(0x123, b"")).data, b"")

    def test_rejects_wrong_size(self) -> None:
        with self.assertRaises(InvalidFrameError):
            decode_can_frame(bytes(CAN_FRAME_SIZE - 1))

    def test_rejects_dlc_above_8(self) -> None:
        with self.assertRaises(InvalidFrameError):
            decode_can_frame(raw_can_frame(0x100, bytes(8), dlc=9))

    def test_rejects_extended_remote_and_error_frames(self) -> None:
        for flag in (CAN_EXTENDED_FRAME_FLAG, CAN_REMOTE_FRAME_FLAG, CAN_ERROR_FRAME_FLAG):
            with self.subTest(flag=hex(flag)), self.assertRaises(InvalidFrameError):
                decode_can_frame(raw_can_frame(0x100 | flag, bytes(8)))


if __name__ == "__main__":
    unittest.main()
