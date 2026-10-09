# Progress Tracker

Update this file after every meaningful implementation
change.

## Current Phase

- Feature 01: Communication and Transport (`Context/feature-specs/01-Communication_and_transport.md`). Implemented and offline-tested. **Live `vcan0` verification on the Pi is pending.**
- Feature 02: Protocol Decoders (`Context/feature-specs/02-Protocol_Decoders.md`). Implemented and offline-tested.
- Feature 03: Hierarchical Message Router (`Context/feature-specs/03-Message_Routing.md`, rewritten 2026-10-08). Implemented and offline-tested. It now lives in `App/src/routes/common/` (moved by Feature 04).
- Feature 04: Architecture refactoring (`Context/feature-specs/04-architecture-specification.md`). Implemented and offline-tested: protocol by domain, `routes/`, `controllers/`, `services/`, `output/`, application events, and `main.py` as the composition root with `--grader`. The application now runs end to end in both modes. **Live `vcan0` verification on the Pi is pending.**
- Feature 05: Controllers (`Context/feature-specs/05-controllers.md`). Implemented and offline-tested. It builds on the Feature 04 controllers and adds validation before state updates, `StatsService` updates, an explicit `ControllerResult`, and rejection (not a crash) of incomplete diagnostics. **Live `vcan0` verification on the Pi is pending.**
- Feature 06: Services and Output (`Context/feature-specs/06-services_and_output.md`). Implemented and offline-tested. It completes the Feature 04 services: a concrete `EventPublisher` with registration and a documented consumer-failure policy, validated `ApplicationState` with snapshots, `StatsService` counter snapshots, the outputs as `EventConsumer`s, and subprocess stream tests. **Live `vcan0` verification on the Pi is pending.**

## Current Goal

- Verify Features 01–06 on the Raspberry Pi 5 (unit tests, the e2e suite, and a manual run of both modes against the generator), then commit them.

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
- Feature 02 (offline):
  - `App/src/config/constants.py`: telemetry layout (`<HHBBH`, scales, temperature offset, status masks), fault layout (offsets, length), identification-text encoding and `SN:`/`FW:`/`#` prefixes.
  - `App/src/models/telemetry.py` `TelemetryResult`, `models/fault.py` `FaultCode` (IntEnum 1–4) + `FaultResult`, `models/diagnostic.py` `DiagnosticResult` (frozen dataclasses).
  - `App/src/protocol/common.py`: `ProtocolDecodeError(ValueError)`, `require_payload_length`, `module_id_from_message_id`.
  - `App/src/protocol/telemetry.py` `decode_telemetry`, `protocol/fault.py` `decode_fault`, `protocol/diagnostic.py` `decode_diagnostic`. Each one is `(Message) -> Result`, raises `ProtocolDecodeError` on invalid input, and has no I/O, state, routing or output. The rules are in architecture-context §18.1.
  - Feature 01 interfaces are unchanged. `helpers.py` gained `complete_message(...)`.
  - Tests: +31 (102 in total). `unit/protocol/` (28: telemetry 10, fault 8, diagnostic 10). They cover valid decoding, module/sequence preservation, result types, bad lengths, bad IDs, unknown codes/modules, non-zero reserved bytes, non-ASCII/control/malformed text (including the generator's decoy and `-BROKEN` texts), and no stdout output. `integration/transport_protocol/` (3): `CanTransport` output → decoders.
  - Windows / venv Python 3.13.5: 96 pass, 6 e2e skipped (unittest and pytest). `compileall` is clean. Static checks: no `print`/`send`, no broad `except`, no banned libraries, no unused imports.
  - Docs synced: architecture-context §18.1 (decoders as implemented), §30 structure.
- Feature 03, Hierarchical Message Router (offline). This replaces the first flat router (`protocol/router.py` and its 15 unit tests), which was deleted when the spec was rewritten.
  - `App/src/router/`:
    - `base_router.py`: `BaseRouter[TargetT]` (per-instance ID → target table, ID validation, all-or-none multi-ID registration, no overwrite), `RouteRegistrationError(ValueError)`.
    - `subrouter.py`: `SubRouter(name, expected_errors)` with `add_route`, `add_routes`, the optional `@route(*ids)` decorator, `dispatch`, `seal`.
    - `root_router.py`: `RootRouter` with `include_router` (indexes the subrouter's IDs, rejects overlaps, seals the subrouter) and `dispatch`.
    - `results.py`: `DispatchStatus` (SUCCESS / ROUTE_NOT_FOUND / HANDLER_NOT_FOUND / HANDLER_FAILED) and frozen `DispatchResult(status, message, router_name, result, error)`.
    - `routes_init.py`: `init_routes(root=None, *_handler=Feature 02 decoders)` builds the `telemetry` (0x100–0x103), `fault` (0x1F0) and `diagnostic` (0x6F0–0x6F3) subrouters with `expected_errors=(ProtocolDecodeError,)`.
    - `__init__.py`: public API.
  - Generic router modules import no decoders; only `routes_init.py` does. There are no new constants: IDs come from `TELEMETRY_BASE_ID`/`FAULT_ID`/`DIAGNOSTIC_BASE_ID`/`MODULE_COUNT`, and ID validation uses `CAN_STANDARD_ID_MASK`. There is no module-level router. Feature 01 and 02 interfaces are unchanged.
  - Tests: +43 (145 in total). They cover all 15 cases in spec 03 §9.
    - `unit/router/test_subrouter.py` (17): registration (single, multi, decorator), duplicate and conflicting batches rejected with nothing overwritten, invalid IDs (negative, > 0x7FF, EFF-flagged, str, float, None, bool) and boundary IDs, non-callable handlers, bad names, independent instances, the right handler gets the original message, SUCCESS result, HANDLER_NOT_FOUND, expected error → HANDLER_FAILED and routing continues, unexpected errors propagate.
    - `unit/router/test_root_router.py` (11): inclusion indexes IDs, overlap rejected all-or-none, double inclusion, empty subrouter and non-subrouter rejected, independent instances, the right subrouter and handler, SUCCESS result, ROUTE_NOT_FOUND, registration after inclusion rejected, HANDLER_NOT_FOUND on a missing subroute.
    - `unit/router/test_routes_init.py` (12): every documented ID registered, a supplied root is used and returned, independent builds, clash with a pre-owned ID, all telemetry/fault/diagnostic IDs reach their decoder, all 256 noise IDs and unknown neighbours reach none, payload untouched, real decoders: valid telemetry, malformed telemetry/fault/diagnostic → HANDLER_FAILED followed by a valid fault, no stdout output.
    - `integration/transport_protocol/test_transport_to_router.py` (3, rewritten): `CanTransport` → `init_routes()` with mixed generator-shaped traffic, an abandoned reassembly, and malformed-then-valid.
  - Windows / venv Python 3.13.5: 139 pass, 6 e2e skipped (unittest and pytest). Static checks: no `print`/`send`, no broad `except`, no FastAPI/Starlette or banned CAN libraries, no unused imports, every public function and class has a docstring.
  - Docs synced: architecture-context §17.1 (rewritten for the hierarchy), §18.1, §30 structure; README project tree.

- Feature 04, Architecture refactoring (offline). Applied in five steps, with the full suite green after each one. Details are in architecture-context §11.3–11.4, §17.1, §18.1, §22.1 and §30.
  1. **Protocol by domain.** `protocol/common/__init__.py` (was `protocol/common.py`). `protocol/{telemetry,fault,diagnostic}/decoder.py` plus `models.py`; the result models moved from `models/{telemetry,fault,diagnostic}.py`, which were deleted. Each domain `__init__` re-exports its decoder and models. The decoder logic is unchanged.
  2. **`router/` → `routes/`.** `routes/common/router.py` (merged `base_router.py`, `subrouter.py`, `root_router.py`; the behavior is unchanged) and `routes/common/results.py`. `unit/router/` tests moved to `unit/routes/`.
  3. **Controllers, services, routes.**
     * `models/application_event.py`: `EventType`, `TelemetryEvent`, `FaultEvent`, `DiagnosticCompleteEvent(diagnostic, completed_at_ns)`, `StatsEvent`, and the `ApplicationEvent` Union.
     * `services/`: `EventPublisher` (ABC), `ApplicationState` (fixed per-module slots plus a bounded fault deque), `StatsService` (`record_frame`, `snapshot`, `poll(now_ns)`).
     * `controllers/`: `BaseController[ResultT]` (`handle(result, message)`, with state and publisher injected); `Telemetry`/`Fault`/`DiagnosticController`; `ApplicationController` (`TransportListener`; `on_message` → injected `dispatch`; `on_frame` counts non-`IGNORED` outcomes; `report_stats_if_due`, `run(poll_frame, keep_running)`, `shutdown`).
     * `routes/common/controller_route.py`: `ControllerRoute(decoder, controller)`, `DECODER_ERRORS`, `per_module_ids`. `routes/{telemetry,fault,diagnostic}/routes.py`: `build_<domain>_router(controller, decoder=...)`. `routes_init.init_routes(telemetry_controller, fault_controller, diagnostic_controller, root=None)`.
     * Transport: `TransportMetadata.completed_at_ns`, stamped by `CanTransport` (injectable `clock`) when a message completes. `Transport.receive_from(communication)` consumes one frame.
  4. **Output.** `output/grader.py` `GraderOutput` (ADAPTER.md NDJSON, one flushed line per event); `output/dashboard.py` `Dashboard` (in place with ANSI, throttled, renders from `ApplicationState`).
  5. **Composition.** `main.py`: `--grader`; `build_output`, `build_application`, `run` (SIGTERM → clean stop, final stats and socket close in `finally`). `config/settings.py`: `OutputMode`, `OutputConfig`. `config/constants.py`: stats/dashboard/fault-history defaults and `NANOSECONDS_PER_SECOND`. `LoggingMessageListener` was removed.
  - `.gitignore`: the unanchored `output/` rule also ignored `App/src/output/`, which would have dropped the package from the repo. It is now `/output/`.
  - Tests: 185 in unittest (179 in pytest plus 28 subtests), with 6 e2e skipped on Windows. New suites: `unit/services/` (state 6, stats 4), `unit/controllers/` (domain 5, application 5), `unit/output/` (grader 5 with exact ADAPTER.md lines, dashboard 5), `unit/transport/` (+4: completion timestamp, `receive_from`), `unit/config/` (+2), `unit/routes/test_routes_init.py` (rewritten for controllers: domain routers, decoder → controller, malformed input never reaches a controller), and `integration/application/` (4: raw bytes → `main.build_application` + `main.run` → NDJSON and dashboard, with all four messy situations, repeated abandonment, noise, exact final `frames_processed`, and only the recovery strings reported).
  - Static checks: every module imports on its own (no cycles); the spec §6 dependency rules were checked with grep; no `print`/`send`/broad `except`/banned libraries; an AST check found no unused imports, no public class or function without a docstring, and no function over 30 lines.

- Feature 05, Controllers (offline, 2026-10-08). Details are in architecture-context §17.1 and §22.1.
  - `controllers/results.py` (new): `ControllerStatus` (PROCESSED / REJECTED) and frozen `ControllerResult(status, decoded, event=None, reason=None)` with `succeeded`.
  - `BaseController[ResultT]`: the constructor is now `(state, stats, publisher)`, plus `ClassVar event_type` (the stats domain). The abstract `handle(result, message) -> ControllerResult` is the only contract method. Shared helpers: `_module_known`, `_reject` (counts rejected, touches nothing else) and `_complete` (publishes, then counts processed). There is no type-based branching.
  - The concrete controllers validate before any state update:
    - Telemetry: known module, and the CAN ID is `0x100 + module`.
    - Fault: known module and a `FaultCode` member.
    - Diagnostic: `completed_at_ns` present (otherwise the message is incomplete and is now rejected, where Feature 04 raised `ValueError`), known module, `result.message_id == message.message_id`, non-empty text.
    - A valid result goes to `ApplicationState`, then the publisher, then stats. Service failures propagate and leave nothing published or counted, so they are not silently swallowed.
  - `StatsService`: fixed per-domain processed/rejected counters (`record_processed`, `record_rejected`, `processed`, `rejected`). The ADAPTER.md `stats` line is unchanged (`frames_processed` only).
  - `ControllerRoute` returns the `ControllerResult` (`DispatchResult.result.decoded` is the decoder output). `ApplicationController.on_message` logs controller rejections at warning level on stderr.
  - `main.build_application` creates `StatsService` first and injects it into the three controllers.
  - Tests: 204 in unittest (198 + 28 subtests in pytest), with 6 e2e skipped on Windows. `unit/controllers/test_domain_controllers.py` was rewritten (21 tests) to cover every spec §9 item for each controller:
    - valid processing, state updated through `ApplicationState` (autospec mock), the event published, stats counted;
    - invalid results keep the last valid state;
    - state/publisher failures propagate with no event or count;
    - `ts_ns` is preserved even with the clocks patched;
    - invalid-then-valid is processed;
    - no stdout output, and an AST check that controllers import no socket/sys/communication/output/routes_init and call no `print`/`send`/`write`.
  - Other test changes: `unit/services/test_stats_service.py` +2 and `unit/controllers/test_application_controller.py` +1 (rejection logged, not raised). `RecordingController` in `helpers.py` now returns a `ControllerResult`. Route and integration tests read `.result.decoded`.
  - Static checks: every module imports on its own; no `print`/`send`/broad `except`; no unused imports; every public class and function has a docstring; no function over 30 lines; no line over 120 characters.

- Feature 06, Services and Output (offline, 2026-10-08). Details are in architecture-context §22.1. Most of spec 06 already existed from Features 04/05; these are the gaps that were closed:
  - `services/event_publisher.py`:
    - `EventPublisher` is now a concrete class (it was an ABC that the outputs implemented directly). `register(consumer)` rejects duplicates (`ValueError`) and non-consumers (`TypeError`); `consumers` returns a tuple. `publish(event)` delivers the same event object synchronously, in registration order.
    - New `EventConsumer` ABC (`on_event`) and `EventDeliveryError(event, failures)`.
    - **Failure policy:** a consumer that raises is logged on stderr; the other consumers still get the event; then `EventDeliveryError` is raised (first cause chained). `KeyboardInterrupt` is not caught.
    - Controllers are unchanged: they still call `publish`.
  - `services/application_state.py`:
    - Per-module `latest_fault`.
    - The latest diagnostic completion is kept with its timestamp: `update_identification(result, completed_at_ns)` stores a `DiagnosticCompleteEvent` (an existing model, not a new representation), read with `diagnostic_completion(module)`. `identification(module)` is kept.
    - Validation before commit: result type, `int` module in range, `FaultCode`, ID `0x6F0 + module`, non-empty text, non-negative `int` timestamp.
    - `snapshot()` returns a frozen `StateSnapshot` of tuples.
    - `DiagnosticController` passes `completed_at_ns`.
  - `services/stats_service.py`:
    - `snapshot()` now returns a frozen `StatsSnapshot` (`frames_processed` plus read-only per-domain processed/rejected mappings).
    - New `stats_event()` builds the ADAPTER.md `StatsEvent`; `poll()` and `ApplicationController.shutdown()` use it.
    - The single counting point (`ApplicationController.on_frame`, outcome ≠ `IGNORED`) is unchanged and is now documented in the class docstring and architecture §22.1.
  - Output:
    - `GraderOutput` and `Dashboard` implement `EventConsumer.on_event` (was `publish`).
    - The grader serializes through `to_json_line` with `allow_nan=False`: NaN/infinity raise and nothing is written for them.
    - The dashboard renders from one `ApplicationState.snapshot()` per redraw; `format_dashboard(snapshot, frames_processed)`.
  - `main.py`:
    - `build_output` returns an `EventConsumer`. `build_application` creates one `EventPublisher` and registers only the selected mode's consumer.
    - `run` treats `EventDeliveryError` like `CommunicationError` (logged, exit 1).
    - The new `stop()` publishes the final stats and always closes the socket, even if the output is broken.
  - Tests: 245 in unittest (239 + 49 subtests in pytest), with 6 e2e skipped on Windows.
    - `unit/services/test_event_publisher.py` (new, 11): delivery to all consumers in order, the same object and `ts_ns` preserved, no-op without consumers, duplicate and non-consumer registration rejected, and the failure policy (others still receive, error raised after delivery, logged, every failure reported, later events still delivered, `KeyboardInterrupt` not caught).
    - `unit/services/test_application_state.py` (rewritten, 14): correct module, current fault, completion timestamp, invalid telemetry/fault/identification keep the last valid state, snapshots are immutable and detached, and memory stays bounded over 20 000 updates (`tracemalloc`).
    - `unit/services/test_stats_service.py` (+8): snapshots are immutable, detached and deterministic. `FrameCountingPointTest` runs the real transport, router and controllers: every relevant ID counts, all 256 noise IDs don't, a segmented message counts per frame and not per layer, and abandoned or malformed frames on real IDs still count.
    - `unit/output/` (+6): dashboard partial data, renders the stored state, and an AST check that it does not decode; grader lines parse independently, `ts_ns` is unchanged, NaN/infinity are refused without writing.
    - `integration/application/test_output_streams.py` (new, 7, `subprocess`): `--grader` stdout is only NDJSON with every line parseable and the final stats correct, and debug logs go only to stderr. Normal mode draws the dashboard and logs go to stderr. Running the real `main.py --iface deepsea-missing0 --grader` exits 1 with an empty stdout.
    - `test_composed_application.py` (+1): a broken output gives exit 1, the socket is still closed, and the failure is logged.
  - Static checks: every module imports on its own; no `print`/`send`/banned libraries; no unused imports; every public class and function has a docstring; no function over 30 lines; no line over 120 characters. The only broad `except` is the publisher's documented isolation boundary, which re-raises.

## In Progress

- None.

## Next Up

1. On the Pi: `python3 --version`, `ip -details link show vcan0`, then `cd App/src && python3 -m unittest discover -s ../test` (the e2e suite runs the generator itself for 20 s and must pass there, not skip).
2. Manual live check of both modes with the generator running in another terminal: `python3 App/src/main.py --iface vcan0` (the dashboard updates in place) and `python3 App/src/main.py --iface vcan0 --grader > out.ndjson` (every line is valid JSON, stats arrive about every 1 s, the final stats line appears after Ctrl+C or SIGTERM).
3. Add an e2e scenario that runs `main.py --grader` as a subprocess against the generator and compares its NDJSON with the ground truth (telemetry values and freshness, `diag_complete` after each situation, final `frames_processed`). This is now possible because `--grader` exists.
4. Commit Features 01–06.
5. Remaining candidates: receive buffer (`rx_buffer.py`, architecture §10); kernel `CAN_RAW_FILTER` (README "Filtering Mechanism"); a root `main.py` shim for delivery (see Open Questions).

## Open Questions

- **Spec 03 refers to an "existing C++ `RootRouter`/`SubRouter` design" that is not in this repository.** The Python router follows the spec's own description (§4–§6). If that C++ code exists elsewhere and has semantics the spec doesn't state (for example prefix or range matching, or extra result codes), share it so the implementation can be aligned.

- **Identification-string strictness (Feature 02).** CHALLENGE.md does not formally specify the text format. The decoder accepts only `SN:<x> FW:<y>[ #<digits>]` in printable ASCII, which matches every string the generator sends and the CHALLENGE.md example. Any other well-reassembled text would be rejected, so no `diag_complete` would be emitted for it. If evaluators may send other formats, relax the decoder to accept any printable ASCII text with SN/FW fields optional.

- **Entry point location vs CHALLENGE.md.** The deliverable asks for `main.py` at the repo root, run as `python3 main.py --iface vcan0`. The entry point now lives in `App/src/main.py`. Before delivery, either add a thin root `main.py` shim that delegates to `App/src/main.py`, or confirm the evaluators accept the path.
- **`App/src/generator.py` must leave the repo before delivery.** It contains `sock.send(...)`. CHALLENGE.md: a transmit call *anywhere in the repo* zeroes the whole score (static check). It also duplicates the read-only generator in `~/challenge/`. Remove it or confirm a plan. Not removed yet: awaiting the user's decision.
- Python version on the Pi has not been checked yet. Code targets Python ≥ 3.9 (no `slots=True`, no `match`, `X | Y` only under `from __future__ import annotations`).
- Kernel `CAN_RAW_FILTER` (described in README) was not in Feature 01's scope. Decide whether it belongs to the communication layer (filters injected via `CommunicationConfig`) in a later feature.

## Architecture Decisions

- **Feature 06 choices:**
  - **The grader schema is ADAPTER.md's, not spec 06's example.** Spec 06 §6.2 shows `{"event": ..., "ts_ns": ..., "data": {...}}`, but labels it "output shape only" and defers to the challenge contract. ADAPTER.md requires flat objects with a `type` field, so the existing NDJSON lines are unchanged.
  - **Consumer failures: log, keep delivering, then raise.** Swallowing errors would keep a grader with a closed stdout looping silently. Raising on the first failure would stop the other consumers. Collect-and-raise satisfies both requirements in spec 06 §4. In `main.run` this ends the process with exit 1, but the socket is still closed.
  - **Duplicate registration is an error,** unlike `Transport.add_listener`, which ignores duplicates. Spec 06 asks that no consumer be registered twice unintentionally, and an exception makes that visible.
  - **Diagnostic completion is stored as `DiagnosticCompleteEvent`.** It is the existing model that pairs a `DiagnosticResult` with `completed_at_ns`, so no new representation was introduced (spec 06 §3).
  - **No dashboard `close()` hook.** The final stats event published in `stop()` already redraws the final state, and the in-place drawing leaves the cursor below the dashboard, so shutdown needs nothing more.

- **Feature 05 choices:**
  - **Spec 05 §6 vs §8.** §6 lists "select the appropriate output implementation" under `ApplicationController`, but §8 forbids controllers from importing the terminal dashboard or grader serializer. Composing controllers there would also reverse the Routes → Controllers direction. Output selection and wiring therefore stay in `main.py` (`build_output`/`build_application`, the Feature 04 composition root). `ApplicationController` keeps lifecycle coordination (`run`, `report_stats_if_due`, `shutdown`) over its injected dependencies.
  - **Validation failures are results; service failures are exceptions.** This follows the established convention (`DispatchResult` for expected bus problems, propagation for programming errors). No new exception hierarchy was added.
  - **Domain stats are not in the grader output.** ADAPTER.md's `stats` event only defines `frames_processed`, so the per-domain counters stay internal and the NDJSON contract is unchanged.

- **Everything lives under `App/` (user decision, 2026-10-08).** `App/src/` is the source root: `main.py` sits next to the packages, and imports are top-level (`from transport.can_transport import ...`). Running `python3 App/src/main.py` puts `App/src` on `sys.path`. Tests live in `App/test/`, are run from `App/src` with `-s ../test`, and import helpers as `from helpers import ...`. `App/test` is deliberately not a package, to avoid clashing with the stdlib `test` package.
- **Hierarchical router, now in `App/src/routes/common/` (Feature 03, moved by Feature 04).** The first flat `protocol/router.py` was deleted. The details are in architecture-context §17.1. Choices that the spec leaves open:
  - **Not a `TransportListener`.** `on_message` returns `None`, but dispatch has to return a `DispatchResult`. `ApplicationController` is the listener and calls `root.dispatch()`.
  - **Expected errors are configured per subrouter (`expected_errors`), not hard-coded.** This keeps the generic classes free of decoder imports (spec §7). `routes_init` passes `(ProtocolDecodeError,)`.
  - **The root indexes IDs at inclusion, then seals the subrouter.** Each lookup is a single dict hit, and overlaps are rejected up front. Sealing turns a late registration, which would otherwise be silently unreachable, into an error. As a consequence, `HANDLER_NOT_FOUND` can only come from dispatching a subrouter directly, and the root never returns it. Both statuses are kept, as spec §6 asks.
  - **Noise and unknown IDs give the same `ROUTE_NOT_FOUND`.** `frames_processed` is already counted from the transport's `FrameOutcome`, so the router does not need to tell noise apart.
- **Two transport files.** `transport.py` is the interface and `can_transport.py` the CAN implementation (architecture §11.1), so a UART/SPI transport can be added next to it.
- **Fixed contexts, created once.** One context per segmented source in the framing map. Each context is reset in place, and its buffer is replaced by a fresh `bytearray` on reset. The context count never changes and each buffer is ≤ `max_message_length`. This gives bounded memory by construction, with no timeout needed.
- **Any First Frame ends the current attempt,** even an invalid one. A sender emitting a new FF has abandoned its old message.
- **FF declared length < 8 is rejected,** because CHALLENGE.md says there is no Single Frame case.
- **`FrameOutcome` returned from `Transport.process`** lets the upper layer do `frames_processed` accounting (anything except `IGNORED`) without the transport owning statistics.
- **Completion `ts_ns` is captured by the transport (Feature 04, superseding spec 01 §9).** Spec 04 §5.2/§8 says it is captured "when reassembly completes and preserved through every subsequent layer". `CanTransport` stamps `TransportMetadata.completed_at_ns` with its injectable clock as it builds the completed message. `DiagnosticController` copies it into the event and the grader prints it. Nothing re-reads the clock later. `received_at_ns` is still the boundary timestamp of the completing frame.
- **Feature 04 design choices (spec 04 leaves them open):**
  - **Decoding happens in the route, not the controller.** `ControllerRoute(decoder, controller)` decodes and hands the structured result to `controller.handle(result, message)`. Controllers never touch payload bytes (spec §5.5), and routes contain no decoding logic of their own (§5.4). A decode error never reaches a controller.
  - **`ApplicationController` is not a `BaseController`.** It handles messages and frame outcomes, not decoded results (§5.5: inherit only when the contract is genuinely shared). It gets `root.dispatch` as a callable and frame polling as `functools.partial(transport.receive_from, communication)`, so it imports neither the communication layer nor any concrete route configuration.
  - **Output adapters are the `EventPublisher`.** Only one output is active per mode, so no event bus or fan-out was added. The dashboard renders from `ApplicationState` (the single owner of the latest values) on events; the grader serializes each event.
  - **Stats cadence.** Every 1 s (`DEFAULT_STATS_INTERVAL_S`), checked after every receive, which times out every 0.5 s. The first report comes on the first iteration and the last one at shutdown. Dashboard redraws are throttled to 0.2 s, except on stats events.
  - **SIGTERM** sets a flag that stops the loop after the current receive (≤ 0.5 s), so the final stats line is written even when the grader terminates the process instead of sending Ctrl+C.
  - **Structure deviations from spec 04 §4** (`App/src/` root, `can_transport.py`, `models/can_frame.py`, `routes/common/controller_route.py`, type-first test layout) are listed with their reasons in architecture-context §30.
- **Invalid raw frames are not exceptions to the caller.** `SocketCanInterface.receive()` returns `None` and increments `invalid_frames`. `CommunicationError` is reserved for real I/O failures.
- **Tests are written with stdlib `unittest`; pytest is an optional runner (user decision, 2026-10-08).** Root `pytest.ini` (`testpaths = App/test`, `pythonpath = App/src App/test`) and `requirements-dev.txt` (`pytest==9.1.1`, dev only). Tests never import pytest, so `unittest` still runs everything on the Pi with zero dependencies. Run pytest from the repo root: `testpaths` only applies there.
- **Test layout: type first, then area (user decision, 2026-10-08).** `unit/<area>/`, `integration/<boundary>/`, `e2e/<scenario>/`; each folder is a package so discovery recurses. Run one type with `-s ../test/<type> -t ../test`.
- **The e2e test composes the stack directly** (config → SocketCAN → CanTransport). It was written before `--grader` existed. A `main.py --grader` subprocess scenario is in Next Up.
- **The e2e ground-truth file is written to a temporary directory** (outside the workspace) and deleted afterwards. This is documented in the README, as AGENTS.md requires.

## Session Notes

- Local development is on Windows with a project venv at `./venv` (Python 3.13.5, git-ignored). Run tests with `cd App/src && ../../venv/Scripts/python.exe -m unittest discover -s ../test` (one type: add `/unit`, `/integration` or `/e2e` to `-s` plus `-t ../test`; e2e skips on Windows). With pytest, from the repo root: `./venv/Scripts/python.exe -m pytest` (or `... -m pytest App/test/unit`). pytest 9.1.1 is installed in the venv. SocketCAN does not exist on Windows: `App/src/main.py` exits with code 1 and the message "SocketCAN is not available on this platform", which is expected. Live checks must run on the Pi.
- 2026-10-08 (Feature 04): while files were being moved, the editor rewrote test imports to `from test.helpers ...` / `from test.unit.router ...`. That breaks discovery, because `App/test` is not a package. They were reverted to `from helpers ...`. If the IDE offers to "update imports" after a move, decline it.
