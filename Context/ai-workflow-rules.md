Development Workflow
Approach

Build this project incrementally using a spec-driven workflow on the Raspberry Pi 5. Context files define what to build, how to build it, and what the current state of progress is. Always implement against these specs — do not infer or invent behavior from scratch.

Sources of truth, in priority order:

~/challenge/CHALLENGE.md — the official specification (read-only).
~/challenge/ADAPTER.md — the output contract for evaluation mode (read-only).
docs/architecture-context.md — our architecture, boundaries and invariants.
docs/progress-tracker.md — current state, completed units and open questions.

If a project context file contradicts CHALLENGE.md or ADAPTER.md, the challenge files win and the context file must be corrected.

Environment Rules
All development happens inside ~/workspace/<repo> on the Pi. Nothing is written under ~/challenge/.
The CAN traffic generator in ~/challenge/ is used as-is to produce test traffic. Do not modify, copy-and-patch, or reimplement it.
Tests run against the vcan0 virtual CAN interface. Check it is up (ip link show vcan0) before testing; bring it up with sudo only if it is down, and document the commands used.
Do not install system-wide packages or change system configuration beyond vcan0. Prefer a project-local virtual environment and pinned dependencies listed in the repo.
The target is a Raspberry Pi 5 (aarch64, Raspberry Pi OS). Keep CPU and memory use modest and avoid dependencies that need heavy native builds.
Never commit secrets, passwords or auth keys to the repository.
Scoping Rules
Work on one feature unit or subsystem at a time.
Prefer small, verifiable increments over large speculative changes.
Do not combine unrelated system boundaries in a single implementation step.

The system boundaries for this project are:

Bus I/O — opening the CAN socket on vcan0, receiving and (if required) sending frames.
Decoding — turning raw frames (ID, DLC, payload) into domain values as defined in CHALLENGE.md.
Processing — any state, aggregation, filtering, timing or error detection the spec requires.
Output / Adapter — producing output that matches the ADAPTER.md contract exactly.
CLI and configuration — entry point, flags, modes (normal vs. evaluation).
When To Split Work

Split an implementation step if it combines:

Bus I/O changes and decoding logic changes
Decoding logic and output format changes
Changes to the evaluation-mode output and to normal-mode behavior
Behavior that is not clearly defined in CHALLENGE.md, ADAPTER.md or the context files

If a change cannot be verified end to end quickly against vcan0 and the traffic generator, the scope is too broad — split it.

Verification

Each unit is verified at two levels:

Offline unit tests — decoding and processing are tested with recorded or hand-built frames, without a live bus, so they run anywhere.
Live test on vcan0 — run the solution while the traffic generator is producing frames, and confirm the output matches ADAPTER.md (format, fields, ordering, timing).

A unit that has only been tested offline is not done until it has also been checked live on the Pi.

Handling Missing Requirements
Do not invent behavior that is not defined in CHALLENGE.md, ADAPTER.md or the context files.
If a requirement is ambiguous, resolve it in the relevant context file before implementing, and record the interpretation chosen and why.
If a requirement is missing, add it as an open question in progress-tracker.md before continuing. Questions that need the evaluators' answer are flagged so they can be sent by email.
Observed behavior of the traffic generator is evidence, not specification. If it differs from CHALLENGE.md, record the difference as an open question.
Protected Components

Do not modify these unless explicitly instructed:

Everything under ~/challenge/ (spec, adapter contract, traffic generator).
Third-party library internals (e.g. python-can or any vendored code).
System networking configuration other than bringing vcan0 up.

Project-specific logic must live in the project's own modules, wrapping third-party libraries rather than patching them.

Keeping Docs In Sync

Update the relevant context file whenever implementation changes:

System architecture or boundaries
Frame decoding rules or signal definitions as implemented
Output contract handling (anything touching ADAPTER.md compliance)
Code conventions or standards
Feature scope
How to set up, run and test the project on the Pi (README)

Progress state must reflect the actual state of the implementation, not the intended state.

Before Moving To The Next Unit
The current unit works end to end within its defined scope, including a live run on vcan0.
Offline tests for the unit pass.
No invariant defined in architecture-context.md was violated.
Output still matches the ADAPTER.md contract.
progress-tracker.md reflects the completed work and any new open questions.
The change is committed to the repository in ~/workspace with a clear message.