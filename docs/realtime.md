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

## Scenario

`make realtime` runs one paced scenario from a JSON file. `SCENARIO` is a path
relative to the Basilisk repository root, which is the container working
directory:

```bash
make realtime SCENARIO=path/to/scenario.json
```

The file is a JSON object with exactly these fields:

| Field | Meaning |
| --- | --- |
| `timestep_s` | Finite task period greater than zero, and at least 1 ns after rounding to integer nanoseconds |
| `duration_s` | Finite duration greater than zero, and a positive integer multiple of `timestep_s` in those rounded nanoseconds |
| `devices` | Device names, in order, whose samples a future exporter may publish |

`devices` may be empty. The run still propagates the orbit and the magnetic
field, and no sample export is selected. The only known name is `imu`. That
selection records that a future exporter may publish body-frame IMU stimulus.
This slice does not encode frames and does not publish device samples.

Any other field is rejected, including `epoch_utc`. The Basilisk epoch stays
the vehicle default. That SPICE epoch places the orbit and the World Magnetic
Model. It is not synchronized with the FlatSat, and real-time sample times
must not be taken from it. The run writes `output/summary.txt` in the scenario
file's directory when the simulation produces that file.

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

On 2026-10-22, a diagnostic run using this readiness sequence completed with
Windows Vizard 2.4 and Basilisk 2.10.2 in WSL Docker host-network mode: 30 simulated
seconds, 29.997099 paced wall seconds, zero ticks over the 0.1-second lag limit,
and a rendered spacecraft view. This validates that setup and startup sequence;
it does not establish automatic reconnection or guaranteed timing on other hosts.
