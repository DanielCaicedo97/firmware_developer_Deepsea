# Progress Tracker

Update this file after every meaningful implementation
change.

## Current Phase

- Feature 01: Communication and Transport (`Context/feature-specs/01-Communication_and_transport.md`). Implemented and offline-tested. **Live `vcan0` verification on the Pi is pending.**

## Current Goal

- Verify Feature 01 live on the Raspberry Pi 5 against the challenge generator, then commit it.

## Completed

- Project specification: overview, architecture, code standards, workflow.
- Feature 01 (offline):
  - `App/src/config/constants.py`: protocol and SocketCAN ABI constants (IDs, PCI masks, 64-byte limit, frame format).
  - `App/src/config/settings.py`: frozen dataclasses `CommunicationConfig`, `TransportConfig` (framing map + max length), `LoggingConfig`, `ApplicationConfig`; `build_framing_map(module_count)`, `build_application_config(...)`.
  - `App/src/models/can_frame.py`: `CANFrame` (11-bit ID, ≤8-byte data, `length` property, optional monotonic `timestamp_ns`), `InvalidFrameError`.
  - `App/src/models/message.py`: `Message` (message_id, source_id, payload, `TransportMetadata`), `FramingMode`.
  - `App/src/communication/interface.py`: generic `CommunicationInterface[UnitT]` (open/receive/close, context manager), `CommunicationError`.
  - `App/src/communication/frame.py`: `decode_can_frame` (struct `=IB3x8s`; rejects EFF/RTR/ERR flags, wrong size, DLC > 8).
  - `App/src/communication/socketcan.py`: `SocketCanInterface`, receive-only (`recv` only). Injectable socket factory, optional `SO_RCVBUF`, timeout returns `None`, invalid frames are counted and dropped.
  - `App/src/transport/transport.py`: `Transport[UnitT]` base (listener registry, `_deliver`), `FrameOutcome`.
  - `App/src/transport/listener.py`: `TransportListener.on_message(message)`.
  - `App/src/transport/reassembler.py`: `SegmentedReassembler` with one fixed `ReassemblyContext` per segmented source, `ReassemblyOutcome`, `ReassemblyResult`.
  - `App/src/transport/can_transport.py`: `CanTransport` (framing map: single-frame passthrough, segmented reassembly, noise ignored).
  - `App/src/main.py`: `--iface` (required), `--debug`; explicit composition; single-threaded receive loop; temporary `LoggingMessageListener` (stderr, debug level).
  - `App/test/`: 71 `unittest` tests, organised by type and then area. Shared doubles are in `helpers.py`.
    - `unit/` (61 tests): `communication/` (raw frame decode, SocketCAN with a fake socket that has no `send`), `transport/` (reassembler: every case in spec §Testing Requirements incl. wraparound, cleanup and a `tracemalloc` bound; CanTransport), `models/` (CANFrame), `config/` (settings and framing map).
    - `integration/communication_transport/` (4 tests): raw bytes → `SocketCanInterface` → `CanTransport` → listener. It covers all four messy situations interleaved with telemetry, fault, noise and an invalid frame, and checks `frames_processed` accounting.
    - `e2e/live_bus/` (6 tests): runs the unmodified challenge generator on `vcan0` and compares against its ground truth. Checks: exact per-ID diagnostic strings in order, `frames_processed == real_frame_count`, single-frame count, all four situations occurred, bounded contexts. Skipped off the Pi.
    - Windows / venv Python 3.13.5: 65 pass, 6 e2e skipped.
  - Static checks: no `send`/`sendto` calls, no banned libraries, no `print`, no unused imports in `App/src/` (excluding `generator.py`) or `App/test/`.
  - Docs synced: architecture-context §11.3–11.5 (message fields, `FrameOutcome`, reassembly rules as implemented), §30; README roadmap and test command.

## In Progress

- None.

## Next Up

1. On the Pi: `python3 --version`, `ip -details link show vcan0`, run `cd App/src && python3 -m unittest discover -s ../test` (the e2e suite runs the generator itself for 20 s and must pass there, not skip). Then run `python3 App/src/main.py --iface vcan0 --debug` with the generator running in another terminal, as a manual check.
2. Commit Feature 01 on `feature/transport_layer`.
3. Next feature candidates: receive buffer (`rx_buffer.py`, architecture §10), kernel `CAN_RAW_FILTER` (README "Filtering Mechanism"), router and protocol decoders, grader output with `frames_processed` from `FrameOutcome`.

## Open Questions

- **Entry point location vs CHALLENGE.md.** The deliverable asks for `main.py` at the repo root, run as `python3 main.py --iface vcan0`. The entry point now lives in `App/src/main.py`. Before delivery, either add a thin root `main.py` shim that delegates to `App/src/main.py`, or confirm the evaluators accept the path.
- **`App/src/generator.py` must leave the repo before delivery.** It contains `sock.send(...)`. CHALLENGE.md: a transmit call *anywhere in the repo* zeroes the whole score (static check). It also duplicates the read-only generator in `~/challenge/`. Remove it or confirm a plan. Not removed yet: awaiting the user's decision.
- Python version on the Pi has not been checked yet. Code targets Python ≥ 3.9 (no `slots=True`, no `match`, `X | Y` only under `from __future__ import annotations`).
- Kernel `CAN_RAW_FILTER` (described in README) was not in Feature 01's scope. Decide whether it belongs to the communication layer (filters injected via `CommunicationConfig`) in a later feature.
- `--grader` is not accepted yet (out of scope for Feature 01). The README Run section already documents it.

## Architecture Decisions

- **Everything lives under `App/` (user decision, 2026-10-08).** `App/src/` is the source root: `main.py` sits next to the packages, and imports are top-level (`from transport.can_transport import ...`). Running `python3 App/src/main.py` puts `App/src` on `sys.path`. Tests live in `App/test/`, are run from `App/src` with `-s ../test`, and import helpers as `from helpers import ...`. `App/test` is deliberately not a package, to avoid clashing with the stdlib `test` package.
- **Two transport files.** `transport.py` is the interface and `can_transport.py` the CAN implementation (architecture §11.1), so a UART/SPI transport can be added next to it.
- **Fixed contexts, created once.** One context per segmented source in the framing map. Each context is reset in place, and its buffer is replaced by a fresh `bytearray` on reset. The context count never changes and each buffer is ≤ `max_message_length`. This gives bounded memory by construction, with no timeout needed.
- **Any First Frame ends the current attempt,** even an invalid one. A sender emitting a new FF has abandoned its old message.
- **FF declared length < 8 is rejected,** because CHALLENGE.md says there is no Single Frame case.
- **`FrameOutcome` returned from `Transport.process`** lets the upper layer do `frames_processed` accounting (anything except `IGNORED`) without the transport owning statistics.
- **Completion `ts_ns` is captured by the upper layer** (spec 01 §9). `Message.metadata.received_at_ns` is only the boundary timestamp of the completing frame.
- **Invalid raw frames are not exceptions to the caller.** `SocketCanInterface.receive()` returns `None` and increments `invalid_frames`. `CommunicationError` is reserved for real I/O failures.
- **Tests are written with stdlib `unittest`; pytest is an optional runner (user decision, 2026-10-08).** Root `pytest.ini` (`testpaths = App/test`, `pythonpath = App/src App/test`) and `requirements-dev.txt` (`pytest==9.1.1`, dev only). Tests never import pytest, so `unittest` still runs everything on the Pi with zero dependencies. Run pytest from the repo root: `testpaths` only applies there.
- **Test layout: type first, then area (user decision, 2026-10-08).** `unit/<area>/`, `integration/<boundary>/`, `e2e/<scenario>/`; each folder is a package so discovery recurses. Run one type with `-s ../test/<type> -t ../test`.
- **The e2e test composes the stack directly** (config → SocketCAN → CanTransport) instead of launching `main.py`, because `main.py` has no machine-readable output yet. Once `--grader` exists, add an e2e scenario that runs `main.py --grader` as a subprocess and checks its NDJSON.
- **The e2e ground-truth file is written to a temporary directory** (outside the workspace) and deleted afterwards. This is documented in the README, as AGENTS.md requires.

## Session Notes

- Local development is on Windows with a project venv at `./venv` (Python 3.13.5, git-ignored). Run tests with `cd App/src && ../../venv/Scripts/python.exe -m unittest discover -s ../test` (one type: add `/unit`, `/integration` or `/e2e` to `-s` plus `-t ../test`; e2e skips on Windows). With pytest, from the repo root: `./venv/Scripts/python.exe -m pytest` (or `... -m pytest App/test/unit`). pytest 9.1.1 is installed in the venv. SocketCAN does not exist on Windows: `App/src/main.py` exits with code 1 and the message "SocketCAN is not available on this platform", which is expected. Live checks must run on the Pi.
