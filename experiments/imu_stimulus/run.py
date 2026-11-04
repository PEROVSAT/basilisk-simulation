"""Short run that logs the gyro stimulus (body rates) every task tick."""

import argparse
from pathlib import Path

from perovsat.simulation import PerovSatSimulation, RunConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--timestep", type=float, default=0.1)
    parser.add_argument("--print-every", type=int, default=10,
                        help="Print every Nth sample to the console (0 = log file only)")
    parser.add_argument("--realtime", action="store_true")
    args = parser.parse_args()
    sim = PerovSatSimulation(RunConfig(
        name="imu_stimulus", duration_s=args.duration,
        timestep_s=args.timestep, record_period_s=args.timestep,
        imu_stimulus=True, imu_print_every=args.print_every,
        realtime=args.realtime,
        output_dir=Path(__file__).resolve().parent / "output",
    ))
    sim.run()
    print(f"IMU stimulus: {sim.imu.emitted} samples -> {sim.imu.path}")


if __name__ == "__main__":
    main()
