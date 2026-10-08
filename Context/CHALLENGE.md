# DeepSea Developments — Embedded Linux Challenge (CAN Bus Diagnostic Tool)

## The Problem

DeepSea's Level 3 DC Fast Charger stations use an internal CAN bus so the main controller can talk to up to 4 power modules. Field engineers can't open the sealed, live, high-voltage enclosure to check on them directly.

Build a diagnostic tool that runs on the controller and:
- shows each module's live electrical readings and any fault codes,
- decodes each module's identification string (serial number, firmware version), sent in pieces across multiple CAN frames because it's too long for one,
- ignores unrelated traffic also present on the same bus,
- keeps working correctly even when the bus behaves messily (details below).

This is a systems-design evaluation, not just a coding exercise. The IPC/filtering mechanism and the state-management design for reassembly are yours to decide and defend in writing.

## Constraints

- **Language: Python 3, standard library only.** Use `socket` (`AF_CAN` / `SOCK_RAW` / `socket.CAN_RAW`) and `struct` directly for all bus I/O and byte packing.
- **Banned**: `python-can` (including its `isotp` transport), `can-isotp` / the kernel `CAN_ISOTP` socket type, `cantools`, `canmatrix`, or any library whose purpose is CAN filtering, message decoding, or ISO-TP/UDS reassembly. These would solve the challenge for you.
- **Receive only.** Your tool never transmits a CAN frame.

## The Bus

A traffic generator (given to you, described under "What's On the Device" below) emits bus traffic on `vcan0` matching the spec below.

### Wire format

All IDs are standard 11-bit. `vcan0` has no physical-layer arbitration, so frames arrive in exactly the order the generator sends them.

**Power module telemetry** — IDs `0x100`–`0x103` (module 0–3), 8-byte payload:

| bytes | field | encoding |
|---|---|---|
| 0–1 | voltage_raw | uint16 little-endian; volts = raw × 0.1 |
| 2–3 | current_raw | uint16 little-endian; amps = raw × 0.01 |
| 4 | temp_raw | uint8; °C = raw − 40 |
| 5 | status | bitfield: bit0 enabled, bit1 fault, bit2 derated |
| 6–7 | seq | uint16 little-endian, increments per send |

**Fault code** — ID `0x1F0`, 8-byte payload: byte0 = module_id, byte1 = fault_code (1=overtemp, 2=overvoltage, 3=undervoltage, 4=isolation_fault), bytes 2–7 = 0.

**Multi-frame identification string** — IDs `0x6F0`–`0x6F3` (one per module), sent unprompted. ISO 15765-2-style framing:

- **First Frame**: byte0 = `0x10 | (len >> 8)`, byte1 = `len & 0xFF`, bytes 2–7 = first 6 bytes of the message. `len` is the *total* message length, including those 6 bytes.
- **Consecutive Frame**: byte0 = `0x20 | seq_nibble`, bytes 1–7 = next up to 7 bytes (final frame may be padded — ignore anything past the declared `len`). `seq_nibble` starts at 1, increments by 1 mod 16 (cycles 1,2,…,15,0,1,…).
- Messages are always longer than 7 bytes (no Single Frame case) and never longer than **64 bytes**.

**Noise** — unrelated traffic on IDs `0x200`–`0x2FF`, volume increasing partway through the run. Ignore it.

### Five things that will happen on the bus

Once each, on one of the four identification-string IDs:

1. **Orphan Consecutive Frame** — arrives with no First Frame in progress. Ignore it.
2. **Restarting First Frame** — a new First Frame arrives mid-message. Drop the old attempt, start fresh.
3. **Oversized length claim** — a First Frame claims more than 64 bytes. Reject it.
4. **Out-of-order sequence number** — wrong `seq_nibble`. Abandon that attempt.

None of these should crash your tool, affect any other module's in-progress message, or produce a wrong result — the correct outcome is simply not completing that one attempt. Each is followed by one clean, complete message on the same ID, which you must reassemble correctly.

5. **Repeated abandonment** — throughout the run, a module will sometimes send only a First Frame and go quiet before eventually sending a complete message. There are only ever 4 modules. Your state management must not grow without bound as this repeats.

## What You Deliver

A public GitHub or GitLab repository:

```
your-repo/
├── main.py       (required entry point — see below)
└── README.md     (required — see below)
```

**`main.py`**, run exactly as:

```
python3 main.py --iface vcan0            # normal mode: terminal dashboard
python3 main.py --iface vcan0 --grader   # grader mode: NDJSON to stdout, see ADAPTER.md
```

**Normal mode** — an in-place terminal dashboard (no `ncurses`, no UI library), showing current readings, faults, and identification strings. Roughly, in whatever layout you prefer:

```
DeepSea CAN Diagnostic Tool
---------------------------
Module 0:  412.3V  118.55A   47C   enabled=True  fault=False
Module 1:  405.1V  120.02A   45C   enabled=True  fault=False
Module 2:  399.8V  115.30A   46C   enabled=True  fault=True
Module 3:  410.0V  119.87A   44C   enabled=True  fault=False
---------------------------
Identification strings:
  0x6f0: SN:PMU-4471-A FW:2.3.1
  0x6f1: SN:PMU-4472-B FW:2.3.1
  0x6f2: SN:PMU-4473-C FW:2.4.0
  0x6f3: (not yet received)
---------------------------
Recent faults:
  module 2, code 1
```

**Grader mode** — see `ADAPTER.md` for the exact NDJSON contract your tool must emit.

**`README.md`** (required; not separately scored, but part of the deliverable and may be read by the interviewer) — your filtering-mechanism choice and why, your reassembly state-management design (how you key, bound, and expire per-message state, and why), and anything you'd do differently with more time.

## Scoring

100 points, fully automated — every category below is measured against the real bus or by static analysis of your repo, with no manual review step.

| Category | Points |
|---|---|
| Build/run succeeds cleanly (both modes) | 10 |
| Filtering — reported frame count matches ground truth | 15 |
| Decoding — telemetry (20) + fault codes (5) | 25 |
| Reassembly — concurrent decode (15) + surviving the 5 situations (10) + bounded memory (10) | 35 |
| Code quality — static analysis of your repo | 15 |

Filtering is scored on correctness only, not speed or resource use. The one exception across all of scoring is bounded memory under Reassembly, which checks whether your design has a bound at all — not a performance number.

**Code quality** is measured by static analysis, not a human read of your code: worst-case function complexity, function length/decomposition, docstring presence, and unused imports. Exact thresholds aren't published — write clean, well-decomposed code rather than aiming at a number.

**Using a banned library anywhere in your repo, or a call that transmits a CAN frame anywhere in your code, zeroes your entire score.** Both are checked statically across your whole repo, not just what executes during the test window.

## Getting Access

The system runs on a headless Raspberry Pi 5, reached remotely via Raspberry Pi Connect (the enclosure is sealed and live — this simulates that).

1. Create a free account at connect.raspberrypi.com.
2. Generate an Auth Key (Settings → Create Auth Key) and send it to DeepSea.
3. Once linked, SSH in via the Raspberry Pi Connect portal. You'll receive the `pi` account's `sudo` password with your access.

## What's On the Device

- **`~/challenge/`** — read-only reference materials: this brief, `ADAPTER.md`, `can_generator/generator.py`.
- **`vcan0`** is already up.
- **The traffic generator is not running.** Start it yourself, whenever you want live traffic to test against:
  ```
  python3 ~/challenge/can_generator/generator.py --iface vcan0 --duration 90
  ```
  It runs for the given duration, then stops. Use a longer duration (e.g. `600`) to check your own design's memory behavior over many abandonment cycles.
- **Clone your repository into `~/workspace/`.**

## Deadline

24 hours from confirmed hardware access. Share your repository link when done — nothing to clean up on the device.