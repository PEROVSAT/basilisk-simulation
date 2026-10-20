# Real-time execution

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
Visualization while Basilisk is waiting.

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

`vizard_live=True` enables the live connection independently of `vizard=True`,
which continues to save a playback file. Both may be enabled together. Live mode
waits for Vizard and can block on a slow/disconnected client; it is an interactive
mode, not a guaranteed deadline interface. Initial connection time is excluded
from pacing; later client delays count toward lag when the update returns.
No separate telemetry service or hardware adapters are required for this example.

Run `make test` for physics equivalence, 1x/2x pacing, overload policies, and
interruption tests. Timing tolerances allow ordinary host scheduling jitter.
Docker/WSL execution is soft real time and does not guarantee hardware deadlines.
