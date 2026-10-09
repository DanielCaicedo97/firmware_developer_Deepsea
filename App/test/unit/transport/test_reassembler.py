"""Tests for per-source segmented reassembly and its bounded state."""

import tracemalloc
import unittest

from config.constants import DIAGNOSTIC_BASE_ID, MAX_DIAGNOSTIC_LENGTH, MODULE_COUNT
from models.can_frame import CANFrame
from transport.reassembler import ContextState, ReassemblyOutcome, SegmentedReassembler
from helpers import consecutive_frame, first_frame, interleave, segment_message

SOURCE_IDS = [DIAGNOSTIC_BASE_ID + module for module in range(MODULE_COUNT)]
ID_0, ID_1, ID_2, ID_3 = SOURCE_IDS
MESSAGE = b"SN:PMU-4471-A FW:2.3.1 #1"


class ReassemblerTestCase(unittest.TestCase):
    """Shared fixture: a reassembler for the four diagnostic IDs."""

    def setUp(self) -> None:
        self.reassembler = SegmentedReassembler(SOURCE_IDS, MAX_DIAGNOSTIC_LENGTH)

    def feed(self, frames):
        """Feed frames in order and return the list of outcomes."""
        return [self.reassembler.process(frame) for frame in frames]

    def completed_payloads(self, frames):
        """Feed frames and return the payloads of every completed message."""
        return [r.payload for r in self.feed(frames) if r.outcome is ReassemblyOutcome.COMPLETED]

    def assert_idle(self, source_id: int) -> None:
        context = self.reassembler.contexts[source_id]
        self.assertIs(context.state, ContextState.IDLE)
        self.assertEqual(context.received_length, 0)
        self.assertEqual(context.expected_length, 0)


class NormalSequenceTest(ReassemblerTestCase):
    """Valid First/Consecutive Frames and completion."""

    def test_valid_first_frame_starts_context(self) -> None:
        result = self.reassembler.process(first_frame(ID_0, len(MESSAGE), MESSAGE[:6]))
        self.assertIs(result.outcome, ReassemblyOutcome.IN_PROGRESS)
        context = self.reassembler.contexts[ID_0]
        self.assertIs(context.state, ContextState.RECEIVING)
        self.assertEqual(context.expected_length, len(MESSAGE))
        self.assertEqual(context.received_length, 6)
        self.assertEqual(context.expected_sequence, 1)

    def test_valid_consecutive_frame_appends_and_advances_sequence(self) -> None:
        frames = segment_message(ID_0, MESSAGE)
        results = self.feed(frames[:2])
        self.assertIs(results[1].outcome, ReassemblyOutcome.IN_PROGRESS)
        context = self.reassembler.contexts[ID_0]
        self.assertEqual(context.received_length, 13)
        self.assertEqual(context.expected_sequence, 2)

    def test_complete_message_reconstruction_ignores_padding(self) -> None:
        frames = segment_message(ID_0, MESSAGE)
        results = self.feed(frames)
        self.assertEqual([r.outcome for r in results[:-1]], [ReassemblyOutcome.IN_PROGRESS] * (len(frames) - 1))
        self.assertIs(results[-1].outcome, ReassemblyOutcome.COMPLETED)
        self.assertEqual(results[-1].payload, MESSAGE)
        self.assertEqual(results[-1].frame_count, len(frames))

    def test_maximum_length_message_is_accepted(self) -> None:
        message = bytes(range(MAX_DIAGNOSTIC_LENGTH))
        self.assertEqual(self.completed_payloads(segment_message(ID_1, message)), [message])

    def test_context_cleanup_after_completion(self) -> None:
        self.feed(segment_message(ID_0, MESSAGE))
        self.assert_idle(ID_0)

    def test_sequence_number_wraparound(self) -> None:
        # 6 + 16 * 7 = 118 bytes forces nibbles 1..15, 0, 1; needs a larger limit.
        reassembler = SegmentedReassembler([ID_0], max_message_length=200)
        message = bytes(i % 256 for i in range(6 + 16 * 7 + 3))
        frames = segment_message(ID_0, message)
        nibbles = [frame.data[0] & 0x0F for frame in frames[1:]]
        self.assertEqual(nibbles[14:17], [15, 0, 1])
        results = [reassembler.process(frame) for frame in frames]
        self.assertIs(results[-1].outcome, ReassemblyOutcome.COMPLETED)
        self.assertEqual(results[-1].payload, message)


class ConcurrencyTest(ReassemblerTestCase):
    """Independent contexts under interleaved traffic."""

    def test_multiple_contexts_active_simultaneously(self) -> None:
        for source_id in SOURCE_IDS:
            self.reassembler.process(first_frame(source_id, len(MESSAGE), MESSAGE[:6]))
        states = [self.reassembler.contexts[source_id].state for source_id in SOURCE_IDS]
        self.assertEqual(states, [ContextState.RECEIVING] * MODULE_COUNT)

    def test_interleaved_module_traffic(self) -> None:
        messages = {source_id: f"SN:PMU-447{i}-X FW:2.{i}.0 #{i}".encode() for i, source_id in enumerate(SOURCE_IDS)}
        frames = interleave(*(segment_message(source_id, text) for source_id, text in messages.items()))
        completed = {}
        for frame in frames:
            result = self.reassembler.process(frame)
            if result.outcome is ReassemblyOutcome.COMPLETED:
                completed[frame.can_id] = result.payload
        self.assertEqual(completed, messages)

    def test_irregular_interleaving_from_spec(self) -> None:
        texts = [b"MODULE-0 IDENT STRING", b"MODULE-1 IDENT STRING", b"MODULE-2 IDENT STRING", b"MODULE-3 IDENT STRING"]
        segmented = [segment_message(source_id, text) for source_id, text in zip(SOURCE_IDS, texts)]
        order = [0, 1, 2, 3, 0, 2, 1, 3, 3, 2, 1, 0, 1, 0, 3, 2]
        positions = [0, 0, 0, 0]
        payloads = {}
        for module in order:
            frame = segmented[module][positions[module]]
            positions[module] += 1
            result = self.reassembler.process(frame)
            if result.outcome is ReassemblyOutcome.COMPLETED:
                payloads[module] = result.payload
        self.assertEqual(payloads, dict(enumerate(texts)))

    def test_error_on_one_module_does_not_affect_others(self) -> None:
        good = segment_message(ID_1, MESSAGE)
        self.feed([good[0], first_frame(ID_0, len(MESSAGE), MESSAGE[:6])])
        self.reassembler.process(consecutive_frame(ID_0, 9, b"garbage"))
        self.assertEqual(self.completed_payloads(good[1:]), [MESSAGE])


class MessySituationTest(ReassemblerTestCase):
    """The five bus situations from CHALLENGE.md, each followed by recovery."""

    def test_orphan_consecutive_frame_is_ignored(self) -> None:
        result = self.reassembler.process(consecutive_frame(ID_2, 5, bytes(7)))
        self.assertIs(result.outcome, ReassemblyOutcome.ORPHAN_CONSECUTIVE_FRAME)
        self.assert_idle(ID_2)
        self.assertEqual(self.completed_payloads(segment_message(ID_2, MESSAGE)), [MESSAGE])

    def test_restarting_first_frame_replaces_unfinished_message(self) -> None:
        decoy = segment_message(ID_3, b"XX:DECOY-NOT-REAL-MSG")
        self.feed(decoy[:2])
        frames = segment_message(ID_3, MESSAGE)
        self.assertEqual(self.completed_payloads(frames), [MESSAGE])
        self.assert_idle(ID_3)

    def test_restart_does_not_mix_old_buffer_into_new_message(self) -> None:
        self.feed(segment_message(ID_0, b"OLD-OLD-OLD-OLD-OLD-OLD")[:3])
        self.reassembler.process(first_frame(ID_0, len(MESSAGE), MESSAGE[:6]))
        self.assertEqual(self.reassembler.contexts[ID_0].received_length, 6)

    def test_oversized_first_frame_is_rejected(self) -> None:
        result = self.reassembler.process(first_frame(ID_1, 200, bytes(6)))
        self.assertIs(result.outcome, ReassemblyOutcome.OVERSIZED)
        self.assert_idle(ID_1)

    def test_oversized_message_followers_are_orphans(self) -> None:
        self.reassembler.process(first_frame(ID_1, MAX_DIAGNOSTIC_LENGTH + 1, bytes(6)))
        result = self.reassembler.process(consecutive_frame(ID_1, 1, bytes(7)))
        self.assertIs(result.outcome, ReassemblyOutcome.ORPHAN_CONSECUTIVE_FRAME)
        self.assertEqual(self.completed_payloads(segment_message(ID_1, MESSAGE)), [MESSAGE])

    def test_out_of_order_sequence_abandons_message(self) -> None:
        broken = segment_message(ID_0, MESSAGE + b"-BROKEN")
        self.feed(broken[:2])
        result = self.reassembler.process(consecutive_frame(ID_0, 3, broken[3].data[1:]))
        self.assertIs(result.outcome, ReassemblyOutcome.SEQUENCE_ERROR)
        self.assert_idle(ID_0)

    def test_frames_after_sequence_error_do_not_complete(self) -> None:
        broken = segment_message(ID_0, MESSAGE)
        results = self.feed([broken[0], broken[2]] + broken[3:])
        self.assertNotIn(ReassemblyOutcome.COMPLETED, [r.outcome for r in results])
        self.assertEqual(self.completed_payloads(segment_message(ID_0, MESSAGE)), [MESSAGE])

    def test_repeated_first_frames_then_complete_message(self) -> None:
        lone = first_frame(ID_2, len(MESSAGE), MESSAGE[:6])
        self.feed([lone] * 5)
        self.assertEqual(self.completed_payloads(segment_message(ID_2, MESSAGE)), [MESSAGE])


class ValidationTest(ReassemblerTestCase):
    """Malformed transport frames are rejected without crashing."""

    def test_unknown_source(self) -> None:
        result = self.reassembler.process(first_frame(0x6F4, len(MESSAGE), MESSAGE[:6]))
        self.assertIs(result.outcome, ReassemblyOutcome.UNKNOWN_SOURCE)
        self.assertNotIn(0x6F4, self.reassembler.contexts)

    def test_empty_frame(self) -> None:
        result = self.reassembler.process(CANFrame(can_id=ID_0, data=b""))
        self.assertIs(result.outcome, ReassemblyOutcome.MALFORMED_FRAME)

    def test_short_first_frame(self) -> None:
        result = self.reassembler.process(CANFrame(can_id=ID_0, data=b"\x10\x16ABC"))
        self.assertIs(result.outcome, ReassemblyOutcome.MALFORMED_FRAME)
        self.assert_idle(ID_0)

    def test_declared_length_below_minimum(self) -> None:
        result = self.reassembler.process(first_frame(ID_0, 7, b"ABCDEF"))
        self.assertIs(result.outcome, ReassemblyOutcome.INVALID_LENGTH)
        self.assert_idle(ID_0)

    def test_consecutive_frame_without_data_abandons(self) -> None:
        self.reassembler.process(first_frame(ID_0, len(MESSAGE), MESSAGE[:6]))
        result = self.reassembler.process(CANFrame(can_id=ID_0, data=b"\x21"))
        self.assertIs(result.outcome, ReassemblyOutcome.MALFORMED_FRAME)
        self.assert_idle(ID_0)

    def test_unsupported_frame_type_leaves_context_untouched(self) -> None:
        self.reassembler.process(first_frame(ID_0, len(MESSAGE), MESSAGE[:6]))
        result = self.reassembler.process(CANFrame(can_id=ID_0, data=b"\x30\x00\x00"))
        self.assertIs(result.outcome, ReassemblyOutcome.UNSUPPORTED_FRAME_TYPE)
        self.assertEqual(self.reassembler.contexts[ID_0].received_length, 6)


class BoundedMemoryTest(ReassemblerTestCase):
    """Repeated abandonment must not grow state."""

    def abandonment_cycle(self) -> None:
        for source_id in SOURCE_IDS:
            self.reassembler.process(first_frame(source_id, len(MESSAGE), MESSAGE[:6]))
            self.reassembler.process(first_frame(source_id, 200, bytes(6)))
            self.reassembler.process(consecutive_frame(source_id, 4, bytes(7)))
            self.feed(segment_message(source_id, MESSAGE)[:2])

    def test_context_cleanup_after_abandonment(self) -> None:
        self.feed(segment_message(ID_0, MESSAGE)[:2])
        self.reassembler.process(consecutive_frame(ID_0, 7, bytes(7)))
        self.assert_idle(ID_0)

    def test_context_count_and_buffers_stay_bounded(self) -> None:
        for _ in range(2000):
            self.abandonment_cycle()
        self.assertEqual(set(self.reassembler.contexts), set(SOURCE_IDS))
        for context in self.reassembler.contexts.values():
            self.assertLessEqual(context.received_length, MAX_DIAGNOSTIC_LENGTH)

    def test_memory_does_not_grow_with_repeated_abandonment(self) -> None:
        for _ in range(200):
            self.abandonment_cycle()
        tracemalloc.start()
        try:
            baseline, _ = tracemalloc.get_traced_memory()
            for _ in range(5000):
                self.abandonment_cycle()
            current, _ = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertLess(current - baseline, 4096)


if __name__ == "__main__":
    unittest.main()
