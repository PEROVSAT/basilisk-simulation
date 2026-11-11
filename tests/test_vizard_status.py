"""Exercise native gauge bindings and physics equivalence with real Basilisk."""

import importlib.util
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np


@unittest.skipUnless(importlib.util.find_spec("Basilisk"), "Basilisk is not installed")
class VizardStatusTests(unittest.TestCase):
    def test_illumination_and_configured_cadence(self):
        from Basilisk.architecture import messaging
        from perovsat.vizard_status import VizardStatus

        battery = messaging.PowerStorageStatusMsg()
        eclipse = messaging.EclipseMsg()
        status = VizardStatus(battery, eclipse, .5)
        for shadow in (0.0, .25, 1.0):
            payload = messaging.EclipseMsgPayload()
            payload.shadowFactor = shadow
            eclipse.write(payload)
            status.UpdateState(0)
            self.assertEqual(status.illumination.currentValue, 100 * shadow)
        self.assertEqual(status.illumination.maxValue, 100)
        self.assertEqual(status.cadence.currentValue, 2)
        self.assertEqual(status.cadence.units, "Hz")
        self.assertEqual(status.illumination_state, 'Sunlight')
        self.assertIn('awaiting data', status.battery.units)

    def test_battery_states_units_and_power_balance(self):
        from Basilisk.architecture import messaging
        from perovsat.vizard_status import VizardStatus

        battery = messaging.PowerStorageStatusMsg()
        eclipse = messaging.EclipseMsg()
        panel = messaging.PowerNodeUsageMsg()
        sink = messaging.PowerNodeUsageMsg()
        for message, watts in ((panel, 3.0), (sink, -2.0)):
            payload = messaging.PowerNodeUsageMsgPayload()
            payload.netPower = watts
            message.write(payload)
        status = VizardStatus(battery, eclipse, .5, [panel], [sink])
        for soc, net, state in ((0, -1, 'Depleted'), (1, 1, 'Full'),
                                (.5, 1, 'Charging'), (.5, -1, 'Discharging'),
                                (.5, 0, 'Idle'), (0, 1, 'Charging'), (1, -1, 'Discharging')):
            with self.subTest(soc=soc, net=net):
                payload = messaging.PowerStorageStatusMsgPayload()
                payload.storageCapacity = 144000
                payload.storageLevel = soc * 144000
                payload.currentNetPower = net
                battery.write(payload)
                status.UpdateState(0)
                self.assertEqual(status.battery_state, state)
                self.assertEqual(status.battery.currentValue, soc * 100)
                self.assertEqual(status.energy.currentValue, soc * 40)
                self.assertEqual(status.energy.maxValue, 40)
                self.assertEqual(status.balance.currentValue, abs(net))
                self.assertIn('surplus' if net > 0 else 'deficit' if net < 0 else 'balanced',
                              status.balance.units)
                self.assertEqual('LOW' in status.battery.units, soc <= .2)
        self.assertEqual(status.generation.currentValue, 3)
        self.assertEqual(status.consumption.currentValue, 2)

    def test_measured_cadence_speed_lag_and_reset(self):
        from Basilisk.architecture import messaging
        from perovsat.vizard_status import VizardStatus

        status = VizardStatus(messaging.PowerStorageStatusMsg(), messaging.EclipseMsg(),
                              .5, realtime_factor=2)
        status.pacer = SimpleNamespace(elapsed_s=2.2, simulation_s=4)
        with patch('perovsat.vizard_status.time.perf_counter', side_effect=[10, 10.25, 10.5, 10.75, 11]):
            for tick in range(5):
                status.UpdateState(tick * 500_000_000)
        self.assertEqual(status.wall_cadence.currentValue, 4)
        self.assertEqual(status.speed.currentValue, 2)
        self.assertAlmostEqual(status.lag.currentValue, .2)
        self.assertIn('LATE', status.lag.units)
        status.Reset(0)
        self.assertEqual(status.wall_cadence.currentValue, 0)
        self.assertIn('warming up', status.speed.units)

    def test_compact_panel_omits_wall_clock_measurement(self):
        from Basilisk.architecture import messaging
        from perovsat.vizard_status import VizardStatus

        status = VizardStatus(messaging.PowerStorageStatusMsg(), messaging.EclipseMsg(),
                              .5, diagnostics=False)
        with patch('perovsat.vizard_status.time.perf_counter') as clock:
            status.UpdateState(0)
        clock.assert_not_called()
        self.assertEqual(len(status.gauges), 8)

    def test_native_gauges_update_without_changing_physics(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            baseline = PerovSatSimulation(RunConfig(
                duration_s=5, record_period_s=.5, output_dir=directory, soc_init=.4,
            ))
            expected = baseline.run()
            sim = PerovSatSimulation(RunConfig(
                duration_s=5, record_period_s=.5, output_dir=directory, soc_init=.4,
                vizard=True,
            ))
            actual = sim.run()
            status = sim.vizard_status
            self.assertAlmostEqual(status.battery.currentValue,
                                   100 * actual.power.stored_ws[-1] / sim.power.capacity_ws)
            self.assertEqual(status.battery.maxValue, 100)
            self.assertNotEqual(status.battery.currentValue, 40)
            self.assertAlmostEqual(status.illumination.currentValue,
                                   100 * sim.env.eclipse_out_msg.read().shadowFactor)
            self.assertEqual(len(sim.viz.scData[0].genericStorageList), 16)
            self.assertAlmostEqual(status.generation.currentValue, actual.power.generation_w[-1])
            self.assertTrue(any(setting.spacecraftName == 'PEROVSAT'
                                and setting.showGenericStoragePanel == 1
                                for setting in sim.viz.settings.instrumentGuiSettingsList))
            np.testing.assert_array_equal(actual.power.stored_ws, expected.power.stored_ws)
            np.testing.assert_array_equal(actual.attitude.sigma_BN, expected.attitude.sigma_BN)
            files = list(Path(directory).rglob('*_UnityViz.bin'))
            self.assertEqual(len(files), 1)
            self.assertGreater(files[0].stat().st_size, 0)
            contents = files[0].read_bytes()
            self.assertIn(b'Battery SOC', contents)
            self.assertIn(b'% | Charging', contents)
            self.assertIn(b'Power balance', contents)

    def test_panel_can_be_disabled(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(duration_s=.5, output_dir=directory,
                                               vizard=True, vizard_status_panel=False))
            sim.run()
            self.assertIsNone(sim.vizard_status)
            self.assertEqual(len(sim.viz.scData[0].genericStorageList), 0)
            self.assertEqual(len(sim.viz.settings.instrumentGuiSettingsList), 1)
            self.assertEqual(sim.viz.settings.instrumentGuiSettingsList[0].showGenericStoragePanel, -1)

    def test_orbit_serializes_eclipse_and_charge_transitions(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(duration_s=6000, record_period_s=10,
                                               output_dir=directory, vizard=True))
            log = sim.run()
            self.assertLess(log.power.shadow_factor.min(), .01)
            self.assertGreater(log.power.shadow_factor.max(), .99)
            self.assertLess(log.power.net_w.min(), 0)
            self.assertGreater(log.power.net_w.max(), 0)
            contents = next(Path(directory).rglob('*_UnityViz.bin')).read_bytes()
            for value in (b'% | Sunlight', b'% | Eclipse', b'% | Charging', b'% | Discharging',
                          b'W | surplus', b'W | deficit'):
                self.assertIn(value, contents)

    def test_status_survives_segmented_mission(self):
        from perovsat.mission import MissionRunner
        from perovsat.mission_config import MissionConfig

        with tempfile.TemporaryDirectory() as directory:
            runner = MissionRunner(MissionConfig(duration_s=6, record_period_s=1,
                segment_s=2, control_s=.5, realtime=False, vizard=True,
                output_dir=Path(directory) / 'mission'))
            result = runner.run()
            self.assertEqual(result['status'], 'complete')
            self.assertEqual(runner.sim.vizard_status.sim_time.currentValue, 6)
            self.assertGreater(runner.sim.vizard_status.energy.currentValue, 0)

    def test_paced_status_uses_measured_wall_time(self):
        from perovsat.simulation import PerovSatSimulation, RunConfig

        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(duration_s=5, output_dir=directory,
                vizard=True, realtime=True, realtime_factor=2))
            sim.run()
            status = sim.vizard_status
            self.assertIs(status.pacer, sim.pacer)
            self.assertAlmostEqual(status.wall_cadence.currentValue, 4, delta=1)
            self.assertAlmostEqual(status.speed.currentValue, 2, delta=.5)
            self.assertGreaterEqual(status.lag.currentValue, 0)
            self.assertEqual(len(status.gauges), 17)
