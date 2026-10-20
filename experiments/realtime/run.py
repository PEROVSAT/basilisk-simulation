"""Short paced run; optionally connect Vizard in Direct Communication mode."""

import argparse
from pathlib import Path

from perovsat.simulation import PerovSatSimulation, RunConfig


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--factor", type=float, default=1)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--viz-address", default="127.0.0.1",
                        help="Vizard host IP/hostname (no tcp:// prefix or port)")
    args = parser.parse_args()
    PerovSatSimulation(RunConfig(
        name="realtime", duration_s=args.duration, realtime=True,
        realtime_factor=args.factor, vizard_live=args.live,
        vizard_address=args.viz_address,
        output_dir=Path(__file__).resolve().parent / "output",
    )).run()


if __name__ == "__main__":
    main()
