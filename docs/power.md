# Power subsystem

[Documentation index](../README.md)

Three solar panels and constant device loads connect to one battery. Values
live in [config.py](../perovsat/config.py); connections live in
[power.py](../perovsat/power.py). Experiments read `log.power`, the `PowerLog`
view in [log.py](../perovsat/log.py).

## Solar panels

| Face | Body normal | Area (m^2) | Efficiency |
| --- | --- | ---: | ---: |
| +X | (1, 0, 0) | 0.008 | 23% |
| +Y | (0, 1, 0) | 0.008 | 23% |
| -Y | (0, -1, 0) | 0.008 | 23% |

Each panel uses spacecraft attitude, the SPICE Sun state and eclipse
illumination. Faces pointing away from the Sun produce zero power. At
1361 W/m^2, one 0.008 m^2 (80 cm^2) panel produces about **2.50 W** at normal
incidence before eclipse attenuation. The faces have different normals, so
summing all three normal-incidence outputs is not an achievable vehicle output.

## Loads

Each device has a count and states with power and duty fractions:

```text
average_power_w = count * sum(state.power_w * state.duty for state in states)
```

Unused duty is off at zero watts. Each device becomes a `SimplePowerSink`
with negative output. Duty cycles become a constant average for the whole run;
load spikes, switching and power modes are not modeled.

| Device | Average load (W) |
| --- | ---: |
| NSLBus | 0.6000 |
| OBC | 0.0631 |
| Eyestar | 0.5796 |
| IMU | 0.0019 |
| SunSensor (2) | 0.0116 |
| AMU (16) | 0.0056 |
| **Total** | **1.2618** |

Values are rounded; counts are included. Configuration rejects invalid duty
fractions, negative or nonfinite loads, noninteger counts, invalid panel
geometry and duplicate device names.

## Battery

The default capacity is **40 Wh**, with **80% initial state of charge (SOC)**.
Basilisk stores energy in joules: `capacity_ws = capacity_wh * 3600`.
Initial energy is capacity multiplied by initial SOC. Every panel and sink
connects through `addPowerNodeToModel`.

Override the initial SOC with `RunConfig(soc_init=0.8)`. SOC is a fraction;
values outside [0, 1] raise `ValueError`.

## Recorded data

`PowerRecorders` groups battery, panel and sink recorders. After execution,
`SimLog.validate()` checks required fields, finite data, sample counts and
matching timestamps before summaries or plots. Power arrays are not padded
or truncated to hide mismatches.

| `log.power` property | Units / type | Meaning |
| --- | --- | --- |
| `t` | s | Battery timestamps |
| `stored_ws` | J | Stored energy |
| `capacity_ws` | J, scalar | Configured capacity |
| `soc` | fraction | Stored energy / capacity |
| `panels` | dict of W arrays | Per-panel generation |
| `sinks` | dict of W arrays | Per-device consumption, positive |
| `generation_w` | W | Sum of panel output |
| `consumption_w` | W | Sum of positive loads |
| `net_w` | W | Generation minus consumption |
| `shadow_factor` | fraction | 0 = shadow, 1 = sunlight |
| `eclipsed` | bool | Shadow factor below 0.5 |

Properties are arrays unless marked otherwise. Positive net power charges the
battery; negative net power discharges it, subject to storage limits.

## Run and extend

From the repository root, run:

```bash
make run SCRIPT=experiments/power/run.py
```

The [power experiment](../experiments/power/run.py) simulates three days with a
1 s task period and 10 s recording period. In `experiments/power/output/` it writes:

- `power_system.png`: generation, consumption, net power and SOC.
- `power_by_sink.png`: per-device load.
- `detumble_curve.png`: body rates and their magnitude.
- `summary.txt`: execution settings and final SOC.

Add hardware through `PANELS` or `DEVICES`. Time-varying loads require a model
publishing power each step. See [development](development.md) for the workflow
and [getting started](getting-started.md) for setup and troubleshooting.
