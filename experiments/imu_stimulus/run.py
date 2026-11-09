"""Short run that logs the gyro stimulus (body rates) every task tick."""

import argparse
from pathlib import Path

import numpy as np

from perovsat.imu import RAD_S_PER_RPM
from perovsat.simulation import PerovSatSimulation, RunConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--timestep", type=float, default=0.1)
    parser.add_argument("--print-every", type=int, default=10,
                        help="Print every Nth sample to the console (0 = log file only)")
    parser.add_argument("--rpm", type=float, default=None,
                        help="Initial spin rate about --axis in rpm (default: config.OMEGA_INIT_RADS)")
    parser.add_argument("--axis", choices=("x", "y", "z"), default="z",
                        help="Body axis for --rpm")
    parser.add_argument("--realtime", action="store_true")
    parser.add_argument("--bridge", metavar="HOST:PORT", default=None,
                        help="Send each sample to the HITL bridge TCP listener (implies --realtime)")
    parser.add_argument("--device-address", type=int, default=1,
                        help="Emulated MPU6050 participant address (default 1)")
    args = parser.parse_args()

    omega_init = None
    if args.rpm is not None:
        omega_init = [[0.0], [0.0], [0.0]]
        omega_init["xyz".index(args.axis)][0] = args.rpm * RAD_S_PER_RPM

    sim = PerovSatSimulation(RunConfig(
        name="imu_stimulus", duration_s=args.duration,
        timestep_s=args.timestep, record_period_s=args.timestep,
        omega_init=omega_init,
        imu_stimulus=True, imu_print_every=args.print_every,
        imu_bridge=args.bridge, imu_destination=args.device_address,
        realtime=args.realtime or args.bridge is not None,
        output_dir=Path(__file__).resolve().parent / "output",
    ))
    sim.run()
    print(f"IMU stimulus: {sim.imu.emitted} samples -> {sim.imu.path}")

    rows = np.loadtxt(sim.imu.path, ndmin=2)
    rpm = np.linalg.norm(rows[:, 2:5], axis=1)
    print(f"|gyro| rpm: start {rpm[0]:.6f}  end {rpm[-1]:.6f}  "
          f"min {rpm.min():.6f}  max {rpm.max():.6f}")


if __name__ == "__main__":
    main()
