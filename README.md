# PEROVSAT simulation

PEROVSAT's Basilisk simulation models orbit, passive magnetic attitude control,
solar generation, and battery energy. Python assembles one vehicle; experiments
choose run settings and analyze its output. C++ plugins model the permanent
magnet and hysteresis rods.

**New teammates: start with [Getting started](docs/getting-started.md).**

## Documentation

| Guide | Contents |
| --- | --- |
| [Getting started](docs/getting-started.md) | Setup, first run, outputs, troubleshooting |
| [Architecture](docs/architecture.md) | Code map, data flow, units, assumptions |
| [Development](docs/development.md) | Experiments, hardware changes, builds, validation |
| [Power](docs/power.md) | Panels, loads, battery, recorded power |
| [Real time](docs/realtime.md) | Wall-clock pacing, timing diagnostics, live Vizard |
| [Missions](docs/mission.md) | Three-day runs, segmented telemetry, stopping and validation |
| [Rod model](ExternalModules/hysteresisRods/README.md) | Hysteresis equations and parameters |

## Quick start

Run from the repository root in a POSIX shell with GNU Make and Docker running.
On Windows, use WSL with Docker Desktop integration; the Makefile does not run
directly in PowerShell. The container supplies Basilisk and the build tools.

```bash
docker info
make smoke
make test
```

The first build downloads the image and compiles plugins. Try the
[short example](docs/getting-started.md#run-a-small-experiment-first) before
launching these longer experiments:

```bash
make run SCRIPT=experiments/power/run.py      # 3 simulated days
make run SCRIPT=experiments/detumble/run.py   # 22 simulated days
make shell                                  # interactive container
```

For a fixed-duration mission with incremental telemetry saving, use `make mission`
(three days at 1x) or `make mission ARGS='--unpaced'` for the same duration as fast
as possible. See [Missions](docs/mission.md) for output and live-viewer options.

For live Vizard on the same native Linux host, run `make live`. Wait for
`Waiting for Vizard listener`, then select **Receive & Reply** and **Live Display**
in Vizard at `tcp://127.0.0.1:5556` and click **Start Visualization**.
For Windows/WSL or another viewer host, follow [Real time](docs/realtime.md).

Plots and summaries go to each experiment's `output/` directory. Vehicle values
live in [config.py](perovsat/config.py); execution settings live in
[run_config.py](perovsat/run_config.py).

Unfinished [continuous-WMM notes](experimental/magneticFieldWMMContinuous/README.md)
are excluded from the build.
