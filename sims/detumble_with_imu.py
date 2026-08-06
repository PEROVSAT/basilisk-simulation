"""
detumble_with_imu.py
The PMAC detumble run with a SimulatedMPU6050 riding along, so you can actually
*see* the IMU do its core measurement inside a live Basilisk sim.

It subclasses the existing DetumbleExperiment (so all the spacecraft / orbit /
magnet / rod / power wiring is inherited unchanged) and only adds:
  * build()       -> attaches an IMU monitor task that samples the sensor each
                     step from the live spacecraft state (via the package's
                     BasiliskMPU6050Adapter),
  * postprocess() -> overlays the IMU gyro output on the true body rate and
                     prints a residual summary (recovered bias + noise).

Neither base.py nor detumble_experiment.py is touched.

Run:  python sims/detumble_with_imu.py
Writes: imu_gyro_vs_truth.png  (plus the usual detumble plots)
"""

import os
import sys

import numpy as np

from Basilisk.architecture import sysModel
from Basilisk.utilities import macros

from detumble_experiment import DetumbleExperiment

# Make the standalone SimulatedMPU6050 package importable. It's self-contained
# (relative imports internally), so it just needs its folder on sys.path; this
# is the only coupling point. Currently lives under PythonModules/devices/.
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_root, "PythonModules", "devices", "SimulatedMPU6050"))
from simulated_mpu6050 import SimulatedMPU6050, GyroRange
from simulated_mpu6050.basilisk_adapter import BasiliskMPU6050Adapter


class IMUMonitor(sysModel.SysModel):
    """Drives the IMU adapter once per task step, logs the readings, and prints
    a subsampled line to the console so you can watch it live."""

    def __init__(self, adapter, print_period_s):
        super().__init__()
        self.ModelTag = "IMUMonitor"
        self.adapter = adapter
        self.print_period_s = print_period_s
        self._next_print_s = 0.0
        self.t, self.gyro, self.accel, self.temp = [], [], [], []

    def UpdateState(self, currentSimNanos):
        reading = self.adapter.step(currentSimNanos)
        if reading is None:
            return
        t_s = currentSimNanos * macros.NANO2SEC
        self.t.append(t_s)
        self.gyro.append(np.array(reading.gyro_dps))
        self.accel.append(np.array(reading.accel_g))
        self.temp.append(reading.temp_c)
        if t_s >= self._next_print_s:
            g = reading.gyro_dps
            print(f"[IMU] t={t_s:8.1f}s  gyro=[{g[0]:+7.3f}, {g[1]:+7.3f}, "
                  f"{g[2]:+7.3f}] deg/s  |g|={np.linalg.norm(g):6.3f}  "
                  f"temp={reading.temp_c:5.1f}C")
            self._next_print_s += self.print_period_s


class DetumbleWithIMU(DetumbleExperiment):
    # Short by default so it's a quick, watchable smoke test; bump for a real run.
    SIM_DURATION_S = 600.0
    INCLUDE_VIZARD = False

    # ---- IMU config ----
    IMU_GYRO_RANGE = GyroRange.DPS_250          # 5 deg/s tumble << 250 dps -> best resolution
    IMU_BIAS_DPS = [0.4, -0.3, 0.2]             # a deliberate zero-rate offset to recover
    IMU_MOUNT_OFFSET_M = [0.04, 0.02, 0.03]     # ~5 cm off the CoM in a 1U
    IMU_SAMPLE_PERIOD_S = 2.0                    # IMU logs on its own (coarser) task
    IMU_PRINT_PERIOD_S = 60.0

    def build(self):
        super().build()   # full sim assembled; self.scObject etc. now exist

        imu = SimulatedMPU6050(gyro_range=self.IMU_GYRO_RANGE,
                               gyro_bias_dps=self.IMU_BIAS_DPS, seed=7)
        adapter = BasiliskMPU6050Adapter(imu, self.scObject.scStateOutMsg,
                                         mount_offset_m=self.IMU_MOUNT_OFFSET_M)

        # Keep hard references (Basilisk's scheduler calls back via raw pointer;
        # see the same note in base.py's _setup_orientation_printout).
        self.imu = imu
        self.imu_monitor = IMUMonitor(adapter, self.IMU_PRINT_PERIOD_S)
        self.imu_task = self.scSim.CreateNewTask(
            "imuTask", macros.sec2nano(self.IMU_SAMPLE_PERIOD_S))
        self.dynProcess.addTask(self.imu_task)
        self.scSim.AddModelToTask("imuTask", self.imu_monitor)

    def postprocess(self):
        super().postprocess()
        self._plot_imu_vs_truth()

    def _plot_imu_vs_truth(self):
        import matplotlib.pyplot as plt

        t = np.array(self.imu_monitor.t)
        if len(t) == 0:
            print("[IMU] no samples recorded (SPICE never populated?)")
            return
        gyro = np.array(self.imu_monitor.gyro)                       # (N,3) deg/s

        truth_t = np.array(self.recorders["scState"].times()) * 1e-9
        truth_w = np.degrees(np.array(self.recorders["scState"].omega_BN_B))  # deg/s

        fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True)
        colors = ["tab:blue", "tab:orange", "tab:green"]
        for i, lbl in enumerate("xyz"):
            ax1.plot(truth_t, truth_w[:, i], color=colors[i], lw=1.2,
                     label=f"truth ω{lbl}")
            ax1.plot(t, gyro[:, i], ".", color=colors[i], ms=3, alpha=0.45,
                     label=f"IMU ω{lbl}")
        ax1.set_ylabel("body rate (deg/s)")
        ax1.set_title("SimulatedMPU6050 gyro vs. true body rate")
        ax1.grid(True, alpha=0.3)
        ax1.legend(ncol=3, fontsize=8)

        ax2.plot(truth_t, np.linalg.norm(truth_w, axis=1), "k-", lw=1.2,
                 label="truth |ω|")
        ax2.plot(t, np.linalg.norm(gyro, axis=1), ".", color="tab:red", ms=3,
                 alpha=0.5, label="IMU |ω|")
        ax2.set_xlabel("time (s)")
        ax2.set_ylabel("|ω| (deg/s)")
        ax2.grid(True, alpha=0.3)
        ax2.legend()

        plt.tight_layout()
        out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "imu_gyro_vs_truth.png")
        plt.savefig(out, dpi=200)
        plt.close(fig)

        # Residual = IMU - truth, sampled at the IMU times. Recovers the bias
        # we injected (mean) and the sensor noise (std), proving the chain.
        truth_at_imu = np.vstack([np.interp(t, truth_t, truth_w[:, i])
                                  for i in range(3)]).T
        resid = gyro - truth_at_imu
        print("\n" + "=" * 60)
        print("IMU vs TRUTH (gyro residual = IMU - truth)")
        print("=" * 60)
        print(f"samples: {len(t)}")
        print(f"mean residual (deg/s): [{resid[:,0].mean():+.3f}, "
              f"{resid[:,1].mean():+.3f}, {resid[:,2].mean():+.3f}]  "
              f"(injected bias {self.IMU_BIAS_DPS})")
        print(f"std  residual (deg/s): [{resid[:,0].std():.3f}, "
              f"{resid[:,1].std():.3f}, {resid[:,2].std():.3f}]  (sensor noise)")
        print(f"plot: {out}")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    DetumbleWithIMU().run()
