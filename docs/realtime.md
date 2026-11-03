# Real-time execution

For a fixed-duration three-day mission with incremental telemetry and graceful
stop handling, use [Missions](mission.md). The commands below remain short
real-time demonstrations with in-memory recordings.

Run from WSL/POSIX with Docker running:

```bash
make run SCRIPT=experiments/realtime/run.py
make run SCRIPT=experiments/realtime/run.py ARGS='--duration 60 --factor 2'
```

The first command advances 60 simulated seconds in approximately 60 wall seconds;
the second takes approximately 30 seconds. Build, initialization, and the first
physics tick are outside the measured pacing interval. The orbital epoch is unchanged.
Existing experiments remain unpaced by default.

Set `realtime=True` in `RunConfig` to enable pacing. `realtime_factor` defaults to 1.
`max_lag_s=0.1` is the permitted wall-clock lag; `overrun_policy="warn"` warns once
and counts every tick over the limit. `"stop"` raises an error and writes a partial
summary. Ctrl-C also writes a partial summary when execution is interrupted.
Physics updates are never skipped. The duration ends on the last scheduled task
tick at or before the requested stop time; choose a multiple of `timestep_s`.

The native Basilisk `simSynch.ClockSynch` runs through a small Python wrapper,
after physics and recording. Timing uses a monotonic clock. `summary.txt` records
paced elapsed time, maximum lag, ticks over the lag limit, and maximum tick work
including host overhead (excluding deliberate pacing waits and the first tick).
The adaptive RKF45 integrator and existing physics task period are unchanged.
Timing statistics use constant memory; existing physics recorders still grow
with the number of recorded samples. Choose recording periods for the run length.

For Basilisk 2.10.2, **Vizard listens and Basilisk connects**. Do not publish Docker
port 5556: that can occupy the port Vizard needs. In Vizard 2.4 select **Receive &
Reply** and **Live Display**, enter a local listening address, and click Start
Visualization only after the terminal prints `Waiting for Vizard listener`.
The simulation first loads its models/data, then repeatedly probes TCP 5556.
As soon as the listener opens, the probe closes and Basilisk begins its own
native handshake. This readiness wait is part of the normal `make live` path.

On a native Linux computer with both Docker and Vizard, use host networking and
enter `tcp://127.0.0.1:5556` in Vizard:

```bash
make live
```

For Vizard on another computer, set `--viz-address` to that computer's reachable
IP address (no protocol prefix or port). In Vizard, use `tcp://<that-IP>:5556`.
TCP 5556 must be reachable on the **Vizard computer**. For Windows Vizard with
Docker running inside WSL, the Windows host address is normally the default
gateway shown by `ip route show default` in WSL; use that address in both places.
It may change when WSL restarts. Example:

```bash
make live VIZARD_ADDRESS=172.26.192.1
```

The corresponding `RunConfig` field is `vizard_address`, defaulting to
`127.0.0.1`. Loopback inside an ordinary container refers to the container itself.
`make live` supplies `--network host` at container startup; no Dockerfile rebuild
is required. Under WSL this shares the Linux network, not Windows loopback.

The listener wait defaults to 120 seconds. Override it with:

```bash
make live VIZARD_ADDRESS=172.26.192.1 ARGS='--duration 300 --viz-timeout 180'
```

The matching setting is `RunConfig.vizard_timeout_s`. Timeouts and Ctrl-C while
waiting write `summary.txt` with a failed/interrupted status. Hostnames use the
OS resolver; DNS resolution itself can exceed the TCP wait deadline. Use an IPv4
address when troubleshooting timing. The address must not include spaces,
`tcp://`, or `:5556` in the CLI/config (the Vizard UI requires the full socket URL).

`vizard_live=True` enables the live connection independently of `vizard=True`,
which continues to save a playback file. Both may be enabled together. Live mode
waits for Vizard and can block on a slow/disconnected client; it is an interactive
mode, not a guaranteed deadline interface. Initial connection time is excluded
from pacing; later client delays count toward lag when the update returns.
The listener timeout does not bound Basilisk's native handshake or later streaming
calls. A reachable TCP port alone is not proof that the Vizard protocol is working.
No separate telemetry service or hardware adapters are required for this example.

Run `make test` for physics equivalence, 1x/2x pacing, overload policies, and
interruption tests. Timing tolerances allow ordinary host scheduling jitter.
Docker/WSL execution is soft real time and does not guarantee hardware deadlines.

## Status gauges

### WSL status-pane quick start

With Docker available in WSL and Vizard installed on Windows, run the following
in your WSL terminal. Adjust the checkout path if needed. This uses the default
WSL gateway as the Windows host address for the NAT setup used by this project;
if your network uses a different viewer address, set `VIZARD_HOST` explicitly.

```bash
cd /mnt/g/basilisk-simulation
docker info
VIZARD_HOST=$(ip route show default | awk '{print $3; exit}')
echo "Vizard socket: tcp://${VIZARD_HOST}:5556"
make live VIZARD_ADDRESS="$VIZARD_HOST" ARGS='--duration 6000 --factor 20 --viz-timeout 600'
```

Wait for **Waiting for Vizard listener**, then enter the printed socket address
in Vizard, select **Receive & Reply** and **Live Display**, and click
**Start Visualization**. Open the spacecraft storage pane and scroll to the
six **Face … illumination** gauges. The run covers 6000 simulated seconds in
about five wall-clock minutes if the host and viewer keep up. The ten-minute
connection timeout is separate from the run duration.

For ten minutes at normal real-time speed instead:

```bash
make live VIZARD_ADDRESS="$VIZARD_HOST" ARGS='--duration 600 --factor 1 --viz-timeout 600'
```

The short live CLI writes `experiments/realtime/output/summary.txt`; it does not
save a Vizard playback file. To record playback from a Python experiment, set
`vizard=True` in addition to `vizard_live=True`. Saved status gauges contain
the values published during that run.

### Fields and interpretation

Live and saved Vizard runs request the spacecraft's native storage panel.
`perovsat/vizard_status.py` reads current messages after physics and updates
the gauges before each Vizard frame, independently of recorder sampling.

| Gauge | Meaning |
| --- | --- |
| Battery SOC | Percentage with Charging, Discharging, Idle, Full, or Depleted state |
| Stored energy | Wh against battery capacity |
| Sun visible (eclipse) | Fraction of the solar disc visible, independent of face orientation |
| Face +X / -X / +Y / -Y / +Z / -Z illumination | Incident direct sunlight relative to a face pointed straight at the Sun at the same distance |
| Solar generation / Electrical load | Positive watts generated / consumed |
| Power balance | Magnitude in W, explicitly marked surplus, deficit, or balanced |
| Simulation elapsed | Seconds against requested duration |
| Simulation cadence (configured) | Physics ticks per simulated second |
| Measured simulation updates | Physics ticks per wall second, measured over windows of at least one second |
| Achieved simulation speed | Simulated seconds per wall second over the same window |
| Pacing lag (previous tick) | Only in paced runs; marks LATE beyond `max_lag_s` |

SOC colours change at 20% and 40%; LOW is shown at or below 20%. These are
display thresholds, not load shedding or battery protection controls. A full
battery with a power deficit is Discharging; an empty battery with surplus is
Charging. Power balance is bus power, not accepted charging power: surplus at
full capacity and deficit at empty capacity remain visible. Power and timing
gauge scales expand to the largest observed value (minimum initial scale 1).

Face illumination is `100 * eclipse_visibility * max(0, dot(normal_B, sun_direction_B))`.
The Sun vector is the SPICE Sun position minus spacecraft position, transformed
from inertial to body axes with the current spacecraft attitude. Thus an
unobscured but backward-facing face is 0%, a normally illuminated face is 100%,
and a face at 60 degrees incidence is 50% in full sunlight. This is normalized
direct irradiance, not percentage of physical surface area lit or solar-cell
efficiency. All six bus faces are shown, including faces without solar cells;
only +X, +Y, and -Y currently produce electrical power. Missing geometry is
shown as awaiting data until both input messages are written; a zero-length
or nonfinite Sun-position difference is marked unavailable.

The calculation follows the existing point-spacecraft, cosine-incidence power
model: it includes Earth eclipse attenuation but not appendage self-shadowing,
albedo, scattered light, or a finite-Sun integration across an edge-on face.
`tests/test_face_illumination.py` compares 256 seeded random timesteps over
6000 simulated seconds, plus every sampled penumbra tick, against independent
axis-angle rotations and six native unit-area/unit-efficiency solar panels.
It also compares predictions with the three actual vehicle panel outputs.
Set `PEROVSAT_VALIDATION_DIR` when running that test to export `samples.csv`
and `summary.json` with the times, values, and maximum errors.
See the [validation report](face-illumination-validation.md) for reproducible
commands, measured errors, and the limits of those checks.

The default 0.5-second task period is 2 Hz of simulation time. At 2x pacing,
measured updates should approach 4 Hz and achieved speed 2x. Neither metric
measures viewer FPS. They start as `warming up`, exclude initial connection
setup, and include subsequent streaming delays. Lag reports the last completed
pacer tick because pacing executes after frame publication. No new data can
be displayed while the simulation or its blocking native stream is paused.
Playback shows timing recorded during generation, not playback performance.

Use `--compact-status` with the realtime or mission CLI to omit wall-clock
diagnostics; `--hide-status` omits the adapter and all gauges. Python equivalents
are `RunConfig(vizard_status_diagnostics=False)` and
`RunConfig(vizard_status_panel=False)`. The adapter uses constant memory and
retains native gauge owners; it never writes back to physics messages.

The pane uses Vizard's existing layout and controls. Open, move, or scroll the
spacecraft storage panel as needed. Status text accompanies units so gauge
labels remain stable. Tests cover state transitions, conversions, timing,
serialized output, and physics equivalence. The three-gauge prototype was
verified in Vizard by the user; the expanded layout needs a visual check.

## Troubleshooting

- `Socket failed`: remove leading/trailing spaces in Vizard's address, confirm it
  is a local address of the viewer computer, and close duplicate viewers. Do not
  publish `-p 5556:5556`; Vizard needs to bind this port itself.
- `Timed out waiting for connection`: restart the stalled simulation and viewer,
  then wait for `Waiting for Vizard listener` before clicking Start Visualization.
- Python listener timeout: verify the current Windows/remote host address and
  network access to its TCP 5556 listener. Increasing `--viz-timeout` only gives
  more time to start the viewer; it does not fix an unreachable address.
- `Basilisk-Vizard connection made` without a scene: this confirms only a handshake.
  Confirm the spacecraft renders and time advances before declaring success.
- If native streaming remains blocked after closing Vizard, stop only that run's
  container (`docker ps` to identify it, then `docker stop <container-id>`) before
  retrying. Do not leave old runs waiting in the background.

## Live test procedure

Run `make live` with the appropriate `VIZARD_ADDRESS`, connect the viewer after
the readiness prompt, and verify spacecraft rendering, advancing simulation time,
`Simulation complete`, and the timing statistics in `experiments/realtime/output/summary.txt`.
The automated suite covers retry/timeout/interruption and regression behavior;
it does not replace this GUI test.

For the status pane, also verify these behaviours:

- In sunlight, differently oriented faces show different percentages; opposing
  faces cannot both receive positive direct illumination in this model.
- During full eclipse, all six face percentages are zero. The separate Sun
  visible gauge reports eclipse visibility, not incidence on any one face.
- At 1x with the default timestep, configured cadence is 2 Hz and measured
  updates approach 2 Hz; at 20x they approach 40 Hz while achieved speed
  approaches 20x. Viewer delays can reduce these measured rates.
- `--compact-status` removes measured cadence, achieved speed and pacing lag
  but keeps the face gauges. `--hide-status` removes the entire status pane.

On 2026-10-22, a diagnostic run using this readiness sequence completed with
Windows Vizard 2.4 and Basilisk 2.10.2 in WSL Docker host-network mode: 30 simulated
seconds, 29.997099 paced wall seconds, zero ticks over the 0.1-second lag limit,
and a rendered spacecraft view. This validates that setup and startup sequence;
it does not establish automatic reconnection or guaranteed timing on other hosts.
