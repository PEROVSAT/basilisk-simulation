"""Short integration check, enabled in the Docker/Basilisk environment."""

import importlib.util
import tempfile
import unittest


@unittest.skipUnless(importlib.util.find_spec("Basilisk"), "Basilisk is not installed")
class SimulationTests(unittest.TestCase):
    def test_short_run_and_single_execution(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(
                duration_s=2, timestep_s=.5, record_period_s=1,
                output_dir=directory,
            ))
            log = sim.run()
            self.assertGreater(len(log.t), 0)
            self.assertEqual(len(log.rods), 8)
            self.assertIs(sim.log, log)
            with self.assertRaisesRegex(RuntimeError, "one run"):
                sim.run()
