# Fixed-duration missions

The mission runner defaults to **3 days (259200 seconds) at 1x speed**: allow
72 wall-clock hours plus setup and file writing. It uses the existing spacecraft,
environment, passive magnetic control and power models without changing physics.
The physics step is 0.5 s; telemetry is sampled every 10 s and saved every 300 s.

## Run from WSL or Linux

```bash
cd /mnt/g/basilisk-simulation   # use your checkout path on native Linux
make mission                  # three days, 1x, no viewer required
make mission ARGS='--unpaced'  # same three simulated days, as fast as possible
make mission ARGS='--days 3 --factor 60'  # approximately 72 minutes if host keeps up
make mission ARGS='--duration 60 --record-period 1 --segment 10'
```

Each run creates a timestamped directory beneath `experiments/mission/output/`.
Set `--output path/to/new-directory` for a specific location; existing directories
are refused. `--days` and `--duration` are mutually exclusive, as are `--factor`
and `--unpaced`. Use `make mission ARGS='--help'` for all options.

`--timestep`, `--record-period`, `--segment`, and `--control` are in simulated
seconds. Duration, sampling, segment and control intervals must be positive
multiples of the physics step; segments must also be multiples of the sampling
period. Default control interval is 5 s. The final physics endpoint is exact;
the final telemetry sample precedes it if the duration is not a sampling multiple.

## Optional live Vizard

```bash
make mission-live VIZARD_ADDRESS=172.26.192.1 ARGS='--duration 60 --segment 10'
```

Use the reachable Windows host address for your WSL installation; the example
address can change. Native Linux with Vizard on the same host uses `127.0.0.1`.
Wait for `Waiting for Vizard listener`, then enter the matching
`tcp://ADDRESS:5556` in Vizard, select **Receive & Reply** and **Live Display**,
and click **Start Visualization**. The runner waits for the listener before
starting the native handshake. See [Real time](realtime.md) for networking details.

`--viz-timeout` bounds listener readiness only. Native handshake and streaming
can block if the viewer stalls or disconnects, delaying stop handling. Viewer
memory is separate from recorder memory. Prefer headless runs for unattended
missions. This is wall-clock pacing on a general-purpose OS, not hard real time.
`--max-lag` defaults to 0.1 s; `--overrun-policy warn` continues without skipping
physics steps, while `stop` fails the run when that threshold is exceeded.

## Results and stopping

Progress prints about every five wall seconds when execution returns to Python.
SOC shown is the latest saved sample. The output directory contains:

- `manifest.json`: status, executed duration, persisted sample count, segment
  list, configuration snapshots, source hashes/revision when available, health
  statistics and pacing measurements.
- `summary.txt`: readable status and statistics.
- `telemetry-000000.npz`, etc.: compressed arrays with units in their names.

The manifest is updated at segment saves and termination. During a segment it
can lag console progress. Each file is written through a temporary file and
replaced; recorder buffers are cleared only after saving the manifest. With the
defaults, at most 31 samples per recorder are buffered. Segment metadata grows
with the number of files; total process memory is not a fixed hard limit.

Ctrl+C or SIGTERM requests a stop at the next control boundary, saves remaining
valid samples and marks the run `interrupted` (CLI exit 130). A second interrupt
forces Python interruption. Native blocking calls can delay signals. A model or
I/O error returns nonzero and attempts to mark the run `failed`; earlier saved
segments remain. If storage itself fails, the last manifest can remain stale.
Abrupt termination or power loss can lose the current segment; directory-entry
durability depends on the host filesystem. Treat the manifest's segment list as
authoritative and ignore unlisted temporary/orphan files.

Saved telemetry **cannot resume** integrator or hysteresis state. Restarting
creates a new mission. Source hashes describe source files, not compiled binary
provenance. Keep the same toolchain/image and source revision for reproduction.

## Validate and read telemetry

```bash
make run SCRIPT=experiments/mission/analyze.py ARGS='experiments/mission/output/RUN'
```

The analyzer checks all persisted channels for finite values, matching lengths,
continuous timestamps, sample counts, battery bounds and completion consistency.
It reads one segment at a time and prints JSON statistics. An interrupted run
can have valid telemetry without being a completed mission.

```python
import json
from pathlib import Path
import numpy as np

run = Path('experiments/mission/output/RUN')
manifest = json.loads((run/'manifest.json').read_text())
for segment in manifest['segments']:
    with np.load(run/segment['file'], allow_pickle=False) as data:
        print(data['t_s'], data['soc'], data['omega_B_rad_s'])
```

Other channels include position, velocity, attitude MRPs, magnetic field,
illumination, power, battery energy and individual rod states/torques. Statistics
are sampled observations; eclipse transition counts have sampling resolution.
Battery bounds and finite orbital data are sanity checks, not independent
physical validation or proof of mission viability.

## Validation

See [implementation plan](mission-plan.md) for acceptance criteria. Regression
tests compare segmented output to one-shot output, exercise partial final
segments, output protection, corruption detection, I/O failure, pacing at 1x
and 2x, and CLI termination. Full-duration validation results are recorded below.

Validation on 2026-10-22 using Basilisk 2.10.2 in the existing WSL Docker image:

- All 32 regression tests passed, including fractional endpoint validation using
  integer nanoseconds to avoid floating-point completion comparisons.
- Full unpaced default mission completed 259200 simulated seconds in 208.96 wall
  seconds including setup on this host (performance varies).
- Saved 25921 samples in 864 segments, with a maximum of 31 buffered samples per
  recorder. The analyzer checked all saved channels and timestamp continuity.
- Sampled SOC ranged from 50.91% to 80.48%, ending at 51.39%; orbit radius ranged
  from 6794.60 to 6801.40 km, with 93 sampled eclipse transitions.
- Short 1x and 2x segmented runs met the timing test tolerance of 0.3 s; SIGTERM
  saved valid partial telemetry and returned exit 130.

This was not a 72-hour wall-clock soak. The new mission command's Vizard launch
arguments and existing readiness tests were checked; an interactive Vizard
session was not repeated for this mission runner.
