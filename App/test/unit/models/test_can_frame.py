"""Unit tests for the CANFrame model."""

import unittest

from models.can_frame import CANFrame, InvalidFrameError


class CANFrameModelTest(unittest.TestCase):
    """Basic structural validation of the frame model."""

    def test_valid_frame_exposes_length(self) -> None:
        frame = CANFrame(can_id=0x100, data=b"\x01\x02\x03")
        self.assertEqual(frame.length, 3)
        self.assertIsNone(frame.timestamp_ns)

    def test_rejects_identifier_outside_11_bits(self) -> None:
        with self.assertRaises(InvalidFrameError):
            CANFrame(can_id=0x800, data=b"")

    def test_rejects_negative_identifier(self) -> None:
        with self.assertRaises(InvalidFrameError):
            CANFrame(can_id=-1, data=b"")

    def test_rejects_payload_longer_than_8_bytes(self) -> None:
        with self.assertRaises(InvalidFrameError):
            CANFrame(can_id=0x100, data=bytes(9))


if __name__ == "__main__":
    unittest.main()
