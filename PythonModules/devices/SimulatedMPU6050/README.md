# SimulatedMPU6050

A register-level simulation of the **InvenSense MPU-6050** — the 6-axis IMU
(3-axis gyroscope + 3-axis accelerometer + temperature sensor) — for the
PEROVSAT CubeSat software-in-the-loop effort.

Its **core measurement**: given the *true* motion of the body it's bolted to,
produce the same 16-bit register values a real MPU-6050 reports over I²C —
correct full-scale-range quantisation, saturation, zero-rate bias, and Gaussian
noise. That's the piece needed now; lockstep/comms with flight software come
later.

> **Status:** lives inside `basilisk-simulation/` for now; intended to be split
> into its own repository once the device interface settles. Structured as a
> self-contained package so that split is a clean lift.

## Design

The sensor model (`simulated_mpu6050/`) is **pure Python + numpy — no Basilisk
dependency.** You hand it truth in SI units, it hands back counts and decoded
engineering values. Anything can drive it: a Basilisk sim, a bench replay, a
unit test.

```
truth motion  ──▶  SimulatedMPU6050.sample()  ──▶  int16 registers + Reading
(omega, specific force, temp)                        (accel/gyro/temp, raw + eng.)
```

| File | Role |
|------|------|
| `registers.py` | Datasheet constants: I²C/register map, FS-range → LSB tables, temp transfer fn. No logic. |
| `model.py` | `SimulatedMPU6050` — the sensor chain (bias → noise → quantise → saturate) + I²C-style reads. |
| `kinematics.py` | `specific_force_at_offset()` — what an off-CoM accelerometer feels during a tumble. |
| `basilisk_adapter.py` | **Optional** bridge to a live Basilisk `scStateOutMsg`. The only file that imports Basilisk; not imported by default. |

### Why the accelerometer needs a mounting offset

An accelerometer measures **specific force** (proper acceleration), not
coordinate acceleration. A spacecraft in orbit is in free fall, so at the
centre of mass the specific force is ≈ 0 (microgravity). The signal during a
tumble comes from the sensor's offset **r** from the CoM: the centripetal term
`ω × (ω × r)` plus the Euler term `ω̇ × r`. `kinematics.specific_force_at_offset`
builds that vector; `sample_from_motion()` wraps it for convenience.

## Usage

Standalone (no Basilisk):

```python
import numpy as np
from simulated_mpu6050 import SimulatedMPU6050, GyroRange

imu = SimulatedMPU6050(gyro_range=GyroRange.DPS_500)

reading = imu.sample(
    omega_rad_s=np.radians([0.0, 0.0, 5.0]),   # 5 deg/s spin about z
    specific_force_m_s2=[0.0, 0.0, 0.0],       # free fall
)
print(reading.gyro_dps)                # decoded rate a driver would compute
print(reading.gyro_raw)                # the raw int16 counts
print(imu.read_measurement_block())    # the 14 bytes an I²C burst read returns
print(hex(imu.who_am_i()))             # 0x68
```

Inside a Basilisk sim (optional bridge):

```python
from simulated_mpu6050 import SimulatedMPU6050, GyroRange
from simulated_mpu6050.basilisk_adapter import BasiliskMPU6050Adapter

imu = SimulatedMPU6050(gyro_range=GyroRange.DPS_500)
bridge = BasiliskMPU6050Adapter(imu, scObject.scStateOutMsg,
                                mount_offset_m=[0.04, 0.02, 0.03])
# each task step:
reading = bridge.step(currentSimNanos)
```

## Run it

```bash
# Demo: a decaying tumble, printed as gyro + accel readings
python examples/tumble_demo.py

# Tests (either runner)
python tests/test_mpu6050.py     # no pytest needed
pytest tests/
```

## Configuration knobs

`SimulatedMPU6050(...)`:

- `gyro_range` — `GyroRange.DPS_250 / 500 / 1000 / 2000` (sets LSB sensitivity + saturation)
- `accel_range` — `AccelRange.G_2 / 4 / 8 / 16`
- `gyro_bias_dps`, `accel_bias_g` — constant zero-rate / zero-g offsets (default 0)
- `gyro_noise_rms_dps`, `accel_noise_rms_g` — per-axis Gaussian noise RMS
- `temp_c` — reported die temperature when a sample doesn't override it
- `seed` — reproducible noise
