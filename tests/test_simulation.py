"""Short integration check, enabled in the Docker/Basilisk environment."""

import importlib.util
import tempfile
import unittest


class ModelOrientationTests(unittest.TestCase):
    def test_user_face_mapping_through_viewer_rotation(self):
        import numpy as np
        from math import cos, sin
        from perovsat import config

        # Viewer: Unity Euler(y, z, -x), composed Z then X then Y.
        a, b, c = config.VIZARD_MODEL_ROTATION_RAD
        rx = np.array([[1, 0, 0], [0, cos(b), -sin(b)], [0, sin(b), cos(b)]])
        ry = np.array([[cos(c), 0, sin(c)], [0, 1, 0], [-sin(c), 0, cos(c)]])
        rz = np.array([[cos(-a), -sin(-a), 0], [sin(-a), cos(-a), 0], [0, 0, 1]])
        # Vizard body (x,y,z) -> Unity (y,z,-x).
        basis = np.array([[0, 1, 0], [0, 0, 1], [-1, 0, 0]])
        correction = basis.T @ (ry @ rx @ rz) @ basis
        expected = np.array([[0, 1, 0], [0, 0, -1], [-1, 0, 0]])
        for sign in (-1, 1):
            for axis in range(3):
                np.testing.assert_allclose(correction @ (sign*np.eye(3)[:, axis]),
                                           sign*expected[:, axis], atol=1e-12)
        self.assertAlmostEqual(np.linalg.det(correction), 1.0)


@unittest.skipUnless(importlib.util.find_spec("Basilisk"), "Basilisk is not installed")
class SimulationTests(unittest.TestCase):
    def test_vizard_sun_vector_and_body_axes(self):
        from pathlib import Path
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(
                name="vectors", duration_s=.1, timestep_s=.025,
                record_period_s=.025, vizard=True, output_dir=directory,
            ))
            sim.run()
            settings = sim.viz.settings
            from perovsat import config
            models = list(settings.customModelList)
            self.assertEqual(len(models), 1)
            self.assertEqual(models[0].modelPath, config.VIZARD_MODEL_PATH)
            self.assertEqual(list(models[0].simBodiesToModify), ["PEROVSAT"])
            self.assertEqual(list(models[0].rotation), list(config.VIZARD_MODEL_ROTATION_RAD))
            self.assertEqual(list(models[0].offset), [0.0, 0.0, 0.0])
            self.assertEqual(list(models[0].scale), [1.0, 1.0, 1.0])
            self.assertEqual(settings.spacecraftCSon, 1)
            self.assertEqual(settings.showCSLabels, 1)
            self.assertEqual(settings.forceStartAtSpacecraftLocalView, 1)
            lines = list(settings.pointLineList)
            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0].fromBodyName, sim.scObject.ModelTag)
            self.assertEqual(lines[0].toBodyName,
                             sim.env.grav_factory.gravBodies["sun"].displayName)
            self.assertEqual(list(lines[0].lineColor), [255, 205, 64, 255])
            self.assertGreater((Path(directory) / "_VizFiles" / "vectors_UnityViz.bin").stat().st_size, 0)

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
