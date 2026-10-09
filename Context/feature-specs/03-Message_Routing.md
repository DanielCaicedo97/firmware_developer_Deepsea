# Feature 03 — Message Routing

## 1. Before starting

**Always read `AGENTS.md` before starting.**

Review the following documents:

* `docs/PROJECT_OVERVIEW.md`
* `docs/CODE_STANDARDS.md`
* `docs/architecture-context.md`
* `01-Communication_and_transport.md`
* `02-Protocol_Decoders.md`
* `CHALLENGE.md`
* `ADAPTER.md`

Inspect the existing implementation before creating or modifying files. Reuse existing message models, protocol decoders, and constants.

## 2. Goal

Implement a modular and extensible message routing system that dispatches complete messages to the appropriate protocol handlers based on their CAN identifiers.

The router must separate route registration, message dispatch, and protocol decoding. New message handlers must be registerable without modifying the core routing algorithm.

## 3. Constraints

* Use Python 3 and the standard library only.
* Do not introduce external dependencies.
* Do not use prohibited CAN or protocol libraries, including `python-can`, `can-isotp`, `cantools`, or `canmatrix`.
* Do not use Linux `CAN_ISOTP`.
* Never transmit CAN frames.
* Do not open CAN sockets or receive raw frames inside the router package.
* Do not implement frame reassembly or protocol payload decoding in the router.
* Do not implement the application controller, dashboard, grader output, or statistics reporting in this feature.
* Do not introduce mutable global routing state or hidden singleton instances.
* Do not invent CAN identifiers or payload formats.

## 4. Technical requirements

### 4.1. Router implementation

Create a generic router responsible for registering message handlers and dispatching complete messages.

The implementation must provide:

* A central router that receives complete messages and selects the appropriate subrouter.
* Subrouters that group handlers by message category.
* A registration mechanism that associates one or more CAN identifiers with a handler.
* A dispatch mechanism that invokes the matching handler and returns its result.
* Explicit routing outcomes for successful dispatch and unsuccessful routing.

Keep the API small, explicit, and easy to test. Avoid unnecessary inheritance, abstractions, or duplicated functionality.

### 4.2. Route registration

Implement an explicit registration interface that allows handlers to be associated with specific CAN identifiers.

The registration mechanism may support decorator-based registration if it simplifies the API, but direct registration must remain possible when useful.

The implementation must:

* Support registering one handler for multiple CAN identifiers.
* Reject invalid CAN identifiers.
* Reject non-callable handlers.
* Reject duplicate or conflicting registrations instead of silently replacing handlers.
* Keep registration state isolated between router instances.

Registering a new message handler must not require modifying the core dispatch algorithm.

### 4.3. Message dispatch

When a complete message is received, the router must:

1. Read the CAN identifier from the existing message model.
2. Identify the registered handler.
3. Dispatch the original complete message to that handler.
4. Return the handler's structured result.
5. Handle unknown or unsupported identifiers according to a documented policy.

Routing decisions must be based on the CAN identifier, not payload inspection.

The router must not interpret telemetry fields, fault codes, diagnostic text, or other protocol-specific payload contents.

### 4.4. Required message routes

Register handlers for the identifiers documented in the challenge:

| CAN identifier | Message type | Handler            |
| -------------- | ------------ | ------------------ |
| `0x100–0x103`  | Telemetry    | Telemetry decoder  |
| `0x1F0`        | Fault        | Fault decoder      |
| `0x6F0–0x6F3`  | Diagnostics  | Diagnostic decoder |

Use the existing protocol decoders from Feature 02 and reuse centralized protocol constants.

Diagnostic messages must be dispatched only after the transport layer has completed their reassembly.

Noise identifiers in `0x200–0x2FF` and other unsupported identifiers must not reach protocol decoders.

### 4.5. Subrouter responsibilities

Each subrouter must group related handlers and provide a consistent registration and dispatch interface.

Subrouters must not:

* Create or manage CAN sockets.
* Receive raw CAN frames.
* Reassemble multi-frame messages.
* Decode protocol payloads themselves.
* Generate terminal output or grader events.
* Maintain duplicate application state.

The central router must remain independent of individual protocol implementations. Concrete handler registration belongs in the route initialization layer.

### 4.6. Dispatch results and error handling

Define a structured dispatch result using existing project models and conventions where possible.

The result must distinguish between:

* Successful dispatch.
* Unknown or unsupported routes.
* Handler or decoding failures, where supported by the existing decoder contract.

Document how unknown identifiers and expected decoding failures are handled. They must not terminate the main message-processing loop.

Reject registration errors explicitly. Avoid broad exception handling that hides unexpected programming errors.

The router must not print messages, write logs directly to the dashboard, or emit grader NDJSON events.

### 4.7. Route initialization

Implement a dedicated route initialization module that configures the application's handlers.

It must:

1. Create or receive the router instances.
2. Register telemetry, fault, and diagnostic handlers.
3. Associate the documented CAN identifiers with their corresponding handlers.
4. Return the configured central router to the application entry point.

Keep the generic routing implementation separate from challenge-specific route configuration. Use explicit dependency injection rather than global mutable instances.

## 5. Expected project structure

Adapt this structure to the existing repository and avoid duplicating existing files.

```
src/
├── router/
│   ├── __init__.py
│   ├── router.py
│   └── routes_init.py
├── protocol/
│   ├── telemetry.py
│   ├── fault.py
│   └── diagnostic.py
├── models/
└── config/
```

Responsibilities:

* `router.py`: generic routing, handler registration, subrouter management, and dispatch results, unless existing project conventions justify a small additional module.
* `routes_init.py`: registration and composition of challenge-specific handlers.
* `protocol/`: protocol-specific decoding.
* `models/`: shared message and result models.
* `config/`: centralized identifiers and settings.

## 6. Testing requirements

Use `unittest` and other Python standard-library testing facilities.

Add tests covering:

1. A registered identifier invokes the correct handler.
2. The handler receives the original complete message.
3. The dispatch result preserves the handler's result.
4. All telemetry identifiers route to the telemetry decoder.
5. The fault identifier routes to the fault decoder.
6. All diagnostic identifiers route to the diagnostic decoder.
7. Noise and unknown identifiers never reach protocol decoders.
8. Duplicate registrations are rejected.
9. Invalid identifiers and non-callable handlers are rejected.
10. Expected decoding failures follow the documented error policy.
11. Separate router instances maintain independent registrations.
12. Route initialization registers all required handlers.

Use mocks or test doubles where appropriate. Tests must not require external dependencies, a physical CAN device, or live CAN traffic.

## 7. Check when done

* [ ] `AGENTS.md` and the required documentation were reviewed.
* [ ] Existing message models, protocol decoders, and constants were reused.
* [ ] The router is implemented using the standard library only.
* [ ] The central router and subrouters have clear, separate responsibilities.
* [ ] Handler registration is independent of the core dispatch algorithm.
* [ ] Multiple CAN identifiers can map to a handler.
* [ ] Duplicate registrations and invalid inputs are rejected.
* [ ] All documented challenge identifiers route to their correct handlers.
* [ ] Noise and unsupported identifiers do not reach protocol decoders.
* [ ] Dispatch results are structured and consistent.
* [ ] The router contains no socket, transmission, reassembly, payload decoding, or output logic.
* [ ] No mutable global routing state or hidden singleton was introduced.
* [ ] Unit tests cover routing, registration, and failure cases.
* [ ] All tests pass using the standard library.
* [ ] No prohibited dependency or CAN transmission code was introduced.

## 8. Definition of done

Feature 03 is complete when the application can initialize the router, register handlers for all required CAN identifiers, and dispatch complete messages to the appropriate protocol decoders with predictable, testable results.

The implementation must be modular, extensible, transport-agnostic, and appropriately scoped to the challenge.
