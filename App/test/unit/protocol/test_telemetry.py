"""Unit tests for the telemetry decoder.

Payloads are packed exactly as the supplied generator does:
``struct.pack("<HHBBH", v_raw, c_raw, t_raw, status, seq)``.
"""

import contextlib
import io
import struct
import unittest

from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MODULE_COUNT, TELEMETRY_BASE_ID
from helpers import complete_message
from protocol.telemetry import TelemetryResult
from protocol.common import ProtocolDecodeError
from protocol.telemetry import decode_telemetry


def telemetry_payload(v_raw: int, c_raw: int, t_raw: int, status: int, seq: int) -> bytes:
    """Pack a telemetry payload the way the generator does."""
    return struct.pack("<HHBBH", v_raw, c_raw, t_raw, status, seq)


class DecodeTelemetryTest(unittest.TestCase):
    """Valid and invalid telemetry messages."""

    def test_decodes_every_documented_field(self) -> None:
        # Generator module 2 baseline: 404.0 V, 102.0 A, 37 C, enabled + fault active.
        message = complete_message(TELEMETRY_BASE_ID + 2, telemetry_payload(4040, 10200, 77, 0x03, 4821))
        result = decode_telemetry(message)
        self.assertIsInstance(result, TelemetryResult)
        self.assertEqual(result.module_id, 2)
        self.assertEqual(result.sequence, 4821)
        self.assertAlmostEqual(result.voltage_v, 404.0)
        self.assertAlmostEqual(result.current_a, 102.0)
        self.assertEqual(result.temperature_c, 37)
        self.assertTrue(result.enabled)
        self.assertTrue(result.fault)
        self.assertFalse(result.derated)

    def test_scaling_matches_generator_ground_truth(self) -> None:
        # The generator logs round(v_raw * 0.1, 2) and round(c_raw * 0.01, 2).
        result = decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(4123, 11855, 87, 0x01, 1)))
        self.assertEqual(round(result.voltage_v, 2), round(4123 * 0.1, 2))
        self.assertEqual(round(result.current_a, 2), 118.55)
        self.assertEqual(result.temperature_c, 47)

    def test_module_identity_comes_from_message_id(self) -> None:
        payload = telemetry_payload(4000, 10000, 75, 0x01, 7)
        for module in range(MODULE_COUNT):
            result = decode_telemetry(complete_message(TELEMETRY_BASE_ID + module, payload))
            self.assertEqual(result.module_id, module)
            self.assertEqual(result.sequence, 7)

    def test_sequence_uses_full_uint16_range(self) -> None:
        for sequence in (0, 1, 0x0100, 0xFFFF):
            result = decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(0, 0, 0, 0, sequence)))
            self.assertEqual(result.sequence, sequence)

    def test_status_bits(self) -> None:
        cases = {
            0x00: (False, False, False),
            0x01: (True, False, False),
            0x02: (False, True, False),
            0x04: (False, False, True),
            0x07: (True, True, True),
        }
        for status, expected in cases.items():
            result = decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(0, 0, 40, status, 0)))
            self.assertEqual((result.enabled, result.fault, result.derated), expected, f"status {status:#x}")

    def test_undocumented_status_bits_are_ignored(self) -> None:
        result = decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(0, 0, 40, 0xF9, 0)))
        self.assertEqual((result.enabled, result.fault, result.derated), (True, False, False))

    def test_temperature_offset_extremes(self) -> None:
        low = decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(0, 0, 0, 0, 0)))
        high = decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(0, 0, 255, 0, 0)))
        self.assertEqual(low.temperature_c, -40)
        self.assertEqual(high.temperature_c, 215)

    def test_rejects_wrong_payload_length(self) -> None:
        payload = telemetry_payload(4000, 10000, 75, 0x01, 7)
        for bad in (b"", payload[:7], payload + b"\x00"):
            with self.assertRaises(ProtocolDecodeError):
                decode_telemetry(complete_message(TELEMETRY_BASE_ID, bad))

    def test_rejects_ids_outside_telemetry_range(self) -> None:
        payload = telemetry_payload(4000, 10000, 75, 0x01, 7)
        for message_id in (TELEMETRY_BASE_ID - 1, TELEMETRY_BASE_ID + MODULE_COUNT, FAULT_ID, DIAGNOSTIC_BASE_ID):
            with self.assertRaises(ProtocolDecodeError):
                decode_telemetry(complete_message(message_id, payload))

    def test_does_not_write_to_stdout(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            decode_telemetry(complete_message(TELEMETRY_BASE_ID, telemetry_payload(4000, 10000, 75, 0x01, 7)))
            with self.assertRaises(ProtocolDecodeError):
                decode_telemetry(complete_message(TELEMETRY_BASE_ID, b"\x00"))
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
