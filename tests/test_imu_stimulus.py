"""IMU stimulus emitter: truth extraction, sequencing, and no physics feedback."""

import importlib.util
from pathlib import Path
import tempfile
import unittest

import numpy as np


class ImuConfigTests(unittest.TestCase):
    def test_print_every_validation(self):
        from perovsat.run_config import RunConfig

        for bad in (-1, 1.5, True):
            with self.assertRaises(ValueError):
                RunConfig(imu_print_every=bad)
        RunConfig(imu_print_every=0)


@unittest.skipUnless(importlib.util.find_spec("Basilisk"), "Basilisk is not installed")
class ImuStimulusTests(unittest.TestCase):
    def test_gyro_matches_body_rate_and_sequence_increments(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(
                duration_s=2, timestep_s=.1, record_period_s=.1,
                output_dir=directory, imu_stimulus=True))
            log = sim.run()
            rows = np.loadtxt(Path(directory, "imu_stimulus.log"), ndmin=2)

            self.assertEqual(sim.imu.emitted, len(log.t))
            self.assertEqual(len(rows), len(log.t))
            np.testing.assert_allclose(rows[:, 0], log.t, rtol=0, atol=1e-9)
            np.testing.assert_array_equal(rows[:, 1], np.arange(len(rows)))
            np.testing.assert_allclose(rows[:, 2:5], log.attitude.omega_B, rtol=1e-8, atol=0)
            np.testing.assert_array_equal(sim.imu.last.gyro_rad_s, log.attitude.omega_B[-1])
            self.assertIn("IMU stimulus samples: 21",
                          Path(directory, "summary.txt").read_text())

    def test_emitter_does_not_change_physics(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            runs = [
                PerovSatSimulation(RunConfig(
                    duration_s=2, timestep_s=.1, record_period_s=.1,
                    output_dir=directory, imu_stimulus=imu)).run()
                for imu in (False, True)
            ]
            a, b = runs
            for x, y in ((a.t, b.t), (a.attitude.sigma_BN, b.attitude.sigma_BN),
                         (a.attitude.omega_B, b.attitude.omega_B),
                         (a.attitude.r_BN_N, b.attitude.r_BN_N)):
                np.testing.assert_array_equal(x, y)

    def test_unlinked_reader_fails_on_reset(self):
        from perovsat.imu import ImuStimulusEmitter
        from perovsat.run_config import RunConfig

        with tempfile.TemporaryDirectory() as directory:
            emitter = ImuStimulusEmitter(RunConfig(), Path(directory))
            with self.assertRaisesRegex(RuntimeError, "not linked"):
                emitter.Reset(0)
