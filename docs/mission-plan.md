# Three-day mission implementation plan

Requested scope: fixed-duration mission, default 259200 simulated seconds (3 days).
Retain the existing vehicle, RKF45 integrator and physics task. Support 1x real
time, accelerated pacing and unpaced execution; live Vizard is optional.

## Before implementation

- Run the existing suite: 21 tests passed on 2026-10-22.
- Inspect Basilisk 2.10.2's repeated stop-time execution and recorder clearing.
- Add regression tests for segmented telemetry, run-directory protection,
  exact stop time, equivalence to one-shot execution, timeout and interruption.
- Run new tests before implementation to establish the missing behavior.

## Implementation

1. Add a separate mission runner and CLI; preserve existing experiments' `run()`
   and full-memory `SimLog` interface.
2. Execute to increasing absolute stop times without resetting models or clocks.
   Validate task/sample/segment alignment. Save compressed NPZ telemetry segments
   atomically and clear saved recorders to bound memory by the segment interval.
3. Store run configuration, vehicle configuration, source revision/hash information,
   progress, final status, timing and sampled health statistics in a manifest and
   readable summary. Use a new output directory, never overwrite another run.
4. Print periodic progress. Honor graceful CLI stop requests between execution
   intervals; retain committed telemetry on interruption, model error or disk error.
   Saved telemetry is not a restart checkpoint for the integrator/hysteresis state.
5. Keep Vizard readiness sequencing. Document that the native handshake/stream can
   block and that live viewer memory and disconnect behavior are not bounded by
   the mission runner. Recommend headless operation for unattended long runs.
6. Document launch, monitoring, loading segments and validation evidence.

## Acceptance tests

- Existing regressions pass unchanged.
- Segmented and one-shot state histories agree at the same timestamps; no missing
  or duplicated samples across boundaries; final partial segments persist.
- Defaults cover 259200 seconds; invalid timing and existing run directories fail.
- Graceful interruption saves valid partial results; injected write/model errors
  leave earlier segments intact and report failure rather than completion.
- A complete unpaced three-day run produces finite validated telemetry through
  the requested endpoint and bounded recorder buffers. Inspect battery limits,
  eclipse transitions, orbit radii and file continuity. This is a model sanity
  check, not independent physical validation or a guarantee of mission viability.
- Short 1x/accelerated runs validate timing. A short real Vizard run verifies the
  mission integration if an interactive viewer is available.
- Record actual tests and limitations; do not claim a 72-hour wall-clock soak.

Push tested changes only to `realtime-simulation`.
