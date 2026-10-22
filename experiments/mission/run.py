"""Run a fixed-duration mission; default: three days at wall-clock speed."""
import argparse
import signal

from perovsat.mission_config import MissionConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    duration = parser.add_mutually_exclusive_group()
    duration.add_argument('--days', type=float, default=3)
    duration.add_argument('--duration', type=float, help='duration in seconds (overrides days)')
    speed = parser.add_mutually_exclusive_group()
    speed.add_argument('--factor', type=float, default=1, help='simulated seconds per wall second')
    speed.add_argument('--unpaced', action='store_true', help='run as fast as possible')
    parser.add_argument('--timestep', type=float, default=.5)
    parser.add_argument('--record-period', type=float, default=10)
    parser.add_argument('--segment', type=float, default=300, help='seconds per telemetry file')
    parser.add_argument('--control', type=float, default=5, help='simulated seconds between stop checks')
    parser.add_argument('--output', help='new output directory; must not already exist')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--viz-address', default='127.0.0.1')
    parser.add_argument('--viz-timeout', type=float, default=120)
    parser.add_argument('--max-lag', type=float, default=.1)
    parser.add_argument('--overrun-policy', choices=('warn', 'stop'), default='warn')
    args = parser.parse_args(argv)
    try:
        cfg = MissionConfig(duration_s=args.duration if args.duration is not None else args.days*86400,
            timestep_s=args.timestep, record_period_s=args.record_period,
            segment_s=args.segment, control_s=args.control, output_dir=args.output,
            realtime=not args.unpaced, realtime_factor=args.factor,
            vizard_live=args.live, vizard_address=args.viz_address,
            vizard_timeout_s=args.viz_timeout, max_lag_s=args.max_lag,
            overrun_policy=args.overrun_policy)
    except ValueError as exc:
        parser.error(str(exc))
    from perovsat.mission import MissionRunner
    runner = MissionRunner(cfg)

    def stop(signum, frame):
        if runner._stop_requested() or runner.manifest.get('status') != 'running':
            raise KeyboardInterrupt
        runner.request_stop()
        print('Stop requested; saving at the next control boundary.', flush=True)

    previous = {sig: signal.signal(sig, stop) for sig in (signal.SIGINT, signal.SIGTERM)}
    print(f'Mission output: {runner.output_dir}', flush=True)
    try:
        result = runner.run()
    finally:
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    return 0 if result['status'] == 'complete' else 130


if __name__ == '__main__':
    raise SystemExit(main())
