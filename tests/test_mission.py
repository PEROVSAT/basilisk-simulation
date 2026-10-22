"""Acceptance tests written before implementing the mission runner."""
import importlib.util
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import time
import signal
import unittest
from unittest.mock import patch

import numpy as np

from perovsat.mission_config import MissionConfig


class MissionConfigTests(unittest.TestCase):
    def test_defaults(self):
        cfg = MissionConfig()
        self.assertEqual(cfg.duration_s, 3 * 86400)
        self.assertTrue(cfg.realtime)

    def test_invalid_timing(self):
        for kw in ({'duration_s': .3}, {'record_period_s': .3},
                   {'segment_s': 0}, {'segment_s': 11}, {'control_s': .3}):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                MissionConfig(**kw)


@unittest.skipUnless(importlib.util.find_spec('Basilisk'), 'Basilisk is not installed')
class MissionTests(unittest.TestCase):
    def cfg(self, path, **kwargs):
        values = dict(duration_s=6, timestep_s=.5, record_period_s=1,
                      segment_s=2, control_s=.5, realtime=False, output_dir=path)
        values.update(kwargs)
        return MissionConfig(**values)

    def test_paced_runs_keep_clock_across_segments(self):
        from perovsat.mission import MissionRunner
        for factor in (1, 2):
            with self.subTest(factor=factor), tempfile.TemporaryDirectory() as tmp:
                runner = MissionRunner(self.cfg(Path(tmp)/'mission', duration_s=4,
                    realtime=True, realtime_factor=factor))
                result = runner.run()
                self.assertAlmostEqual(result['timing']['paced_wall_s'], 4/factor, delta=.3)
                self.assertEqual(result['status'], 'complete')

    @unittest.skipIf(sys.platform == 'win32', 'POSIX signal test')
    def test_cli_sigterm_preserves_partial_results(self):
        from experiments.mission.analyze import validate_output
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp)/'mission'
            process = subprocess.Popen([sys.executable, '-m', 'experiments.mission.run',
                '--duration', '60', '--control', '.5', '--record-period', '.5',
                '--segment', '1', '--output', str(output)],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            try:
                deadline = time.monotonic()+30
                while not list(output.glob('telemetry-*.npz')):
                    if process.poll() is not None or time.monotonic() >= deadline:
                        self.fail('CLI did not produce telemetry')
                    time.sleep(.05)
                process.send_signal(signal.SIGTERM)
                self.assertEqual(process.wait(timeout=10), 130)
                result = validate_output(output)
                self.assertEqual(result['status'], 'interrupted')
                self.assertGreater(result['samples'], 0)
                self.assertLess(result['completed_s'], 60)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait()

    def test_final_partial_segment_and_saved_validation(self):
        from perovsat.mission import MissionRunner
        from experiments.mission.analyze import validate_output
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionRunner(self.cfg(Path(tmp)/'mission', duration_s=3.5))
            runner.run()
            result = validate_output(runner.output_dir)
            self.assertEqual(result['samples'], 4)
            self.assertEqual(result['segments'], 2)
            self.assertEqual(result['completed_s'], 3.5)
            segment = runner.output_dir/runner.manifest['segments'][1]['file']
            with np.load(segment) as data:
                arrays = {key: data[key] for key in data.files}
            arrays['time_ns'][0] = 0
            np.savez(segment, **arrays)
            with self.assertRaisesRegex(ValueError, 'timestamps'):
                validate_output(runner.output_dir)

    def test_fractional_endpoint_uses_nanosecond_precision(self):
        from perovsat.mission import MissionRunner
        from experiments.mission.analyze import validate_output
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionRunner(self.cfg(Path(tmp)/'mission', duration_s=.3,
                timestep_s=.1, control_s=.1, record_period_s=.1, segment_s=.2))
            runner.run()
            self.assertEqual(validate_output(runner.output_dir)['samples'], 4)

    def test_segmented_matches_one_shot(self):
        from perovsat.mission import MissionRunner
        from perovsat.simulation import PerovSatSimulation, RunConfig
        with tempfile.TemporaryDirectory() as tmp:
            baseline = PerovSatSimulation(RunConfig(duration_s=6,
                output_dir=Path(tmp)/'baseline')).run()
            runner = MissionRunner(self.cfg(Path(tmp)/'mission'))
            manifest = runner.run()
            self.assertEqual(manifest['status'], 'complete')
            self.assertEqual(manifest['completed_s'], 6)
            self.assertEqual(manifest['samples'], 7)
            self.assertLessEqual(manifest['max_buffer_samples'], 3)
            chunks = []
            for item in manifest['segments']:
                with np.load(runner.output_dir/item['file'], allow_pickle=False) as data:
                    chunks.append({key: data[key] for key in data.files})
            for key, expected in [('t_s', baseline.t),
                                  ('sigma_BN', baseline.attitude.sigma_BN),
                                  ('omega_B_rad_s', baseline.attitude.omega_B),
                                  ('position_N_m', baseline.attitude.r_BN_N),
                                  ('battery_J', baseline.power.stored_ws)]:
                np.testing.assert_array_equal(np.concatenate([c[key] for c in chunks]), expected)
            self.assertIn('vehicle', manifest)
            self.assertIn('source', manifest)

    def test_existing_directory_is_preserved(self):
        from perovsat.mission import MissionRunner
        with tempfile.TemporaryDirectory() as tmp:
            keep = Path(tmp)/'keep.txt'
            keep.write_text('keep')
            with self.assertRaises(FileExistsError):
                MissionRunner(self.cfg(Path(tmp))).run()
            self.assertEqual(keep.read_text(), 'keep')

    def test_graceful_stop_saves_partial_results(self):
        from perovsat.mission import MissionRunner
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionRunner(self.cfg(Path(tmp)/'mission'))
            with patch.object(runner, '_stop_requested',
                              side_effect=lambda: runner.completed_s >= 2.5):
                manifest = runner.run()
            self.assertEqual(manifest['status'], 'interrupted')
            self.assertEqual(manifest['completed_s'], 2.5)
            self.assertEqual(manifest['samples'], 3)
            self.assertTrue(manifest['segments'])

    def test_write_failure_preserves_prior_segments(self):
        from perovsat.mission import MissionRunner
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionRunner(self.cfg(Path(tmp)/'mission'))
            original = runner._save_segment
            def fail_second():
                if runner.manifest['segments']:
                    raise OSError('injected disk failure')
                return original()
            with patch.object(runner, '_save_segment', side_effect=fail_second):
                with self.assertRaisesRegex(OSError, 'injected disk failure'):
                    runner.run()
            saved = json.loads((runner.output_dir/'manifest.json').read_text())
            self.assertEqual(saved['status'], 'failed')
            self.assertEqual(len(saved['segments']), 1)
            self.assertTrue((runner.output_dir/saved['segments'][0]['file']).exists())

    def test_execution_failure_preserves_saved_segments(self):
        from perovsat.mission import MissionRunner
        with tempfile.TemporaryDirectory() as tmp:
            runner = MissionRunner(self.cfg(Path(tmp)/'mission'))
            original = runner._save_segment
            def save_then_break_execution():
                original()
                runner.sim.scSim.ExecuteSimulation = lambda: (_ for _ in ()).throw(
                    RuntimeError('injected execution failure'))
            with patch.object(runner, '_save_segment', side_effect=save_then_break_execution):
                with self.assertRaisesRegex(RuntimeError, 'injected execution failure'):
                    runner.run()
            saved = json.loads((runner.output_dir/'manifest.json').read_text())
            self.assertEqual(saved['status'], 'failed')
            self.assertEqual(saved['completed_s'], 2)
            self.assertEqual(saved['samples'], 3)
