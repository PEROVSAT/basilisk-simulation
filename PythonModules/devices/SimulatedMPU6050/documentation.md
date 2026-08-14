# SimulatedMPU6050 — Work Log & Context

Context document for the SimulatedMPU6050 device: what it is, what has been
built so far, how it works, how to run it, and the decisions behind it. Written
as a running record so anyone (or any future session) can pick up with full
context. For the user-facing quick start, see [`README.md`](README.md); this
file is the "why and how it got here."

- **Status:** core measurement complete, tested, and wired into a live sim.
- **Committed in:** `7c32220` — *"Add SimulatedMPU6050 register-level IMU device + detumble wiring"* (author: Labib Muzahid).
- **Location:** `PythonModules/devices/SimulatedMPU6050/` (moved here from a
  top-level folder; still self-contained so it can become its own repo later).

---

## 1. Goal

Part of a set of **simulated flight devices** for PEROVSAT (a 1U CubeSat), built
toward eventual software-in-the-loop (SITL) testing. The lockstep/comms layer
between the devices and flight software is deferred to a later phase; the goal
for *now* is that each device **executes its core measurement**.

For the MPU-6050 (the CubeSat's 6-axis IMU: 3-axis gyroscope + 3-axis
accelerometer + temperature sensor), the core measurement is:

> **measure acceleration and tumbling parameters from the simulation** — i.e.
> given the true motion of the spacecraft, report what the real chip would
> report over I²C.

---

## 2. Design decisions (and why)

Three choices were made up front; they shape everything else:

1. **Subdirectory for now, own repo later.** Built as a self-contained package
   so splitting it into its own repository (the stated end goal for each device)
   is a clean lift, not a refactor. It has its own `README`, `pyproject.toml`,
   and `.gitignore`.

2. **Pure sensor model, no Basilisk dependency.** The core takes truth as plain
   SI inputs and returns sensor output. It imports nothing from Basilisk, so it
   is standalone-testable and portable. The bridge to a live sim is an
   **optional** adapter and is the *only* file that imports Basilisk — it is not
   even imported by the package `__init__`, so importing the sensor never pulls
   in Basilisk. This adapter is also the seam where the future SITL command
   interface will hook in.

3. **Register-level fidelity.** Not "roughly what a gyro reads" but the actual
   16-bit register values the real MPU-6050 produces: correct full-scale-range
   quantisation, saturation, zero-rate bias, and Gaussian noise. Faithful to the
   real part so downstream flight software is tested against realistic,
   imperfect data — which is where real failures hide.

---

## 3. What was built

### Package layout

```
SimulatedMPU6050/
├── README.md                       quick start + register-map notes
├── documentation.md                this file
├── pyproject.toml                  installable; Basilisk is an OPTIONAL extra
├── .gitignore                      keeps __pycache__/build artifacts out
├── simulated_mpu6050/              ← the pure, Basilisk-free core
│   ├── __init__.py                 public API (no Basilisk import)
│   ├── registers.py                datasheet constants only (no logic)
│   ├── model.py                    SimulatedMPU6050 — the sensor itself
│   ├── kinematics.py               off-CoM accelerometer physics
│   └── basilisk_adapter.py         OPTIONAL bridge (only file importing Basilisk)
├── tests/test_mpu6050.py           10 tests; runs with or without pytest
└── examples/tumble_demo.py         standalone decaying-tumble demo
```

### File responsibilities

- **`registers.py`** — I²C address `0x68`, `WHO_AM_I = 0x68`, the register map,
  the full-scale-range → LSB sensitivity tables (gyro ±250/500/1000/2000 °/s at
  131/65.5/32.8/16.4 LSB per °/s; accel ±2/4/8/16 g at 16384/8192/4096/2048 LSB
  per g), and the temperature transfer function (`°C = raw/340 + 36.53`). Pure
  constants, checkable against the datasheet at a glance.

- **`model.py`** — `SimulatedMPU6050`. The measurement chain and an I²C-style
  read interface. Emits a `Reading` dataclass (raw counts + decoded engineering
  units) and maintains a register bank so a caller can read it the way firmware
  would.

- **`kinematics.py`** — `specific_force_at_offset(omega, omega_dot, r, a_cm)`.
  An accelerometer measures **specific force** (proper acceleration), which at
  the centre of mass of a free-falling satellite is ≈ 0. The accel signal during
  a tumble comes from the sensor's offset from the CoM: the centripetal term
  `ω×(ω×r)` plus the Euler term `ω̇×r`. This builds that vector.

- **`basilisk_adapter.py`** — `BasiliskMPU6050Adapter`. Reads a live spacecraft
  state message (`omega_BN_B`, `omegaDot_BN_B`, `nonConservativeAccelpntB_B`),
  resolves the specific force at the mounting offset, optionally rotates into the
  sensor frame, and drives one `sample()` per step.

### The measurement chain (in `model.py`)

Each sample runs truth through the same sequence the real chip does:

```
true motion → + bias → + Gaussian noise → quantise at range sensitivity → saturate to int16 → pack into register bank
```

The engineering values returned are **decoded back from the counts**, not from
the input — so they reflect exactly what a driver reading the registers would
compute (quantisation loss included). Selecting a range writes the real
`GYRO_CONFIG` / `ACCEL_CONFIG` bits, and readback is available via
`who_am_i()`, `read_register(addr)`, `read_block(addr, n)`, and
`read_measurement_block()` (the 14-byte accel+temp+gyro burst).

---

## 4. Integration into a live sim

`sims/detumble_with_imu.py` (in the sim project, not in this package) wires the
sensor into the existing PMAC detumble run **without touching the shared
`base.py` or `detumble_experiment.py`**:

- It **subclasses** `DetumbleExperiment`.
- `build()` — after the base build, it attaches an `IMUMonitor` SysModel on its
  own task, driven by `BasiliskMPU6050Adapter`, sampling the live state each step.
- `postprocess()` — overlays the IMU gyro output on the true body rate
  (`imu_gyro_vs_truth.png`) and prints a residual summary.

This "additive integration" (subclass + override, never edit shared files) is
part of the pattern (see §7).

---

## 5. Verification

All green as of the commit:

- **Unit tests:** 10/10 pass (`tests/test_mpu6050.py`) — WHO_AM_I, gyro/accel
  sensitivity round-trips, range switching, saturation, temperature round-trip,
  bias offset, measurement-block/register consistency, centripetal kinematics,
  and noise scale.
- **Live-sim residual check:** feeding a known bias `[0.4, −0.3, 0.2] °/s` and
  `0.05 °/s` noise, the IMU-minus-truth residual recovered **exactly** that mean
  bias and std noise — confirming the sensor chain adds precisely what it should
  and the gyro tracks the 5.06 → ~4.12 °/s detumble.

---

## 6. Known behaviours / findings

- **The accelerometer reads mostly noise during a slow tumble — and that is
  physically correct.** At ~5–8 °/s with a ~5 cm mounting offset, the centripetal
  signal is ≈ 0.1 mg, well below the MPU-6050's ~8 mg noise floor. **The gyro is
  the tumbling instrument; the accelerometer cannot see a slow tumble.** It
  becomes useful for fast spins, larger offsets, or deployment/thruster
  transients. This is true of the real chip too.

- **`model.py` is a library, not a script — do not run it directly.** It uses a
  relative import (`from . import registers`), which Python only allows when the
  module is imported as part of a package. Running
  `python .../simulated_mpu6050/model.py` raises
  `ImportError: attempted relative import with no known parent package`. That is
  expected. Use the entry points in §8 instead.

- **IDE "move file → update imports" can break the standalone imports.** After
  moving the folder, an IDE refactor once rewrote the test/demo imports from
  `from simulated_mpu6050 import …` to a `PythonModules.devices.…` absolute path,
  which cannot resolve (no `__init__.py` at those levels). The fix was to restore
  the original relative-to-`sys.path` import. If imports break again, check that
  the entry files still use `from simulated_mpu6050 import …` after inserting the
  package root on `sys.path`.

---

## 7. The pattern this set (template for the other devices)

This device established a repeatable recipe now being reused for the other
simulated devices (`SimulatedAMU`, `SimulatedNSLEPS`, and the future
`SimulatedEyestar`):

1. **Pure measurement core** — "truth in → device output out", zero sim dependency.
2. **One thin optional adapter** — the sole Basilisk coupling; the SITL seam.
3. **Faithful-to-hardware fidelity** — real registers/units/imperfections.
4. **Standalone tests + a runnable demo** — provable without a full sim.
5. **Self-contained, own-repo-ready folder** — own README/pyproject/.gitignore.
6. **Additive integration** — subclass an experiment and override
   `build()`/`postprocess()`; never edit shared framework files.

---

## 8. How to run

From the repo root, with the project venv:

```bash
PY=.venv/bin/python
PKG=PythonModules/devices/SimulatedMPU6050

# Demo — decaying-tumble table (gyro / accel / temp)
$PY $PKG/examples/tumble_demo.py

# Tests — 10/10 pass
$PY $PKG/tests/test_mpu6050.py

# Live sim — IMU riding a real detumble run (writes imu_gyro_vs_truth.png)
$PY sims/detumble_with_imu.py
```

Use it from your own code:

```python
import sys; sys.path.insert(0, "PythonModules/devices/SimulatedMPU6050")
from simulated_mpu6050 import SimulatedMPU6050, GyroRange

imu = SimulatedMPU6050(gyro_range=GyroRange.DPS_500)
r = imu.sample(omega_rad_s=[0, 0, 0.09], specific_force_m_s2=[0, 0, 0])
print(r.gyro_dps, r.gyro_raw)          # decoded + raw counts
print(imu.read_measurement_block())    # the 14-byte I²C burst
```

---

## 9. Status & possible next steps

**Done:** core measurement, register-level fidelity, tests, standalone demo, and
live-sim integration — the MPU-6050 is complete for this phase.

**Not done (by design):** the SITL lockstep/command interface — deferred; the
adapter is the hook for it.

**Optional enhancements if wanted later:**
- A noise-free "ideal" output alongside the noisy one for comparison.
- Axis misalignment / cross-axis sensitivity, temperature-dependent bias.
- Recording IMU output through a Basilisk recorder (rather than the in-monitor list).
