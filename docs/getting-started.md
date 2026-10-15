# Getting started

[Documentation index](../README.md)

## What you will run

PEROVSAT is a small satellite with a permanent magnet and hysteresis rods for
passive magnetic attitude control (PMAC). The magnet applies torque in Earth's
magnetic field; the rods model magnetic hysteresis that dissipates rotational
energy. The simulation also tracks sunlight, eclipses, solar generation,
constant average electrical loads, and battery energy.

An **experiment** is a Python script that selects execution settings, runs this
vehicle, and inspects or plots recorded arrays. Power and detumble experiments
share the same vehicle implementation.

## Set up your checkout

You need Git, Docker with access to Linux containers, GNU Make, and a POSIX shell
with standard tools such as `find`. The container supplies Python, Basilisk
2.10.2, the compiler, CMake, SWIG, and build dependencies. Image downloads and
dependency installation need network access. A separate host Basilisk
installation is not required.

On Windows, use a WSL terminal with Docker Desktop integration enabled for that
distribution. Open the checkout there (a checkout on `G:` is normally under
`/mnt/g/`). Run `make` commands from that shell, not PowerShell. Keep the
repository's `.venv` for the Linux container; do not reuse a Windows Python
environment in that directory.

Open a terminal at the cloned repository root, then run:

```bash
docker info
make smoke
make test
```

`docker info` must connect to the engine. `make smoke` builds what is needed
and prints `plugins ok` if both custom modules import. `make test` runs
configuration and logging regressions plus a two-second simulation. That short
simulation checks wiring and recording; it does not establish long-term
physical accuracy. The first build takes longer than subsequent runs.

## Run a small experiment first

Create `experiments/first_run.py` with this code:

```python
from pathlib import Path

from perovsat.simulation import PerovSatSimulation, RunConfig
from experiments.plotting import plot_detumble_curve, plot_power_history


def main():
    sim = PerovSatSimulation(RunConfig(
        name="first_run",
        duration_s=600.0,
        timestep_s=0.5,
        record_period_s=1.0,
        output_dir=Path(__file__).resolve().parent / "first_run_output",
    ))
    log = sim.run()
    plot_detumble_curve(log, sim.output_dir)
    plot_power_history(log, sim.output_dir)
    print(f"Final SOC: {log.power.soc[-1]:.1%}")
    print(f"Mean generation: {log.power.generation_w.mean():.3f} W")


if __name__ == "__main__":
    main()
```

From the host shell, run:

```bash
make run SCRIPT=experiments/first_run.py
```

The script executes in the container while its files remain in your checkout.
Look in `experiments/first_run_output/` for `detumble_curve.png`,
`power_system.png`, and `summary.txt`. Ten simulated minutes check the workflow;
do not expect full detumbling or a complete orbit in that time.

Each simulation instance supports one call to `run()`. For another execution,
create another instance. Choose distinct output directories to preserve runs:
reusing a directory overwrites the same plot names and `summary.txt`. Logs are
in-memory arrays; the workflow does not automatically save raw data.

## Read the results

`run()` returns a `SimLog`, also available as `sim.log`. Time arrays are seconds.
`log.attitude.omega_B` is rad/s; `omega_deg` is deg/s. `log.power.soc` is a
fraction: `0.8` means 80%. Generation and displayed consumption are positive
watts; net power is generation minus consumption. The battery stores joules,
although its configured capacity is in Wh.

The summary contains execution settings and final SOC. Use plots and arrays for
the histories. A successful run validates recorder consistency; assessing model
assumptions and choosing sufficiently fine time settings are separate steps.

Once the small run works, try the existing experiments:

| Command | Settings and output directory |
| --- | --- |
| `make run SCRIPT=experiments/power/run.py` | Three days, 1 s task, 10 s recording; `experiments/power/output/` |
| `make run SCRIPT=experiments/detumble/run.py` | 22 days, 10 s task, 20 s recording; `experiments/detumble/output/` |

Power produces power history, per-device load and attitude plots. Detumble
produces attitude, magnetic field, rod torque and hysteresis plots. The detumble
script also requests Vizard output: when supported, Basilisk writes a file ending
in `_UnityViz.bin`. Python plots do not require opening Vizard.

## Troubleshooting

| Symptom | What to check |
| --- | --- |
| `make` missing or shell syntax errors | Use a POSIX shell with GNU Make; on Windows use WSL. |
| Docker missing or not running | Check `docker info` in the same shell; start the engine and check WSL integration if applicable. |
| Image or dependency download fails | Check network access to the registry/package source shown in the error. |
| `Basilisk` or plugins cannot be imported | Use `make run` or `make shell`, then `make smoke`; host Python is a separate environment. |
| Old `hyteresisRods` import fails | Update it to `hysteresisRods` and run `make plugins-force`. |
| Plugin appears stale after C++ or SWIG changes | Run `make plugins-force`; after toolchain changes, run `make image` first. |
| Missing SPICE or WMM data | Keep the full error and check runtime data availability/network access; `environment.py` uses Basilisk's data lookup. |
| Configuration raises `ValueError` | Correct the named parameter and check units. SOC and duty are fractions, not percentages. |
| Recorder validation fails | Check scheduling, recorder periods, message wiring and payload fields; do not pad arrays to hide the mismatch. |
| Second call to `run()` fails | Create a new `PerovSatSimulation` instance. |

When asking a teammate for help, include the command, full traceback/build error,
Git revision and local changes, experiment settings, and whether `make smoke`
and `make test` pass. Continue with [architecture](architecture.md) or
[development](development.md).
