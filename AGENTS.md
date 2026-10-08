# This runs on a Raspberry Pi 5, not your usual dev machine

This project is developed and tested on a remote Raspberry Pi 5 (aarch64, Raspberry Pi OS, user `pi`), accessed over SSH through Raspberry Pi Connect. Do not assume tools, versions or hardware from your training data — check them on the device before relying on them (`uname -m`, `python3 --version`, `ip -details link show vcan0`, installed packages).

- The challenge material lives in `~/challenge/` and is read-only. Read `~/challenge/CHALLENGE.md` (full specification) and `~/challenge/ADAPTER.md` (output contract for evaluation mode) before writing any code. They take precedence over anything in this repo.
- Test CAN traffic comes from the generator in `~/challenge/`, on the `vcan0` virtual CAN interface. Use the generator as-is; never modify it.
- `vcan0` should already be up. Only bring it up yourself (with `sudo`) if it is down, and record the commands in the README.
- All code lives in this repository under `~/workspace/`. Nothing is written outside it except what the README documents.

## Application Building Context

Read the following files in order before implementing or making any architectural decision:

1. `context/project-overview.md` — challenge summary, goals, features, and scope, as derived from `CHALLENGE.md`
2. `context/architecture-context.md` — system structure, boundaries (CAN bus I/O, decoding, processing, adapter output, CLI), and invariants
3. `context/code-standards.md` — implementation rules and conventions
4. `context/ai-workflow-rules.md` — development workflow, scoping rules, verification on `vcan0`, and delivery approach
5. `context/progress-tracker.md` — current phase, completed work, open questions, and next steps

Update `context/progress-tracker.md` after each meaningful implementation change.

If implementation changes the architecture, scope, or standards documented in the context files, update the relevant file before continuing.
