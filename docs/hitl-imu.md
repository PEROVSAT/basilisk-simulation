# IMU stimulus to the FlatSat

`RunConfig(imu_stimulus=True)` adds the `imuStimulus` plugin. Each task tick it
reads the spacecraft state and fills a [perovsat-protocol](https://github.com/PEROVSAT/perovsat-protocol)
`psp_sample` with its IMU stimulus arm (`kind = PSP_SAMPLE_IMU_STIMULUS`):

| `psp_sample_imu_stimulus` field | Source |
|---|---|
| `sequence` | Tick counter from 0; skips the reserved `0xFFFFFFFF` |
| `gyro_rad_s` | `omega_BN_B`, body frame, float32 |
| `accel_m_s2` | `nonConservativeAccelpntB_B`: specific force, about 0 in free fall. It is 0 on the first tick, where Basilisk reports NaN before any step. |
| `temperature_present` | 0; Basilisk has no IMU temperature, so the emulator uses its 25 °C default |

`imu_stimulus.log` in the output directory records every sample, with gyro in rpm.

## Build

The plugin compiles perovsat-protocol from a sibling checkout,
`../perovsat-protocol`. That is the FlatSat west workspace layout, and the
Makefile mounts it into Docker. Without a sibling checkout, CMake fetches the
pinned commit in [CMakeLists.txt](../CMakeLists.txt). Set
`-DPEROVSAT_PROTOCOL_ROOT=...` to use another checkout.

## Send to the HITL bridge

Start [hitl-bridge](https://github.com/PEROVSAT/hitl-bridge) with the emulator
on its UART, for example:

```yaml
listen: 127.0.0.1:4242
devices:
  - name: imu0
    address: 1
    port: /dev/cu.usbmodem102
```

```sh
python -m hitl_bridge bridge.yaml --print-frames
```

Then run the experiment with the bridge's listen address:

```sh
make run SCRIPT=experiments/imu_stimulus/run.py ARGS='--rpm 1 --bridge host.docker.internal:4242'
# native venv:
PYTHONPATH=. .venv/bin/python experiments/imu_stimulus/run.py --rpm 1 --bridge 127.0.0.1:4242
```

`--bridge` paces the run in real time, so each tick sends one 50-byte Sample
frame. Basilisk is participant 252 and sends to device 1 (`--device-address`).
It sends `GetStatus` before the first tick and after the last, then logs every
frame the device returns, decoded by the protocol codec. The log goes to the
console and to `bridge.log`; `summary.txt` keeps both status replies.

Read the device status like this:

- `rejected_samples` and `rx_errors` unchanged: the emulator decoded and
  accepted every Basilisk sample.
- `sample_present=1 active_sample=N`: the emulator served sample `N` on I2C.
  A received sample stays pending until the OBC starts a burst read, so this
  shows only with the OBC wired to the emulator. With an OBC reading, each
  `log i2c_transaction ... served_sample=N` line names the Basilisk sample
  behind that read.
