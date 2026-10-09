# Feature 02 — Protocol Decoders

Read `AGENTS.md` before starting.

Read the following project documentation before implementing this feature:

* `docs/PROJECT_OVERVIEW.md`
* `docs/CODE_STANDARDS.md`
* `docs/architecture-context.md`
* `01-Communication_and_transport.md`
* `CHALLENGE.md`
* `ADAPTER.md`

Inspect the existing communication, transport, and model implementations before making changes. Reuse existing interfaces and data structures whenever possible.

## Goal

Implement independent protocol decoders for telemetry, fault, and diagnostic messages.

Each decoder must accept a complete message from the transport layer, validate its application payload, and return a structured result.

The decoders must remain independent of SocketCAN, transport reassembly, message routing, terminal output, and grader output.

## Constraints

* Use Python 3 and the standard library only.
* Do not add external dependencies.
* Do not use `python-can`, `can-isotp`, `cantools`, `canmatrix`, Linux `CAN_ISOTP`, or any other CAN protocol/decoding library.
* Do not implement SocketCAN communication or transport reassembly in this feature.
* Do not implement the message router in this feature.
* Do not implement the application controller or output services.
* Do not print decoded messages or emit Grader NDJSON.
* Do not introduce global Singletons or unnecessary abstractions.
* Use the challenge documentation and supplied generator as the source of truth for payload layouts, field encodings, and expected values.
* Do not invent field offsets, units, scaling factors, or validation rules that are not documented.

## Technical Requirements

### 1. Reuse existing message models

Inspect the complete-message model produced by Feature 01.

Each decoder must consume the existing complete-message representation or its payload through a clearly defined interface.

Do not duplicate the CAN frame or complete-message models.

If required information is missing from the existing model, make the smallest justified change and keep the transport/protocol boundary explicit.

### 2. Telemetry decoder

Implement a dedicated telemetry decoder.

The decoder must:

* Accept a complete telemetry message.
* Validate the payload length and structure according to the challenge specification.
* Decode all required telemetry fields using the documented encoding.
* Preserve the module identity and sequence information required by the evaluator.
* Return a structured telemetry result.
* Reject malformed payloads safely.

The challenge uses telemetry identifiers `0x100–0x103`.

Do not hard-code these identifiers in multiple places. Reuse the project's centralized protocol constants where appropriate.

The decoder must not update application state, print output, or emit grader events.

### 3. Fault decoder

Implement a dedicated fault decoder.

The decoder must:

* Accept a complete fault message.
* Validate the payload according to the documented fault format.
* Decode the required fault information.
* Return a structured fault result.
* Reject malformed payloads safely.

The documented fault identifier is `0x1F0`.

Use the exact field layout and expected semantics defined by the challenge materials. Do not assume a payload format that has not been verified.

The decoder must not print fault messages or emit application events directly.

### 4. Diagnostic decoder

Implement a dedicated diagnostic decoder.

The decoder receives a complete, reassembled diagnostic message from Feature 01.

The decoder must:

* Accept the reconstructed diagnostic payload.
* Validate the payload against the documented format.
* Decode the required diagnostic fields.
* Return a structured diagnostic result.
* Handle invalid or unsupported payloads safely.

The challenge uses diagnostic identifiers `0x6F0–0x6F3`.

The supplied generator produces diagnostic text containing information such as serial number, firmware version, and a counter. Follow the exact format defined by the challenge materials.

Do not implement:

* First Frame or Consecutive Frame processing.
* Transport sequence-number validation.
* Message reassembly.
* Reassembly context management.
* Transport completion timestamps.
* Grader `diag_complete` event generation.

These responsibilities belong to other layers.

### 5. Structured results

Define or reuse typed models for decoded results:

* `TelemetryResult`
* `FaultResult`
* `DiagnosticResult`

Use the existing naming conventions if equivalent models already exist.

Models must contain only fields supported by the documented protocol and required by the application.

Use appropriate Python types and meaningful field names. Keep protocol results separate from transport buffers, dashboard state, logging, and grader serialization.

### 6. Validation and error handling

Each decoder must distinguish successful decoding from invalid payloads.

Handle expected invalid input, including:

* Incorrect payload length.
* Missing required fields.
* Invalid field encoding.
* Malformed diagnostic text.
* Unsupported payload formats.

Follow a consistent error-handling convention across the decoders. Reuse an existing project convention if one has already been established.

Invalid payloads must not terminate the application's receive loop.

Do not silently swallow unexpected programming errors with broad exception handling such as:

```python
except Exception:
    pass
```

Do not return a successful result when decoding has failed.

### 7. Separation of responsibilities

Keep each decoder focused on one message type.

The decoders must not:

* Classify or route messages between handlers.
* Open or read CAN sockets.
* Manage transport state.
* Update dashboard state.
* Maintain application statistics.
* Print directly to stdout.
* Serialize grader events.

The future message router will select the appropriate decoder, and the application controller will consume successful decoding results.

### 8. Configuration and constants

Keep protocol identifiers and documented protocol constants centralized in the existing configuration module.

Avoid duplicating constants across decoders.

Do not introduce runtime configuration options unless they are required by the existing architecture or challenge.

## Expected Project Structure

The relevant structure should be approximately:

```text
src/
├── protocol/
│   ├── __init__.py
│   ├── telemetry.py
│   ├── fault.py
│   └── diagnostic.py
├── models/
│   ├── ...
│   ├── telemetry.py
│   ├── fault.py
│   └── diagnostic.py
└── config/
    └── ...
```

Adapt this structure to the existing repository. Do not create duplicate models or files when an equivalent implementation already exists.

## Testing Requirements

Add unit tests using Python's standard library test framework.

Test each decoder independently using constructed complete-message objects and payloads grounded in the challenge specification or supplied generator.

At minimum, test:

* Valid telemetry payload decoding.
* Valid fault payload decoding.
* Valid diagnostic payload decoding.
* Correct preservation of module identity and required sequence information.
* Invalid payload lengths.
* Malformed or unsupported payloads.
* Invalid diagnostic text.
* Correct structured result types.
* Failed decoding does not produce a successful result.
* Decoder execution does not print directly to stdout.

Do not require a running CAN interface to execute decoder unit tests.

Do not invent test payload layouts or expected values. Derive them from the challenge documentation and generator.

## Check when done

### Implementation

* Telemetry decoder is implemented and independently testable.
* Fault decoder is implemented and independently testable.
* Diagnostic decoder is implemented and independently testable.
* Structured result models are defined or reused.
* Protocol constants are centralized.
* Existing Feature 01 interfaces remain compatible.

### Architecture

* Decoders do not access SocketCAN.
* Decoders do not perform transport reassembly.
* No message router is implemented in this feature.
* No application controller or output service is implemented.
* No prohibited library or external dependency is introduced.

### Validation

* Valid payloads decode according to the documented format.
* Invalid payloads are handled safely.
* Required module and sequence information is preserved.
* No undocumented protocol assumptions have been introduced.

### Code quality

* Unit tests cover all three decoders.
* Python standard library only.
* Clear type hints and focused functions are used.
* No broad exception swallowing.
* No direct stdout output or grader serialization in protocol code.

### Final verification

* Run the relevant unit tests.
* Run available syntax checks or static checks.
* Verify compatibility with Feature 01.
* Report completed requirements and any remaining gaps.

Do not mark the feature complete if required tests fail or any architectural constraint remains unsatisfied.
