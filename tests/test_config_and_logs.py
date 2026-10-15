"""Configuration and recorder regressions; no Basilisk installation needed."""

import unittest
from types import SimpleNamespace

import numpy as np

from perovsat import config
from perovsat.run_config import RunConfig
from perovsat.log import (
    EnvironmentRecorders, PmacRecorders, PowerRecorders,
    SimulationRecorders, SimLog,
)


class FakeRecorder(SimpleNamespace):
    def times(self):
        return np.asarray(self.timestamps)


def recorder(**fields):
    return FakeRecorder(timestamps=[0, 1_000_000_000], **fields)


def make_log():
    vector = np.zeros((2, 3))
    return SimLog(SimulationRecorders(
        scState=recorder(sigma_BN=vector, omega_BN_B=vector, r_BN_N=vector),
        environment=EnvironmentRecorders(
            mag=recorder(magField_N=vector), eclipse=recorder(shadowFactor=[1, 0])),
        pmac=PmacRecorders(pmTorque=recorder(torqueRequestBody=vector)),
        power=PowerRecorders(
            battery=recorder(storageLevel=[80, 79]),
            panels={"panel": recorder(netPower=[2, 0])},
            sinks={"load": recorder(netPower=[-1, -1])}),
    ), battery_capacity_ws=100)


class ConfigurationTests(unittest.TestCase):
    def test_run_config_rejects_invalid_parameters(self):
        for kwargs in (
            {"duration_s": 0}, {"timestep_s": -1},
            {"record_period_s": float("nan")}, {"soc_init": 1.1},
            {"sigma_init": [0, 0]}, {"omega_init": [0, float("inf"), 0]},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                RunConfig(**kwargs)

    def test_run_config_revalidation(self):
        cfg = RunConfig()
        cfg.timestep_s = 0
        with self.assertRaises(ValueError):
            cfg.validate()

    def test_vehicle_defaults(self):
        config.validate_vehicle()

    def test_invalid_values(self):
        constructors = (
            lambda: config.Panel((1, 0, 0), -1, .2),
            lambda: config.Panel((2, 0, 0), 1, .2),
            lambda: config.DeviceState("bad", float("nan"), .5),
            lambda: config.DeviceState("bad", 1, float("nan")),
            lambda: config.Device("bad", 1.5, ()),
            lambda: config.HystMaterial(.75, .8, 5),
            lambda: config.HystMaterial(.75, .1, 0),
            lambda: config.Rod("bad", (1, 0, 0), "missing"),
        )
        for constructor in constructors:
            with self.subTest(constructor=constructor), self.assertRaises(ValueError):
                constructor()

    def test_average_load(self):
        device = config.Device("example", 2, (config.DeviceState("on", 4, .25),))
        self.assertEqual(device.average_power_w, 2)


class LoggingTests(unittest.TestCase):
    def test_power_signs_and_soc(self):
        log = make_log()
        log.validate()
        np.testing.assert_allclose(log.power.net_w, [1, -1])
        np.testing.assert_allclose(log.power.consumption_w, [1, 1])
        np.testing.assert_allclose(log.power.soc, [.8, .79])

    def test_missing_field_is_error(self):
        log = make_log()
        del log._recorders.power.panels["panel"].netPower
        with self.assertRaisesRegex(ValueError, "missing field"):
            log.validate()

    def test_sample_mismatch_is_error(self):
        log = make_log()
        log._recorders.power.panels["panel"].netPower = [2]
        with self.assertRaisesRegex(ValueError, "sample count"):
            log.validate()
        with self.assertRaises(ValueError):
            _ = log.power.generation_w

    def test_timestamp_mismatch_is_error(self):
        log = make_log()
        log._recorders.power.panels["panel"].timestamps = [0, 2_000_000_000]
        with self.assertRaisesRegex(ValueError, "timestamps"):
            log.validate()

    def test_nonfinite_samples_are_error(self):
        log = make_log()
        log._recorders.power.battery.storageLevel = [80, float("nan")]
        with self.assertRaisesRegex(ValueError, "nonfinite"):
            log.validate()


if __name__ == "__main__":
    unittest.main()
