# Feature 06 — Services and Output

## 1. Objective

Implement the services that maintain application state, publish application events, and track statistics. Integrate those services with two independent output implementations:

1. **Normal mode:** a terminal dashboard for human-readable monitoring.
2. **Grader mode:** machine-readable NDJSON written exclusively to `stdout`.

The output layer must consume application events and state without taking responsibility for CAN communication, transport reassembly, protocol decoding, or domain-specific controller logic.

## 2. Suggested structure

```text
src/
├── services/
│   ├── event_publisher.py
│   ├── application_state.py
│   └── stats_service.py
├── output/
│   ├── dashboard.py
│   └── grader.py
├── models/
│   └── application_event.py
└── config/
    ├── constants.py
    └── settings.py
```

Reuse existing files and interfaces where possible. Do not create duplicate implementations simply to match this example tree.

## 3. ApplicationState

**Responsibility:** maintain the current application state in memory.

The state should support the information required by the challenge, including:

* Latest valid telemetry for each power module.
* Current fault information.
* Latest diagnostic completion information, where applicable.
* Any additional state explicitly required by the challenge contract.

Requirements:

* Provide explicit methods for updating and retrieving state.
* Validate updates before committing them.
* Keep module-specific telemetry associated with the correct module.
* Avoid exposing mutable internal collections directly.
* Do not perform decoding, output formatting, or CAN operations.
* Keep memory bounded.
* Ensure invalid messages do not overwrite the last valid state.

Use the existing protocol models where appropriate. Avoid introducing another representation of the same decoded information without a clear need.

## 4. EventPublisher

**Responsibility:** provide a consistent way for controllers and other application components to publish application events.

The service should accept the established `ApplicationEvent` model and deliver events to registered consumers, including the selected output implementation.

Expected event categories:

* `telemetry`
* `fault`
* `diag_complete`
* `stats`

Requirements:

* Keep event publication independent of output formatting.
* Define a simple registration and publication interface.
* Avoid coupling controllers to the dashboard or grader.
* Ensure an output consumer cannot silently cause an unrelated consumer to stop receiving events.
* Handle consumer failures using an explicit, documented policy.
* Avoid unbounded event queues and uncontrolled background threads.
* Preserve the event's original timestamp and relevant message metadata.

Use synchronous delivery unless the stabilized application design requires asynchronous delivery. Do not introduce a message broker or external dependency for this challenge.

### Event model

`ApplicationEvent` should be the common event representation shared across the application.

It should contain the information required by the existing challenge contract, such as:

* Event type.
* Timestamp, where applicable.
* Event payload or structured data.

Use the exact field names and schema required by the challenge and existing grader expectations. Do not invent a new wire format just to fit the internal architecture.

## 5. StatsService

**Responsibility:** maintain application counters and expose a consistent statistics snapshot.

At minimum, support the statistics required by the challenge, including `frames_processed` and any existing diagnostic or message counters.

### `frames_processed` requirement

Count only frames belonging to the challenge's actual telemetry, fault, and diagnostic identifiers.

Relevant identifiers:

* Telemetry: `0x100–0x103`
* Fault: `0x1F0`
* Diagnostics: `0x6F0–0x6F3`

Ignore noise frames in `0x200–0x2FF` for this counter.

The counter must not be incremented twice for the same frame merely because it passes through multiple layers. Establish one clear counting point in the architecture and document it.

Additional requirements:

* Provide a method to retrieve a snapshot of the counters.
* Keep statistics independent of dashboard rendering.
* Avoid exposing mutable internal counter structures.
* Emit a `stats` event when required by the challenge's existing output contract.
* Ensure the statistics output is deterministic and testable.

Do not change the meaning of an existing counter without verifying the challenge specification.

## 6. Output interface

The output layer consumes application events and, when needed, state or statistics snapshots.

The dashboard and grader are two implementations of the same output responsibility. They must not be mixed together or selected implicitly from inside a controller.

### 6.1 Dashboard

**File:** `src/output/dashboard.py`

Purpose: provide a readable terminal interface for normal interactive execution.

Requirements:

* Display current telemetry, faults, diagnostic completion, and relevant statistics.
* Update its presentation when application events arrive.
* Keep rendering logic separate from business logic.
* Avoid direct CAN access or protocol decoding.
* Keep the display readable when data is missing or has not yet arrived.
* Send diagnostics and errors to `stderr` or the configured logging destination.
* Handle shutdown cleanly.

A continuously refreshed screen is acceptable if it does not interfere with message processing. Do not introduce a heavy UI framework unless it is already part of the project and explicitly allowed.

### 6.2 Grader

**File:** `src/output/grader.py`

Purpose: provide deterministic machine-readable output for automated evaluation.

Required invocation:

```bash
python3 main.py --iface vcan0 --grader
```

Requirements:

* Emit one valid JSON object per line.
* Use newline-delimited JSON (NDJSON).
* Flush `stdout` after every emitted event.
* Do not print banners, tables, progress messages, or debug logs to `stdout`.
* Send diagnostics and error logs to `stderr`.
* Serialize only the event types and fields required by the challenge.
* Preserve the required timestamp semantics, especially diagnostic completion timestamps.
* Avoid non-JSON values in serialized output.
* Produce valid, independently parseable lines.
* Do not transmit CAN frames.

Example of the output shape only; actual fields must match the challenge contract:

```json
{"event":"telemetry","ts_ns":123456789,"data":{}}
{"event":"fault","ts_ns":123456999,"data":{}}
{"event":"diag_complete","ts_ns":123457123,"data":{}}
{"event":"stats","data":{}}
```

The empty `data` objects above are placeholders, not the required final payload schema. Implement the actual fields using the challenge documentation and established decoded models.

Use the Python standard library's `json` module. Do not add a third-party serialization dependency.

## 7. Mode selection and composition

`main.py` is the composition root.

It should:

1. Parse the command-line arguments.
2. Initialize the communication and transport layers.
3. Initialize protocol decoders, routes, controllers, and services.
4. Select the dashboard for normal mode or the grader for `--grader`.
5. Register the chosen output consumer with the event publication service.
6. Start processing.
7. Shut down cleanly when requested or when execution ends.

The application must not instantiate both output modes as active consumers unless there is an explicit requirement to do so.

Normal mode:

```bash
python3 main.py --iface vcan0
```

Grader mode:

```bash
python3 main.py --iface vcan0 --grader
```

In grader mode, **only NDJSON events may be written to `stdout`**. Startup messages, exceptions, warnings, and diagnostic logs must not contaminate that stream.

## 8. Data flow

```text
Communication
     |
     v
Transport
     |
     v
Complete Message
     |
     v
Router
     |
     v
Controller
     |
     +------> ApplicationState
     |
     +------> StatsService
     |
     +------> EventPublisher
                    |
                    v
             Selected Output
               /        \
              v          v
         Dashboard     Grader
         (terminal)   (NDJSON)
```

The router and controller interfaces must remain consistent with the previously implemented features. This diagram describes responsibility and flow, not permission to duplicate decoding or statistics counting across layers.

## 9. Tests

### ApplicationState

* Valid telemetry updates the correct module.
* Invalid data does not overwrite valid state.
* Fault and diagnostic state behave as expected.
* Returned snapshots cannot mutate internal state accidentally.
* State remains bounded over extended processing.

### EventPublisher

* Registered consumers receive published events.
* Events retain their expected fields and timestamps.
* Consumer failures follow the documented policy.
* No consumer is registered multiple times unintentionally.

### StatsService

* Relevant CAN identifiers are counted correctly.
* Noise identifiers are excluded from `frames_processed`.
* The same frame is not counted multiple times due to layer transitions.
* Statistics snapshots are consistent.
* Counter behavior matches the challenge's requirements.

### Dashboard and grader

* Dashboard handles missing data and renders events without decoding them.
* Grader emits valid NDJSON.
* Every emitted line can be parsed independently with `json.loads`.
* Grader flushes output per event.
* `stdout` contains no non-NDJSON content in grader mode.
* Logging and errors go to `stderr`.
* Diagnostic completion timestamps are preserved.
* Both execution modes start and shut down correctly.

Use redirected output or `subprocess` tests to verify the grader's output stream. No physical CAN hardware should be required for these tests.

## 10. Constraints

* Python standard library only.
* No `python-can`, `can-isotp`, `cantools`, or `canmatrix`.
* No Linux `CAN_ISOTP` dependency.
* No CAN transmission.
* No global mutable application state.
* No direct output from controllers.
* No circular dependencies between services, controllers, and output.
* No unbounded queues or unnecessary threading.
* No changes to the required grader event schema without verifying the challenge documentation.

## 11. Definition of done

* [ ] Application state is centralized in `ApplicationState`.
* [ ] Events use the shared `ApplicationEvent` model.
* [ ] Event publication is independent of output formatting.
* [ ] Statistics are consistent and noise frames are excluded.
* [ ] Each frame is counted at one clearly defined point.
* [ ] The dashboard renders application events and state.
* [ ] The grader emits strictly valid NDJSON on `stdout`.
* [ ] Logs and diagnostics do not contaminate grader output.
* [ ] Diagnostic timestamps retain their defined meaning.
* [ ] Unit and integration tests pass.
* [ ] Both normal and grader modes work using the required commands.
* [ ] The implementation remains receive-only.
* [ ] Existing interfaces and challenge requirements remain intact.

---

# Recommended implementation order

1. **BaseController:** define the minimal controller contract using the stabilized interfaces.
2. **Concrete controllers:** implement telemetry, fault, and diagnostic processing.
3. **ApplicationState:** centralize application state and update methods.
4. **StatsService:** establish a single counting point and implement snapshots.
5. **EventPublisher:** connect controllers and output consumers.
6. **Grader:** implement and test strict NDJSON output first, because it has the clearest automated acceptance criteria.
7. **Dashboard:** connect the human-readable terminal presentation.
8. **Integration tests:** validate routing, controller processing, service updates, and both execution modes.
9. **Final regression:** run the challenge's tests and verify that no prohibited dependency or CAN transmission has been introduced.

**Important:** Before implementation, compare the exact event schema, decoded payload fields, and interface signatures against `CHALLENGE.md`, `ADAPTER.md`, and the existing code. These specifications define architecture and responsibilities; the challenge contract remains authoritative for exact field names and output values.
