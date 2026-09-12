# Optional flight recorder

## Document control
- Owner: Munish Goyal
- Created: 2026-09-12
- Status: Validated
- Baseline: 957b7f37

## User problem and desired outcome
Recorder overhead has previously pressured the main run. The owner wants a
single environment-level feature flag, initially off, to retain diagnostic
optionality while removing optional capture work from normal planning.

## Scope
Use TRIPPLANNER_FLIGHT_RECORDER as the master flag in the existing local,
canary and prod profiles. Default to disabled, including when absent or invalid.
Gate private diagnostic recording and automatic local trip revision capture.
Retain TRIPPLANNER_DEBUG_STORE as the local archive sub-control; hosted archives
remain prohibited. Verbose capture never overrides the master flag.

## Acceptance criteria
1. Every checked-in profile explicitly disables recording.
2. Disabled model construction omits recorder callbacks and custom transports;
   usage accounting remains attached. Graph compilation omits recorder callbacks.
3. Disabled ASGI and provider requests bypass capture before body parsing,
   hashing, recorder UUID allocation or recorder timers, including errors.
4. Disabled recording performs no serialization, enqueue, worker startup or
   automatic local archive work. Existing files remain available for inspection.
5. Enabling the flag and restarting restores recording with existing privacy,
   retention, batching and streaming behavior.
6. Ordinary logs, usage ledgers, spend enforcement and trip persistence continue.

## Validation matrix
| Contract | Proof |
| --- | --- |
| Defaults and parsing | Flag tests plus environment profile tests |
| Disabled capture has no work | Sentinel failures at capture and serialization boundaries |
| Model and graph setup | Callback and model-option assertions |
| Provider behavior | Success/error passthrough tests and outbound client regressions |
| Opt-in capture | Existing recorder and archive suites |
| Style | Repository Ruff gate (E9,F63,F7,F82) |

## Operations and boundaries
Change the flag in config/environments/<environment>.env and restart that
backend. Process environment overrides retain existing precedence. No hot-toggle
contract, production deployment, deletion of recorder history, frontend changes,
or claimed latency benchmark is part of this milestone.

## Validation evidence
- Recorder, archive and config run: 88 passed; the sole failure is the existing
  profile key-parity test, because five VALIDATION_GATE_* keys exist only locally.
  Verified the same mismatch at baseline 957b7f37.
- Outbound, observability, release and selector checks: 102 passed.
- Graph policy, parallel tools, tool selection and selector checks: 106 passed.
- Both modified deployment scripts passed PowerShell syntax parsing.
- Repository Ruff gate passed; full Ruff has existing baseline findings.
- Hosted deploy scripts now export the master flag from the imported profile.
- No live performance benchmark or hosted deployment was performed.
