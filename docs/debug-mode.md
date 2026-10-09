# Debug Mode

How to enable debug logging, what each log line means, and how to use it to verify the tool against the challenge generator on `vcan0`.

This is an operational guide. Requirements live in `feature-specs/`; architecture lives in `architecture-context.md`. Update this file whenever a feature adds, removes or renames a debug log line.

---

## 1. What `--debug` Does

```bash
python App/src/main.py --iface vcan0 --debug
```

`--debug` only changes the logging level. It does not change processing, state or output.

| | Without `--debug` | With `--debug` |
|---|---|---|
| Log level | `WARNING` | `DEBUG` |
| What you see | Real errors only (e.g. interface cannot be opened) | Every complete message, every rejected frame, socket open/close |
| Destination | stderr | stderr |
| Log file | None | None |

Logging is configured once, in `configure_logging()` in `App/src/main.py`:

```python
logging.basicConfig(
    stream=sys.stderr,
    level=logging.DEBUG if config.debug else logging.WARNING,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
```

All logging goes to **stderr**. stdout is never written by logging, so debug mode can be combined with grader mode (once implemented) without corrupting the NDJSON stream.

---

## 2. Log Line Format

```text
2026-10-08 19:51:04,917 DEBUG transport.can_transport: source 0x6f2: frame rejected (sequence_error)
└──────── asctime ────┘ └level┘ └──── logger name ────┘ └──────────────── message ───────────────┘
```

The logger name is the module that wrote the line, so you can filter by layer.

| Logger name | Layer | Source file |
|---|---|---|
| `deepsea` | Entry point / temporary upper layer | `App/src/main.py` |
| `communication.socketcan` | Communication (SocketCAN) | `App/src/communication/socketcan.py` |
| `transport.can_transport` | Transport (CAN framing) | `App/src/transport/can_transport.py` |
| `transport.reassembler` | Transport (segmented reassembly) | `App/src/transport/reassembler.py` |

---

## 3. Log Line Catalog

### Communication layer

| Message | Written by | Meaning |
|---|---|---|
| `SocketCAN opened on vcan0` | `SocketCanInterface.open()` | Socket created and bound. |
| `SocketCAN closed on vcan0` | `SocketCanInterface.close()` | Socket released on shutdown. |
| `dropped invalid CAN frame: <reason>` | `SocketCanInterface.receive()` | Raw frame failed basic validation (wrong size, DLC > 8, extended/remote/error flag). Counted in `invalid_frames`, never passed on. |

### Transport layer

| Message | Written by | Meaning |
|---|---|---|
| `source 0x6fX: First Frame restarts unfinished message` | `SegmentedReassembler._handle_first_frame()` | A First Frame arrived while a message was in progress on that ID. The old attempt is dropped and the new one starts. |
| `source 0x6fX: frame rejected (<reason>)` | `CanTransport._process_segmented()` | A diagnostic frame did not advance a valid message. See reasons below. |

Rejection reasons:

| Reason | Cause | Challenge situation |
|---|---|---|
| `orphan_consecutive_frame` | CF with no message in progress | 1. Orphan Consecutive Frame |
| `oversized` | FF declares more than 64 bytes | 3. Oversized length claim |
| `sequence_error` | CF with the wrong sequence nibble; attempt abandoned | 4. Out-of-order sequence |
| `invalid_length` | FF declares fewer than 8 bytes (no Single Frame case exists) | Not sent by the generator |
| `malformed_frame` | FF shorter than 8 bytes, or empty / header-only CF | Not sent by the generator |
| `unsupported_frame_type` | PCI type is neither FF (`0x1_`) nor CF (`0x2_`) | Not sent by the generator |

### Upper layer (temporary)

| Message | Written by | Meaning |
|---|---|---|
| `message 0xNNN (single_frame, 1 frame(s)): <hex>` | `LoggingMessageListener` in `main.py` | Telemetry (`0x100`–`0x103`) or fault (`0x1F0`) frame delivered as a complete message. |
| `message 0x6fX (segmented, N frame(s)): <hex>` | `LoggingMessageListener` in `main.py` | Identification string fully reassembled and delivered. |

`LoggingMessageListener` is a placeholder until the router and protocol decoders exist. Payloads are printed in hex because nothing decodes them yet.

Noise frames (`0x200`–`0x2FF`) produce **no log line**: the transport ignores them silently.

---

## 4. What a Normal Run Looks Like

The generator repeats a 0.25 s cycle on every identification ID:

```text
t + 0.00 s   lone First Frame             → context starts receiving
t + 0.10 s   new First Frame (real msg)   → "First Frame restarts unfinished message"
t + 0.10 s   Consecutive Frames ...       → (no line while in progress)
t + ~0.16 s  last Consecutive Frame       → "message 0x6fX (segmented, 4 frame(s)): ..."
```

So **one `restarts` line per message is normal**. That is challenge situation 5 (repeated abandonment), and it happens on every ID every cycle.

The four special situations each happen once per run, on a random ID and cycle. Each one is followed by a clean message on the same ID:

| Situation | Expected lines on that ID |
|---|---|
| Orphan CF | `frame rejected (orphan_consecutive_frame)` → `message ... (segmented ...)` |
| Restarting FF | `First Frame restarts unfinished message` → `message ... (segmented ...)` (indistinguishable from a normal cycle) |
| Oversized length | `frame rejected (oversized)` → `message ... (segmented ...)` |
| Out-of-order | `frame rejected (sequence_error)` → `message ... (segmented ...)` |

Approximate totals for a 75 s generator run:

| Line | Approx. count |
|---|---|
| `segmented` | ~1170 (4 IDs × ~292 cycles) |
| `restarts` | `segmented` − 3 (orphan, oversized and out-of-order cycles start from idle) |
| `single_frame` | ~603 (600 telemetry + up to 3 faults) |
| `rejected` | 3 (one each: `orphan_consecutive_frame`, `oversized`, `sequence_error`) |
| `dropped invalid CAN frame` | 0 |

---

## 5. Running It Against the Generator

Requires the Raspberry Pi (SocketCAN and `vcan0`). It does not work on Windows. See section 7.

**Terminal 1: the tool first, so no frames are missed.**

```bash
cd ~/workspace/firmware_developer_Deepsea && source venv/bin/activate
python App/src/main.py --iface vcan0 --debug 2> debug.log
```

**Terminal 2: the unmodified challenge generator.**

```bash
cd ~/workspace/firmware_developer_Deepsea
python3 ~/challenge/can_generator/generator.py --iface vcan0 --duration 75 --out ground_truth.jsonl
```

When the generator prints `done`, stop the tool with `Ctrl+C`.

Both `*.log` and `*.jsonl` are git-ignored, so `debug.log` and `ground_truth.jsonl` stay inside the workspace and are never committed.

---

## 6. Reading the Log

```bash
grep segmented debug.log | head                 # reassembled identification strings
grep rejected  debug.log                        # the 3 rejected situations
grep -c restarts debug.log                      # repeated abandonment count
grep -c single_frame debug.log                  # telemetry + fault messages
grep "transport\." debug.log | grep -v restarts # transport events except normal restarts
```

Live, without a file:

```bash
python App/src/main.py --iface vcan0 --debug 2>&1 | grep -E "segmented|rejected"
```

Decode a hex payload:

```bash
python3 -c "print(bytes.fromhex('534e3a504d552d343437312d4120').decode())"
# SN:PMU-4471-A
```

Compare with what the generator says it sent:

```bash
grep diag_complete_sent ground_truth.jsonl | head
grep diag_situation     ground_truth.jsonl        # which ID got which situation
grep run_summary        ground_truth.jsonl        # real_frame_count
```

For each `diag_situation` record, the log should show the matching `rejected` line on that `can_id` (or the `restarts` line for `restart_ff`), followed by a `segmented` message whose decoded payload equals the next `diag_complete_sent` string on that ID.

---

## 7. On Windows

SocketCAN does not exist on Windows, so the tool exits immediately:

```text
... ERROR deepsea: SocketCAN is not available on this platform
```

This is expected (exit code 1). On Windows, verify with the offline tests instead:

```powershell
.\venv\Scripts\python.exe -m pytest -v
```

The automated equivalent of sections 5–6 is the e2e suite, which runs only on the Pi:

```bash
python -m pytest App/test/e2e -v
```
