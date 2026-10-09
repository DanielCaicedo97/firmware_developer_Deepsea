"""Unit tests for the identification string decoder.

Texts follow the supplied generator: ``f"{DIAG_STRINGS[ctx]} #{counter}"``
with ``DIAG_STRINGS`` such as ``"SN:PMU-4471-A FW:2.3.1"``.
"""

import contextlib
import io
import unittest

from config.constants import DIAGNOSTIC_BASE_ID, MAX_DIAGNOSTIC_LENGTH, MODULE_COUNT, TELEMETRY_BASE_ID
from helpers import complete_message
from protocol.diagnostic import DiagnosticResult
from models.message import FramingMode, Message
from protocol.common import ProtocolDecodeError
from protocol.diagnostic import decode_diagnostic

GENERATOR_STRINGS = [
    "SN:PMU-4471-A FW:2.3.1",
    "SN:PMU-4472-B FW:2.3.1",
    "SN:PMU-4473-C FW:2.4.0",
    "SN:PMU-4474-D FW:2.4.0",
]


def diagnostic_message(message_id: int, text: bytes) -> Message:
    """Build a reassembled diagnostic message carrying ``text``."""
    return complete_message(message_id, text, framing=FramingMode.SEGMENTED)


class DecodeDiagnosticTest(unittest.TestCase):
    """Valid and invalid identification strings."""

    def test_decodes_generator_message(self) -> None:
        result = decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, b"SN:PMU-4471-A FW:2.3.1 #12"))
        self.assertIsInstance(result, DiagnosticResult)
        self.assertEqual(result.message_id, DIAGNOSTIC_BASE_ID)
        self.assertEqual(result.module_id, 0)
        self.assertEqual(result.text, "SN:PMU-4471-A FW:2.3.1 #12")
        self.assertEqual(result.serial_number, "PMU-4471-A")
        self.assertEqual(result.firmware_version, "2.3.1")
        self.assertEqual(result.counter, 12)

    def test_every_module_keeps_its_identity_and_exact_text(self) -> None:
        for module in range(MODULE_COUNT):
            text = f"{GENERATOR_STRINGS[module]} #{module + 1}"
            result = decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID + module, text.encode("ascii")))
            self.assertEqual((result.message_id, result.module_id), (DIAGNOSTIC_BASE_ID + module, module))
            self.assertEqual(result.text, text)
            self.assertEqual(result.counter, module + 1)

    def test_text_without_counter_as_in_challenge_example(self) -> None:
        result = decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID + 2, b"SN:PMU-4473-C FW:2.4.0"))
        self.assertEqual(result.serial_number, "PMU-4473-C")
        self.assertEqual(result.firmware_version, "2.4.0")
        self.assertIsNone(result.counter)

    def test_accepts_length_bounds(self) -> None:
        shortest = b"SN:A FW:1"  # shortest well-formed text, above the 8-byte minimum
        self.assertEqual(decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, shortest)).serial_number, "A")
        longest = b"SN:" + b"X" * (MAX_DIAGNOSTIC_LENGTH - len(b"SN: FW:1")) + b" FW:1"
        self.assertEqual(len(longest), MAX_DIAGNOSTIC_LENGTH)
        self.assertEqual(decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, longest)).firmware_version, "1")

    def test_rejects_length_out_of_range(self) -> None:
        too_long = b"SN:" + b"X" * MAX_DIAGNOSTIC_LENGTH + b" FW:1"
        for payload in (b"", b"SN:A FW", too_long):
            with self.assertRaises(ProtocolDecodeError):
                decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, payload))

    def test_rejects_invalid_encoding(self) -> None:
        for payload in (b"SN:PMU-\xff FW:2.3.1", "SN:PMU-ñ FW:2.3.1".encode("utf-8")):
            with self.assertRaises(ProtocolDecodeError):
                decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, payload))

    def test_rejects_control_characters(self) -> None:
        for payload in (b"SN:PMU-4471-A FW:2.3.1\x00\x00", b"SN:PMU\n4471 FW:2.3.1", b"SN:PMU-4471-A\tFW:2.3.1"):
            with self.assertRaises(ProtocolDecodeError):
                decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, payload))

    def test_rejects_malformed_text(self) -> None:
        malformed = [
            b"XX:DECOY-NOT-REAL-MSG",  # the generator's restart decoy
            b"FW:2.3.1 SN:PMU-4471-A",  # fields swapped
            b"SN: FW:2.3.1 #1",  # empty serial number
            b"SN:PMU-4471-A FW: #1",  # empty firmware version
            b"SN:PMU-4471-A FW:2.3.1 #",  # empty counter
            b"SN:PMU-4471-A FW:2.3.1 #1-BROKEN",  # the generator's out-of-order text
            b"SN:PMU-4471-A FW:2.3.1 12",  # counter without prefix
            b"SN:PMU-4471-A FW:2.3.1 #1 extra",  # unexpected field
            b"SN:PMU-4471-A  FW:2.3.1",  # empty field
            b"SN:PMU-4471-A,FW:2.3.1",  # single field
        ]
        for payload in malformed:
            with self.assertRaises(ProtocolDecodeError, msg=payload):
                decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, payload))

    def test_rejects_ids_outside_diagnostic_range(self) -> None:
        for message_id in (DIAGNOSTIC_BASE_ID - 1, DIAGNOSTIC_BASE_ID + MODULE_COUNT, TELEMETRY_BASE_ID):
            with self.assertRaises(ProtocolDecodeError):
                decode_diagnostic(diagnostic_message(message_id, b"SN:PMU-4471-A FW:2.3.1 #1"))

    def test_does_not_write_to_stdout(self) -> None:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, b"SN:PMU-4471-A FW:2.3.1 #1"))
            with self.assertRaises(ProtocolDecodeError):
                decode_diagnostic(diagnostic_message(DIAGNOSTIC_BASE_ID, b"XX:DECOY-NOT-REAL-MSG"))
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
