"""Scenario file validation; no Basilisk installation needed."""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from perovsat.realtime.scenario import Scenario, execution_settings, load_scenario

ROOT = Path(__file__).resolve().parents[1]


class ScenarioTests(unittest.TestCase):
    def load_payload(self, payload):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return load_scenario(path)

    def test_imu_scenario(self):
        scenario = self.load_payload({
            "timestep_s": 0.5,
            "duration_s": 1.5,
            "devices": ["imu"],
        })
        self.assertEqual(scenario, Scenario(0.5, 1.5, ("imu",)))

    def test_empty_devices(self):
        scenario = self.load_payload({
            "timestep_s": 1,
            "duration_s": 2,
            "devices": [],
        })
        self.assertEqual(scenario.devices, ())
        self.assertEqual(scenario.timestep_s, 1.0)
        self.assertEqual(scenario.duration_s, 2.0)

    def test_execution_settings(self):
        scenario = self.load_payload({
            "timestep_s": 0.5,
            "duration_s": 1.0,
            "devices": ["imu"],
        })
        settings = execution_settings(scenario)
        self.assertEqual(list(settings), [
            "name", "duration_s", "timestep_s", "record_period_s", "realtime",
        ])
        self.assertEqual(settings["name"], "realtime")
        self.assertEqual(settings["duration_s"], scenario.duration_s)
        self.assertEqual(settings["timestep_s"], scenario.timestep_s)
        self.assertEqual(settings["record_period_s"], scenario.timestep_s)
        self.assertIs(settings["realtime"], True)
        self.assertNotIn("epoch_utc", settings)

    def test_duration_equal_to_timestep(self):
        scenario = self.load_payload({
            "timestep_s": 0.5,
            "duration_s": 0.5,
            "devices": [],
        })
        self.assertEqual(scenario.duration_s, scenario.timestep_s)

    def test_missing_key(self):
        full = {"timestep_s": 0.5, "duration_s": 1.0, "devices": []}
        for key in full:
            payload = {name: value for name, value in full.items() if name != key}
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, key):
                    self.load_payload(payload)

    def test_unknown_key_is_named(self):
        for key in ("epoch_utc", "utc", "realtime", "listen"):
            payload = {
                "timestep_s": 0.5,
                "duration_s": 1.0,
                "devices": [],
                key: "no",
            }
            with self.subTest(key=key):
                with self.assertRaisesRegex(ValueError, f"unknown key: {key}"):
                    self.load_payload(payload)

    def test_unknown_device(self):
        with self.assertRaisesRegex(ValueError, "unknown device: magnetometer"):
            self.load_payload({
                "timestep_s": 0.5,
                "duration_s": 1.0,
                "devices": ["magnetometer"],
            })

    def test_duplicate_device(self):
        with self.assertRaisesRegex(ValueError, "duplicate device: imu"):
            self.load_payload({
                "timestep_s": 0.5,
                "duration_s": 1.0,
                "devices": ["imu", "imu"],
            })

    def test_devices_string_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "array"):
            self.load_payload({
                "timestep_s": 0.5,
                "duration_s": 1.0,
                "devices": "imu",
            })

    def test_non_positive_timestep(self):
        for timestep in (0, -1, float("nan"), float("inf")):
            with self.subTest(timestep=timestep):
                with self.assertRaisesRegex(ValueError, "timestep_s"):
                    self.load_payload({
                        "timestep_s": timestep,
                        "duration_s": 1.0,
                        "devices": [],
                    })

    def test_timestep_below_one_nanosecond(self):
        with self.assertRaisesRegex(ValueError, "nanosecond"):
            self.load_payload({
                "timestep_s": 1e-10,
                "duration_s": 1.0,
                "devices": [],
            })

    def test_duration_must_be_nanosecond_multiple(self):
        with self.assertRaisesRegex(ValueError, "duration_s"):
            self.load_payload({
                "timestep_s": 0.2,
                "duration_s": 0.5,
                "devices": [],
            })

    def test_wrong_json_types(self):
        cases = (
            {"timestep_s": True, "duration_s": 1, "devices": []},
            {"timestep_s": "0.5", "duration_s": 1, "devices": []},
            {"timestep_s": 0.5, "duration_s": 1, "devices": ["imu", 1]},
            [],
        )
        for payload in cases:
            with self.subTest(payload=payload):
                with self.assertRaises(ValueError):
                    self.load_payload(payload)

    def test_scenario_module_does_not_reference_basilisk(self):
        source = (ROOT / "perovsat/realtime/scenario.py").read_text(encoding="utf-8")
        self.assertNotIn("Basilisk", source)
        self.assertNotIn("mission_config", source)

    def test_cli_schema_errors_exit_2(self):
        env = os.environ.copy()
        env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "scenario.json"
            path.write_text(json.dumps({
                "timestep_s": 0.5,
                "duration_s": 1.0,
                "devices": [],
                "epoch_utc": "2026 JUN 21 12:00:00.0 (UTC)",
            }), encoding="utf-8")
            cases = {
                "unknown key": [str(path)],
                "missing file": [str(Path(directory) / "missing.json")],
                "bad json": None,
                "usage": [],
            }
            broken = Path(directory) / "broken.json"
            broken.write_text("{", encoding="utf-8")
            cases["bad json"] = [str(broken)]
            for name, args in cases.items():
                with self.subTest(name=name):
                    completed = subprocess.run(
                        [sys.executable, "-m", "perovsat.realtime", *args],
                        cwd=ROOT,
                        env=env,
                        capture_output=True,
                        text=True,
                        check=False,
                    )
                    self.assertEqual(completed.returncode, 2)
                    self.assertEqual(completed.stdout, "")
                    self.assertNotIn("Traceback", completed.stderr)
                    lines = completed.stderr.splitlines()
                    self.assertEqual(lines, [lines[0]])
                    if name == "unknown key":
                        self.assertIn("epoch_utc", lines[0])

    def test_pacer_is_separate_from_realtime_package(self):
        import importlib.util

        import perovsat.realtime as realtime

        self.assertFalse(hasattr(realtime, "RealtimePacer"))
        if importlib.util.find_spec("Basilisk") is None:
            with self.assertRaises(ModuleNotFoundError) as caught:
                import perovsat.pacing
            self.assertIn("Basilisk", str(caught.exception))
            return
        import perovsat.pacing as pacing
        self.assertIn("UpdateState", pacing.RealtimePacer.__dict__)

    def test_run_scenario_notes_and_failures(self):
        from types import ModuleType
        from unittest.mock import patch

        import perovsat
        from perovsat.realtime.runner import run_scenario

        epoch = (
            "Basilisk epoch: orbit and magnetic model only; not a FlatSat sample clock"
        )
        state = {"behavior": "success"}

        class Failed(RuntimeError):
            pass

        class FakeSimulation:
            last = None

            def __init__(self, cfg):
                FakeSimulation.last = cfg
                self.config = cfg

            def run(self):
                behavior = state["behavior"]
                if behavior == "raise-before-summary":
                    raise Failed("before summary")
                output = Path(self.config.output_dir)
                output.mkdir(parents=True, exist_ok=True)
                summary_path = output / "summary.txt"
                if behavior == "already-noted":
                    summary_path.write_text(
                        "Status: complete\nDevices: imu\n" + epoch + "\n",
                        encoding="utf-8",
                    )
                    return
                if behavior == "partial-note":
                    summary_path.write_text(
                        "Status: complete\nDevices: imu\n",
                        encoding="utf-8",
                    )
                    return
                if behavior == "no-newline":
                    summary_path.write_text("Status: complete", encoding="utf-8")
                    return
                summary_path.write_text("Status: complete\n", encoding="utf-8")
                if behavior == "raise-after-summary":
                    raise Failed("after summary")

        fake = ModuleType("perovsat.simulation")
        fake.PerovSatSimulation = FakeSimulation
        previous = sys.modules.get("perovsat.simulation")

        def restore_parent():
            if previous is None:
                if getattr(perovsat, "simulation", None) is fake:
                    del perovsat.simulation
            else:
                perovsat.simulation = previous

        self.addCleanup(restore_parent)
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(sys.modules, {"perovsat.simulation": fake}):
            path = Path(directory) / "scenario.json"
            summary = path.parent / "output" / "summary.txt"
            imu = Scenario(0.5, 1.0, ("imu",))
            empty = Scenario(0.5, 1.0, ())

            state["behavior"] = "success"
            run_scenario(imu, path)
            cfg = FakeSimulation.last
            self.assertEqual(cfg.name, "realtime")
            self.assertEqual(cfg.duration_s, imu.duration_s)
            self.assertEqual(cfg.timestep_s, imu.timestep_s)
            self.assertEqual(cfg.record_period_s, imu.timestep_s)
            self.assertIs(cfg.realtime, True)
            self.assertIsNone(cfg.epoch_utc)
            self.assertEqual(cfg.realtime_factor, 1.0)
            self.assertFalse(cfg.vizard)
            self.assertFalse(cfg.vizard_live)
            self.assertEqual(Path(cfg.output_dir), path.parent / "output")
            self.assertEqual(summary.read_text(encoding="utf-8").splitlines(), [
                "Status: complete", "Devices: imu", epoch,
            ])

            state["behavior"] = "success"
            run_scenario(empty, path)
            self.assertEqual(summary.read_text(encoding="utf-8").splitlines(), [
                "Status: complete", "Devices: none", epoch,
            ])

            state["behavior"] = "already-noted"
            run_scenario(imu, path)
            self.assertEqual(summary.read_text(encoding="utf-8").splitlines(), [
                "Status: complete", "Devices: imu", epoch,
            ])

            state["behavior"] = "partial-note"
            run_scenario(imu, path)
            self.assertEqual(summary.read_text(encoding="utf-8").splitlines(), [
                "Status: complete", "Devices: imu", epoch,
            ])

            state["behavior"] = "no-newline"
            run_scenario(imu, path)
            self.assertEqual(summary.read_text(encoding="utf-8").splitlines(), [
                "Status: complete", "Devices: imu", epoch,
            ])

            state["behavior"] = "raise-after-summary"
            with self.assertRaises(Failed):
                run_scenario(imu, path)
            self.assertEqual(summary.read_text(encoding="utf-8").splitlines(), [
                "Status: complete", "Devices: imu", epoch,
            ])

            state["behavior"] = "raise-before-summary"
            summary.unlink()
            with self.assertRaises(Failed):
                run_scenario(imu, path)
            self.assertFalse(summary.exists())


if __name__ == "__main__":
    unittest.main()
