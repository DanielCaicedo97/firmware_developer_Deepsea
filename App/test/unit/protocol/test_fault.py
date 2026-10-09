"""Unit tests for the fault decoder.

Payloads are built exactly as the supplied generator does:
``bytes([module, code, 0, 0, 0, 0, 0, 0])``.
"""

import contextlib
import io
import unittest

from config.constants import FAULT_ID, MODULE_COUNT, TELEMETRY_BASE_ID
from helpers import complete_message
from protocol.fault import FaultCode, FaultResult
from protocol.common import ProtocolDecodeError
from protocol.fault import decode_fault


def fault_payload(module: int, code: int) -> bytes:
    """Build a fault payload the way the generator does."""
    return bytes([module, code, 0, 0, 0, 0, 0, 0])


class DecodeFaultTest(unittest.TestCase):
    """Valid and invalid fault messages."""

    def test_decodes_module_and_code(self) -> None:
        result = decode_fault(complete_message(FAULT_ID, fault_payload(2, 1)))
        self.assertIsInstance(result, FaultResult)
        self.assertEqual(result.module_id, 2)
        self.assertIs(result.code, FaultCode.OVERTEMP)
        self.assertEqual(result.code, 1)

    def test_every_module_and_documented_code(self) -> None:
        expected_codes = {
            1: FaultCode.OVERTEMP,
            2: FaultCode.OVERVOLTAGE,
            3: FaultCode.UNDERVOLTAGE,
            4: FaultCode.ISOLATION_FAULT,
        }
        for module in range(MODULE_COUNT):
            for raw_code, code in expected_codes.items():
                result = decode_fault(complete_message(FAULT_ID, fault_payload(module, raw_code)))
                self.assertEqual((result.module_id, result.code), (module, code))

    def test_rejects_unknown_fault_codes(self) -> None:
        for raw_code in (0, 5, 0xFF):
            with self.assertRaises(ProtocolDecodeError):
                decode_fault(complete_message(FAULT_ID, fault_payload(0, raw_code)))

    def test_rejects_unknown_module(self) -> None:
        for module in (MODULE_COUNT, 0xFF):
            with self.assertRaises(ProtocolDecodeError):
                decode_fault(complete_message(FAULT_ID, fault_payload(module, 1)))

    def test_rejects_non_zero_reserved_bytes(self) -> None:
        for index in range(2, 8):
            payload = bytearray(fault_payload(0, 1))
            payload[index] = 0x01
            with self.assertRaises(ProtocolDecodeError):
                decode_fault(complete_message(FAULT_ID, bytes(payload)))

    def test_rejects_wrong_payload_length(self) -> None:
        payload = fault_payload(0, 1)
        for bad in (b"", payload[:2], payload[:7], payload + b"\x00"):
            with self.assertRaises(ProtocolDecodeError):
                decode_fault(complete_message(FAULT_ID, bad))

    def test_rejects_other_message_ids(self) -> None:
        for message_id in (FAULT_ID - 1, FAULT_ID + 1, TELEMETRY_BASE_ID):
            with self.assertRaises(ProtocolDecodeError):
                decode_fault(complete_message(message_id, fault_payload(0, 1)))

    def test_does_not_write_to_stdout(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            decode_fault(complete_message(FAULT_ID, fault_payload(1, 2)))
            with self.assertRaises(ProtocolDecodeError):
                decode_fault(complete_message(FAULT_ID, fault_payload(1, 9)))
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
