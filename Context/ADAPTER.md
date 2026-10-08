# Grading Adapter Contract

Your tool must accept a `--grader` flag. In that mode:

- No terminal dashboard drawing, no ANSI cursor control. Plain line-oriented output only.
- One JSON object per line (newline-delimited JSON) written to **stdout**, flushed after every line.
- Nothing else goes to stdout. Logs/diagnostics go to stderr.
- Every line has a `"type"` field identifying what it is. Emit lines as events happen — this is a live stream, not a final summary.

## `telemetry` — emit one whenever you decode a new module telemetry frame

```json
{"type": "telemetry", "module": 0, "seq": 4821, "voltage": 412.3, "current": 118.55, "temp_c": 47, "enabled": true, "fault": false, "derated": false}
```

## `fault` — emit one whenever you decode a fault-code frame

```json
{"type": "fault", "module": 2, "code": 1}
```

## `diag_complete` — emit one every time you finish reassembling a diagnostic message

```json
{"type": "diag_complete", "can_id": "0x6f0", "string": "SN:PMU-4471-A FW:2.3.1", "ts_ns": 88123456789}
```

`can_id` can be a hex string with or without a `0x` prefix, in either case, or a plain integer — any of those work, they're all normalized before comparison. `0x6f0`, `0x6F0`, `6f0`, and `1776` are all treated identically.

`ts_ns` is your own `time.monotonic_ns()` (or equivalent) at the moment reassembly completed — this is what lets grading match a specific completion against a specific point in the known traffic timeline, not just "some string eventually looked right." Do **not** emit a line for an attempt you abandoned (orphan/out-of-order/oversized/superseded-by-restart) — silently not completing that one is the correct behavior, not something to report.

## `stats` — emit periodically (at least once every few seconds) and once more right before you'd otherwise exit

```json
{"type": "stats", "frames_processed": 15234}
```

`frames_processed` is your running total of real frames (telemetry + fault + diagnostic) you have processed — never count noise-range frames (`0x200`-`0x2FF`) here, whether or not you looked at them. **This is how Filtering is scored** — if you never emit a `stats` line, or emit one too rarely to reflect a recent count, you'll score zero there regardless of whether your actual filtering logic is correct.

## What grading does with this

- Cross-checks every `telemetry`/`fault` value against the generator's own send log (it knows exactly what it sent).
- Confirms your last `telemetry` line for each module reflects that module's true latest `seq` at the end of the run (freshness), not stale data.
- Walks the generator's timeline of the 5 messy situations and checks: no `diag_complete` with wrong content for a broken attempt (missing is correct; wrong content is not), and the very next `diag_complete` on that ID after each situation matches the recovery message exactly.
- Compares your final `frames_processed` against the generator's real-traffic-only count.
- Separately (not from anything you report) samples your process's own memory over the run to check it doesn't grow across repeated abandonment cycles.