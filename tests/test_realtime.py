"""Real Basilisk pacing and deterministic overload regression checks."""

import importlib.util
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import warnings

import numpy as np


@unittest.skipUnless(importlib.util.find_spec("Basilisk"), "Basilisk is not installed")
class RealtimeTests(unittest.TestCase):
    def test_vizard_modes(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig, vizSupport

        with tempfile.TemporaryDirectory() as directory:
            for save, live in ((True, False), (False, True), (True, True)):
                sim = PerovSatSimulation(RunConfig(
                    output_dir=directory, vizard=save, vizard_live=live))
                with patch.object(vizSupport, "vizFound", True), patch.object(
                        vizSupport, "enableUnityVisualization") as enable:
                    sim._setup_vizard()
                self.assertEqual(enable.call_args.kwargs["liveStream"], live)
                self.assertEqual(enable.call_args.kwargs["saveFile"] is not None, save)
            with patch.object(vizSupport, "vizFound", False):
                with self.assertRaisesRegex(RuntimeError, "unavailable"):
                    sim._setup_vizard()

    def test_pacing_preserves_physics(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            baseline = PerovSatSimulation(RunConfig(
                duration_s=2, timestep_s=.1, record_period_s=.1, output_dir=directory))
            a = baseline.run()
            self.assertIsNone(baseline.pacer)
            for factor in (1, 2):
                sim = PerovSatSimulation(RunConfig(
                    duration_s=2, timestep_s=.1, record_period_s=.1,
                    output_dir=directory, realtime=True, realtime_factor=factor))
                b = sim.run()
                self.assertAlmostEqual(sim.pacer.elapsed_s, 2 / factor, delta=.2)
                self.assertEqual(sim.pacer.simulation_s, 2)
                for x, y in ((a.t, b.t), (a.attitude.sigma_BN, b.attitude.sigma_BN),
                             (a.attitude.omega_B, b.attitude.omega_B),
                             (a.attitude.r_BN_N, b.attitude.r_BN_N),
                             (a.power.stored_ws, b.power.stored_ws), (a.mag.B_N, b.mag.B_N)):
                    np.testing.assert_array_equal(x, y)
                for tag in a.rods:
                    np.testing.assert_allclose(a.rods[tag].M, b.rods[tag].M, rtol=0, atol=1e-12)
                self.assertIn("Paced wall time:", Path(directory, "summary.txt").read_text())

    def test_overrun_warn_and_stop(self):
        from Basilisk.architecture import sysModel
        from perovsat.simulation import PerovSatSimulation, RunConfig

        class SlowModel(sysModel.SysModel):
            def UpdateState(self, current_time):
                if current_time:
                    time.sleep(.08)

        class SlowSimulation(PerovSatSimulation):
            def _build(self):
                super()._build()
                self.slow = SlowModel()
                self.scSim.AddModelToTask("simTask", self.slow, -50)

        with tempfile.TemporaryDirectory() as directory:
            for policy in ("warn", "stop"):
                sim = SlowSimulation(RunConfig(
                    duration_s=.06, timestep_s=.02, record_period_s=.02,
                    output_dir=directory, realtime=True, max_lag_s=.01,
                    overrun_policy=policy))
                if policy == "stop":
                    with self.assertRaisesRegex(RuntimeError, "Real-time lag"):
                        sim.run()
                    self.assertIn("interrupted or failed", Path(directory, "summary.txt").read_text())
                else:
                    with warnings.catch_warnings(record=True) as caught:
                        warnings.simplefilter("always")
                        log = sim.run()
                    self.assertEqual(len(caught), 1)
                    np.testing.assert_allclose(log.t, [0, .02, .04, .06])
                self.assertGreater(sim.pacer.overruns, 0)
                self.assertGreater(sim.pacer.max_work_s, .07)

    def test_interrupt_preserves_summary(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig
        from Basilisk.utilities import SimulationBaseClass

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(
                output_dir=directory, realtime=True, duration_s=1))
            with patch.object(SimulationBaseClass.SimBaseClass, "ExecuteSimulation",
                              side_effect=KeyboardInterrupt):
                with self.assertRaises(KeyboardInterrupt):
                    sim.run()
            self.assertIn("interrupted or failed", Path(directory, "summary.txt").read_text())
