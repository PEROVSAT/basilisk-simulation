# Working on the simulation

[Documentation index](../README.md)

## Where to make a change

| Change | Start here |
| --- | --- |
| Duration, sampling, initial attitude/rate, SOC or epoch | Your experiment's `RunConfig` |
| Mass, inertia, panels, devices, battery, rods or orbit | [perovsat/config.py](../perovsat/config.py) |
| Gravity, field or eclipse connections | [perovsat/environment.py](../perovsat/environment.py) |
| Attached magnetic effectors | [perovsat/pmac.py](../perovsat/pmac.py) |
| Power connections | [perovsat/power.py](../perovsat/power.py) |
| Magnet or hysteresis equations | Corresponding C++ module in [ExternalModules/](../ExternalModules) |
| Recorded data exposed to experiments | [perovsat/log.py](../perovsat/log.py) and subsystem recorder setup |
| Shared plots | [experiments/plotting.py](../experiments/plotting.py) |

Keep hardware values in vehicle configuration and plotting in experiments.
Use `RunConfig` for supported execution and initial-condition overrides so
experiments continue to compare the same vehicle.

## Add an experiment

Copy the [first-run example](getting-started.md#run-a-small-experiment-first)
into a new script, or follow [experiments/power/run.py](../experiments/power/run.py). Select an output
directory, construct a fresh simulation, call `run()`, then analyze `SimLog`.
No Makefile change or image rebuild is needed:

```bash
make run SCRIPT=experiments/my_study/run.py
```

| `RunConfig` field | Default and meaning |
| --- | --- |
| `name` | `"unnamed"`; summary label and Vizard filename prefix |
| `duration_s` | `3600.0`; positive simulated duration |
| `timestep_s` | `0.5`; positive task period |
| `record_period_s` | `1.0`; positive requested recording period |
| `omega_init` | `None` uses vehicle default; finite body rate vector in rad/s |
| `sigma_init` | `None` uses vehicle default; finite MRP vector |
| `soc_init` | `None` uses vehicle default; fraction in [0, 1] |
| `epoch_utc` | `None` uses configured SPICE epoch string |
| `output_dir` | `None` writes to `output/` relative to the working directory |
| `vizard` | `False`; request visualization output if supported |

Initial vectors accept three entries or a 3×1 nested list. Follow the configured
epoch format, for example `2026 JUN 21 12:00:00.0 (UTC)`. `RunConfig` can also
be imported from `perovsat.run_config` without loading Basilisk. Settings are
revalidated before building models. Create a new simulation instance for each run.

## Change the vehicle

Panels need a unit body normal, positive area in m², and efficiency in [0, 1].
Devices need unique names, positive integer counts, nonnegative powers and
state duty fractions summing to at most one. Power is per instance; count is
applied by `average_power_w`. Leftover duty is off at zero power.

For example, two instances each drawing 0.4 W for 25% of the time contribute
`2 × 0.4 × 0.25 = 0.2 W` continuously. Adding that device does not introduce
switching behavior.

Rods need unique tags, unit body axes and an existing material key. Materials
require positive `Bs` and `Hc`, `0 < Br < Bs`, and finite initial magnetization.
Changing rod dimensions may require reconsidering effective material values,
not just volume, because those values include installed demagnetization effects.

## Build commands

Run these in the host POSIX shell at the repository root:

| Command | Purpose |
| --- | --- |
| `make help` | List common targets |
| `make plugins` | Compile/install plugins when source timestamps change |
| `make plugins-force` | Force rebuild, including after module renames |
| `make smoke` | Build as needed and check both plugin imports |
| `make test` | Build as needed and run all regression tests |
| `make run SCRIPT=...` | Execute an experiment with the environment configured |
| `make shell` | Open a container shell; `exit` returns to the host |
| `make image` | Rebuild after Dockerfile, Basilisk or toolchain dependency changes |
| `make clean` | Remove local environment/build artifacts; the next run rebuilds them |
| `make image-clean` | Also remove the local toolchain image and image stamp |

Python edits are visible through the mounted checkout without rebuilding the
image. C++ sources/headers, SWIG interfaces, custom messages, plugin package
initialization and build configuration are plugin inputs. The image and SDK
are pinned to Basilisk 2.10.2; keep their versions consistent.

## Modify a plugin or message

Each active module has a header, implementation and `.i` SWIG interface.
`CMakeLists.txt` declares compilation and binding generation. Custom payloads
are in [messages/](../messages); `bsk_generate_messages` creates their bindings. The plugin
package imports generated messaging before wrappers so messages support recorders.

Preserve Python ownership of attached C++ wrappers. Keep derivative and torque
evaluation separate from deliberate state changes: modifying an ODE state
during an integrator stage can change the numerical method. The rod torque
helper projects a local value; the scheduled update projects the actual state,
and exceptional recovery has its own helper.

After binding changes, run `make plugins-force`, `make smoke` and `make test`.
For a recorder channel, update the typed container, attach its recorder, expose
it through `SimLog`, and extend validation/tests. Preserve time alignment rather
than padding or truncating arrays to hide mismatches.

## Validate and share changes

Without Basilisk, configuration/logging tests can run with Python and NumPy:

```bash
python -m unittest discover -s tests -v
```

The integration test skips there. Use `make test` to exercise compiled modules
and the short simulation in the container. For dynamics changes, also compare
representative outputs before/after and repeat at a finer task period. Passing
an import check or two-second run does not establish multi-day damping accuracy.

When sharing results, record the Git revision, local vehicle changes,
`RunConfig`, command, output directory and validation performed. `summary.txt`
does not capture the full vehicle or Git revision, so include those in experiment
notes or the review description. Update the relevant guide when behavior or
assumptions change.
