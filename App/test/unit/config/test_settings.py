"""Unit tests for runtime settings validation and the framing map."""

import unittest

from config.constants import DIAGNOSTIC_BASE_ID, FAULT_ID, MAX_DIAGNOSTIC_LENGTH, MODULE_COUNT
from config.settings import CommunicationConfig, TransportConfig, build_application_config, build_framing_map
from models.message import FramingMode


class CommunicationConfigTest(unittest.TestCase):
    """Validation of communication settings."""

    def test_rejects_invalid_values(self) -> None:
        for kwargs in ({"interface": ""}, {"interface": "vcan0", "receive_timeout_s": 0},
                       {"interface": "vcan0", "socket_receive_buffer_bytes": 0}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                CommunicationConfig(**kwargs)


class TransportConfigTest(unittest.TestCase):
    """Validation of transport settings."""

    def test_rejects_out_of_range_max_length(self) -> None:
        for bad in (7, 0x1000):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                TransportConfig(framing={}, max_message_length=bad)

    def test_framing_map_cannot_be_mutated(self) -> None:
        framing = {0x6F0: FramingMode.SEGMENTED}
        config = TransportConfig(framing=framing)
        framing[0x6F1] = FramingMode.SEGMENTED
        self.assertNotIn(0x6F1, config.framing)
        with self.assertRaises(TypeError):
            config.framing[0x6F2] = FramingMode.SEGMENTED  # type: ignore[index]


class FramingMapTest(unittest.TestCase):
    """The challenge framing map and application config builder."""

    def test_default_framing_map(self) -> None:
        framing = build_framing_map()
        self.assertEqual(len(framing), 2 * MODULE_COUNT + 1)
        self.assertIs(framing[FAULT_ID], FramingMode.SINGLE_FRAME)
        self.assertIs(framing[DIAGNOSTIC_BASE_ID + 3], FramingMode.SEGMENTED)

    def test_rejects_non_positive_module_count(self) -> None:
        with self.assertRaises(ValueError):
            build_framing_map(0)

    def test_application_config_from_cli_values(self) -> None:
        config = build_application_config(interface="vcan0", debug=True)
        self.assertEqual(config.communication.interface, "vcan0")
        self.assertTrue(config.logging.debug)
        self.assertEqual(config.transport.max_message_length, MAX_DIAGNOSTIC_LENGTH)


if __name__ == "__main__":
    unittest.main()
