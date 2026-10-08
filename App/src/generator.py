#!/usr/bin/env python3
"""DeepSea CAN traffic generator -- ground truth source for the grading harness.

Not part of what candidates submit. Candidates get a copy to run locally
while developing; grading always uses DSD's own copy.

Design note: every scheduled action is a single, already-computed CAN frame
send at an absolute time offset. Nothing here sleeps *inside* an action --
all timing math (abandon gaps, consecutive-frame pacing, cycle repetition)
is done up front when building the schedule, then one flat, time-sorted list
is walked by a single loop that only ever sleeps to reach the next action.
An earlier draft nested sleeps inside per-context cycle handling, which
blocked the whole generator for seconds at a time and starved every other
scheduled event (telemetry, noise, other contexts) of its own timing --
caught before ever running it, not from a live bug.

Usage:
    python3 generator.py --iface vcan0 --duration 75 --out ground_truth.jsonl
"""
import argparse
import json
import random
import socket
import struct
import subprocess
import sys
import time

TELEMETRY_BASE = 0x100
FAULT_ID = 0x1F0
DIAG_BASE = 0x6F0
NOISE_LO, NOISE_HI = 0x200, 0x2FF
NUM_MODULES = 4
CF_PACING = 0.03  # seconds between consecutive frames of one message

DIAG_STRINGS = [
    "SN:PMU-4471-A FW:2.3.1",
    "SN:PMU-4472-B FW:2.3.1",
    "SN:PMU-4473-C FW:2.4.0",
    "SN:PMU-4474-D FW:2.4.0",
]

FRAME_FMT = "=IB3x8s"  # canid_t, dlc, 3 pad bytes, 8-byte data (struct can_frame)


def ensure_iface(iface):
    result = subprocess.run(["ip", "link", "show", iface], capture_output=True, text=True)
    if result.returncode == 0:
        return
    print(f"[generator] {iface} not found, attempting to bring it up...", file=sys.stderr)
    subprocess.run(["sudo", "modprobe", "vcan"], check=False)
    subprocess.run(["sudo", "ip", "link", "add", "dev", iface, "type", "vcan"], check=False)
    r = subprocess.run(["sudo", "ip", "link", "set", "up", iface], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"[generator] could not bring up {iface}: {r.stderr}")


def open_socket(iface):
    sock = socket.socket(socket.AF_CAN, socket.SOCK_RAW, socket.CAN_RAW)
    sock.bind((iface,))
    return sock


def pack_frame(can_id, data):
    data = data[:8].ljust(8, b"\x00")
    return struct.pack(FRAME_FMT, can_id, len(data), data)


def ff_bytes(total_len, first6):
    b0 = 0x10 | ((total_len >> 8) & 0x0F)
    b1 = total_len & 0xFF
    return bytes([b0, b1]) + first6.ljust(6, b"\x00")


def cf_bytes(seq_nibble, chunk):
    b0 = 0x20 | (seq_nibble & 0x0F)
    return bytes([b0]) + chunk.ljust(7, b"\x00")


def message_cf_chunks(msg):
    """Yield (seq_nibble, chunk) for every Consecutive Frame needed after the
    First Frame's initial 6 bytes, per the 1,2,...,15,0,1,... wrap rule."""
    rest = msg[6:]
    nibble = 1
    for i in range(0, len(rest), 7):
        yield nibble, rest[i:i + 7]
        nibble = (nibble + 1) % 16


class GroundTruth:
    def __init__(self, path):
        self.f = open(path, "w")

    def log(self, event, **kw):
        rec = {"event": event}
        rec.update(kw)
        self.f.write(json.dumps(rec) + "\n")
        self.f.flush()

    def close(self):
        self.f.close()


def build_telemetry_schedule(duration):
    events = []
    period = 0.5
    n = int(duration / period)
    for i in range(n):
        t = i * period
        for m in range(NUM_MODULES):
            events.append((t + m * 0.05, "telemetry", {"module": m}))
    return events


def build_fault_schedule(duration):
    events = []
    lo, hi = 10, max(11, int(duration) - 5)
    k = min(3, max(1, int(duration // 20)))
    times = sorted(random.sample(range(lo, hi), k=k))
    for t in times:
        events.append((float(t), "fault", {"module": random.randrange(NUM_MODULES),
                                            "code": random.randrange(1, 5)}))
    return events


def build_noise_schedule(duration):
    events = []
    half = duration / 2.0
    t = 0.0
    while t < half:
        t += 1.0 / 20.0
        events.append((t, "noise", {}))
    t = half
    while t < duration:
        t += 1.0 / 150.0
        events.append((t, "noise", {}))
    return events


def build_message_frames(can_id, ctx, counter):
    """Returns (text, [frame_byte_payloads...]) for one complete message:
    first entry is the First Frame payload, the rest are Consecutive Frames,
    in send order. Kept separate from scheduling so the round-robin builder
    below can interleave frames from several contexts' messages frame-by-
    frame rather than one whole message at a time."""
    text = f"{DIAG_STRINGS[ctx]} #{counter}"
    msg = text.encode("ascii")
    frames = [("diag_ff", {"can_id": can_id, "ctx": ctx, "len": len(msg), "first6": msg[:6]})]
    for nibble, chunk in message_cf_chunks(msg):
        frames.append(("diag_cf", {"can_id": can_id, "ctx": ctx, "nibble": nibble, "chunk": chunk}))
    return text, frames


def build_diag_schedule(duration):
    """Fully flattened: every individual frame of every cycle, for every
    context, as its own (t, action) entry. No function here sleeps -- this
    only computes times.

    All 4 contexts are synchronized to the same cycle boundaries (no stagger)
    specifically so their real message bursts genuinely overlap in time, and
    within a burst, frames from different contexts are interleaved
    round-robin (ctx0 First Frame, ctx1 First Frame, ..., ctx0 frame 2, ctx1
    frame 2, ...) rather than one context finishing before the next starts.
    An earlier version staggered contexts 2s apart while each burst only
    took ~0.15s to send -- bursts never actually overlapped, so a consumer
    using a single shared buffer across all contexts (a real bug) sailed
    through undetected. Caught by testing a deliberately-broken variant
    against this exact schedule, not assumed from reading the code."""
    events = []
    cycle_period = 0.25
    abandon_gap = 0.1
    round_gap = 0.02  # pacing between successive rounds of the interleaved burst
    epsilon = 0.004    # tiny offset between contexts within the same round, keeps ordering deterministic

    # Which context gets which situation, and on which cycle, is randomized
    # fresh every run (no fixed seed) -- deliberately, not an oversight.
    # CHALLENGE.md tells candidates each situation happens "once each, on
    # one of the four IDs" specifically because it must not be predictable:
    # a candidate who could read this file and find a hardcoded mapping
    # would know exactly what's coming and could narrowly pattern-match the
    # test instead of building a genuinely general per-context state
    # machine. This costs nothing in grading determinism -- grade.py always
    # scores against that run's own logged ground truth, never a hardcoded
    # expectation, and already reads the situation-to-can_id mapping
    # generically from the log rather than assuming any fixed assignment.
    situations_order = ["orphan_cf", "restart_ff", "oversized_len", "out_of_order"]
    random.shuffle(situations_order)
    contexts_order = list(range(NUM_MODULES))
    random.shuffle(contexts_order)
    approx_total_cycles = max(8, int((duration - 2) / cycle_period))
    special_at_cycle = {}
    for i in range(NUM_MODULES):
        ctx = contexts_order[i]
        situation = situations_order[i]
        fire_cycle = random.randint(3, approx_total_cycles - 3)
        special_at_cycle[ctx] = (situation, fire_cycle)

    counters = [0, 0, 0, 0]
    cycle_idx = 0
    t_cycle = 0.0

    while t_cycle < duration - 2:
        # Phase 1: each context's "attempt start" for this cycle -- either a
        # normal lone First Frame (which is what makes case 5, repeated
        # abandonment, happen every cycle for every context) or, on its one
        # designated cycle, a special situation's opening frames.
        for ctx in range(NUM_MODULES):
            can_id = DIAG_BASE + ctx
            special_case, special_cycle = special_at_cycle[ctx]
            is_special = (cycle_idx == special_cycle)
            t = t_cycle + ctx * epsilon

            if not is_special:
                placeholder = DIAG_STRINGS[ctx].encode("ascii")
                events.append((t, "diag_ff", {"can_id": can_id, "ctx": ctx, "len": len(placeholder),
                                               "first6": placeholder[:6]}))
            elif special_case == "orphan_cf":
                events.append((t, "diag_situation", {"can_id": can_id, "case": "orphan_cf"}))
                events.append((t + epsilon / 2, "diag_cf", {"can_id": can_id, "ctx": ctx, "nibble": 5,
                                                             "chunk": b"\x00" * 7}))
            elif special_case == "restart_ff":
                decoy = b"XX:DECOY-NOT-REAL-MSG"
                events.append((t, "diag_situation", {"can_id": can_id, "case": "restart_ff"}))
                events.append((t, "diag_ff", {"can_id": can_id, "ctx": ctx, "len": len(decoy),
                                               "first6": decoy[:6]}))
                events.append((t + round_gap, "diag_cf", {"can_id": can_id, "ctx": ctx, "nibble": 1,
                                                           "chunk": decoy[6:13]}))
            elif special_case == "oversized_len":
                events.append((t, "diag_situation", {"can_id": can_id, "case": "oversized_len"}))
                events.append((t, "diag_ff", {"can_id": can_id, "ctx": ctx, "len": 200,
                                               "first6": b"\x00" * 6}))
            elif special_case == "out_of_order":
                events.append((t, "diag_situation", {"can_id": can_id, "case": "out_of_order"}))
                broken = f"{DIAG_STRINGS[ctx]} #{counters[ctx]}-BROKEN".encode("ascii")
                events.append((t, "diag_ff", {"can_id": can_id, "ctx": ctx, "len": len(broken),
                                               "first6": broken[:6]}))
                rest = broken[6:]
                events.append((t + round_gap, "diag_cf", {"can_id": can_id, "ctx": ctx, "nibble": 1,
                                                           "chunk": rest[0:7]}))
                skip_chunk = rest[7:14] if len(rest) > 7 else b"\x00" * 7
                events.append((t + 2 * round_gap, "diag_cf", {"can_id": can_id, "ctx": ctx, "nibble": 3,
                                                               "chunk": skip_chunk}))  # skips nibble 2

        # Phase 2: after the abandon gap, all 4 contexts' real/recovery
        # messages are sent simultaneously, genuinely interleaved frame by
        # frame (round-robin), not one context finishing before the next.
        t_burst = t_cycle + abandon_gap
        per_ctx_frames = []
        per_ctx_text = []
        for ctx in range(NUM_MODULES):
            counters[ctx] += 1
            can_id = DIAG_BASE + ctx
            text, frames = build_message_frames(can_id, ctx, counters[ctx])
            per_ctx_frames.append(frames)
            per_ctx_text.append(text)

        max_rounds = max(len(f) for f in per_ctx_frames)
        last_time_per_ctx = [t_burst] * NUM_MODULES
        for round_idx in range(max_rounds):
            for ctx in range(NUM_MODULES):
                if round_idx < len(per_ctx_frames[ctx]):
                    t_frame = t_burst + round_idx * round_gap + ctx * epsilon
                    events.append((t_frame,) + per_ctx_frames[ctx][round_idx])
                    last_time_per_ctx[ctx] = t_frame

        for ctx in range(NUM_MODULES):
            can_id = DIAG_BASE + ctx
            events.append((last_time_per_ctx[ctx] + epsilon, "diag_complete_mark",
                            {"can_id": can_id, "ctx": ctx, "string": per_ctx_text[ctx]}))

        t_cycle += cycle_period
        cycle_idx += 1

    return events


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iface", default="vcan0")
    ap.add_argument("--duration", type=float, default=75.0)
    ap.add_argument("--out", default="ground_truth.jsonl")
    args = ap.parse_args()

    ensure_iface(args.iface)
    sock = open_socket(args.iface)
    gt = GroundTruth(args.out)

    events = []
    events += build_telemetry_schedule(args.duration)
    events += build_fault_schedule(args.duration)
    events += build_noise_schedule(args.duration)
    events += build_diag_schedule(args.duration)
    events.sort(key=lambda e: e[0])

    print(f"[generator] {len(events)} scheduled events over {args.duration}s on {args.iface}", file=sys.stderr)

    telemetry_state = [{"seq": 0, "voltage": 400.0 + m * 2.0, "current": 100.0 + m,
                        "temp": 35 + m, "fault_until": -1.0} for m in range(NUM_MODULES)]

    run_start = time.monotonic()
    real_frame_count = 0

    for t, kind, data in events:
        now = time.monotonic() - run_start
        delay = t - now
        if delay > 0:
            time.sleep(delay)

        if kind == "telemetry":
            m = data["module"]
            st = telemetry_state[m]
            st["seq"] = (st["seq"] + 1) & 0xFFFF
            voltage = st["voltage"] + random.uniform(-0.5, 0.5)
            current = st["current"] + random.uniform(-0.3, 0.3)
            temp = st["temp"] + random.uniform(-1, 1)
            fault_active = time.monotonic() < st["fault_until"]
            v_raw = max(0, min(0xFFFF, round(voltage / 0.1)))
            c_raw = max(0, min(0xFFFF, round(current / 0.01)))
            t_raw = max(0, min(255, round(temp + 40)))
            status = 0x01 | (0x02 if fault_active else 0)
            payload = struct.pack("<HHBBH", v_raw, c_raw, t_raw, status, st["seq"])
            sock.send(pack_frame(TELEMETRY_BASE + m, payload))
            real_frame_count += 1
            gt.log("telemetry_sent", module=m, seq=st["seq"],
                   voltage=round(v_raw * 0.1, 2), current=round(c_raw * 0.01, 2),
                   temp_c=t_raw - 40, enabled=True, fault=fault_active, derated=False)

        elif kind == "fault":
            m, code = data["module"], data["code"]
            payload = bytes([m, code, 0, 0, 0, 0, 0, 0])
            sock.send(pack_frame(FAULT_ID, payload))
            real_frame_count += 1
            telemetry_state[m]["fault_until"] = time.monotonic() + 5.0
            gt.log("fault_sent", module=m, code=code)

        elif kind == "noise":
            noise_id = random.randrange(NOISE_LO, NOISE_HI + 1)
            payload = bytes(random.randrange(256) for _ in range(8))
            sock.send(pack_frame(noise_id, payload))

        elif kind == "diag_ff":
            sock.send(pack_frame(data["can_id"], ff_bytes(data["len"], data["first6"])))
            real_frame_count += 1

        elif kind == "diag_cf":
            sock.send(pack_frame(data["can_id"], cf_bytes(data["nibble"], data["chunk"])))
            real_frame_count += 1

        elif kind == "diag_situation":
            gt.log("diag_situation", can_id=hex(data["can_id"]), case=data["case"])

        elif kind == "diag_complete_mark":
            gt.log("diag_complete_sent", can_id=hex(data["can_id"]), string=data["string"])

    gt.log("run_summary", real_frame_count=real_frame_count)
    gt.close()
    print(f"[generator] done, real_frame_count={real_frame_count}", file=sys.stderr)


if __name__ == "__main__":
    main()