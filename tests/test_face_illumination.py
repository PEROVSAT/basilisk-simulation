"""Independent attitude geometry and native solar-power checks for face gauges."""

import csv
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest

import numpy as np


@unittest.skipUnless(importlib.util.find_spec('Basilisk'), 'Basilisk is not installed')
class FaceIlluminationTests(unittest.TestCase):
    def test_known_geometry_eclipse_and_relative_sun_position(self):
        from Basilisk.architecture import messaging
        from perovsat.vizard_status import VizardStatus

        battery = messaging.PowerStorageStatusMsg()
        eclipse = messaging.EclipseMsg()
        spacecraft = messaging.SCStatesMsg()
        sun = messaging.SpicePlanetStateMsg()
        status = VizardStatus(battery, eclipse, .5, state_message=spacecraft, sun_message=sun)
        state = messaging.SCStatesMsgPayload()
        state.r_BN_N = [100, 200, 300]
        spacecraft.write(state)
        light = messaging.SpicePlanetStateMsgPayload()
        light.PositionVector = [1100, 200, 300]
        sun.write(light)
        shadow = messaging.EclipseMsgPayload()
        for visibility in (1.0, .25, 0.0):
            shadow.shadowFactor = visibility
            eclipse.write(shadow)
            status.UpdateState(0)
            for face, gauge in status.face_illumination.items():
                self.assertAlmostEqual(gauge.currentValue, 100 * visibility if face == '+X' else 0)
        shadow.shadowFactor = 1
        eclipse.write(shadow)
        state.sigma_BN = [0, np.tan(np.pi / 8), 0]
        spacecraft.write(state)
        status.UpdateState(0)
        self.assertAlmostEqual(status.face_illumination['+Z'].currentValue, 100)
        self.assertAlmostEqual(status.face_illumination['+X'].currentValue, 0)
        light.PositionVector = state.r_BN_N
        sun.write(light)
        status.UpdateState(0)
        self.assertTrue(all(gauge.units == '% | unavailable'
                            for gauge in status.face_illumination.values()))

    def test_random_timesteps_against_geometry_and_native_panels(self):
        from Basilisk.architecture import sysModel
        from Basilisk.simulation import simpleSolarPanel
        from Basilisk.utilities import macros
        from perovsat import config
        from perovsat.simulation import PerovSatSimulation, RunConfig

        normals = {'+X': [1, 0, 0], '-X': [-1, 0, 0], '+Y': [0, 1, 0],
                   '-Y': [0, -1, 0], '+Z': [0, 0, 1], '-Z': [0, 0, -1]}
        seed = 20261103
        sample_ticks = set(np.random.default_rng(seed).choice(12001, size=256, replace=False).tolist())
        rows = []
        with tempfile.TemporaryDirectory() as directory:
            sim = PerovSatSimulation(RunConfig(duration_s=6000, timestep_s=.5,
                record_period_s=10, output_dir=directory, vizard=True))
            sim._build()
            references = {}
            for face, normal in normals.items():
                panel = simpleSolarPanel.SimpleSolarPanel()
                panel.ModelTag = f'reference_{face}'
                panel.setPanelParameters(normal, 1.0, 1.0)
                panel.stateInMsg.subscribeTo(sim.scObject.scStateOutMsg)
                panel.sunInMsg.subscribeTo(sim.env.sun_state_msg)
                panel.sunEclipseInMsg.subscribeTo(sim.env.eclipse_out_msg)
                sim.scSim.AddModelToTask('simTask', panel, -10)
                references[face] = panel

            class Observer(sysModel.SysModel):
                def UpdateState(self, current_time):
                    tick = round(current_time / 500_000_000)
                    eclipse = sim.env.eclipse_out_msg.read().shadowFactor
                    if tick not in sample_ticks and not 0 < eclipse < 1:
                        return
                    state = sim.scObject.scStateOutMsg.read()
                    sun = sim.env.sun_state_msg.read()
                    relative = np.asarray(sun.PositionVector) - np.asarray(state.r_BN_N)
                    distance = np.linalg.norm(relative)
                    sun_direction = relative / distance
                    sigma = np.asarray(state.sigma_BN)
                    magnitude = np.linalg.norm(sigma)
                    angle = 4 * np.arctan(magnitude)
                    axis = sigma / magnitude if magnitude else np.array([1., 0., 0.])
                    flux = 1372.5398 * (149597870693.0 / distance) ** 2
                    for face, normal in normals.items():
                        normal = np.asarray(normal)
                        inertial_normal = (normal * np.cos(angle)
                            + np.cross(axis, normal) * np.sin(angle)
                            + axis * np.dot(axis, normal) * (1 - np.cos(angle)))
                        expected = 100 * eclipse * max(0.0, np.dot(inertial_normal, sun_direction))
                        reference_flux = references[face].nodePowerOutMsg.read().netPower
                        actual_panel = sim.power.panels.get(face)
                        actual_w = actual_panel.nodePowerOutMsg.read().netPower if actual_panel else None
                        expected_w = (expected / 100 * flux * config.PANELS[face].area_m2
                                      * config.PANELS[face].efficiency if actual_panel else None)
                        rows.append(dict(time_s=current_time * 1e-9, face=face,
                            random_sample=tick in sample_ticks, eclipse_visibility=eclipse,
                            displayed_percent=sim.vizard_status.face_illumination[face].currentValue,
                            geometry_percent=float(expected), native_percent=100 * reference_flux / flux,
                            native_irradiance_w_m2=reference_flux, actual_panel_w=actual_w,
                            expected_panel_w=expected_w))

            observer = Observer()
            sim.scSim.AddModelToTask('simTask', observer, -50)
            sim.scSim.InitializeSimulation()
            sim.scSim.ConfigureStopTime(macros.sec2nano(6000))
            sim.scSim.ExecuteSimulation()
            sim.log.validate()
            contents = next(Path(directory).rglob('*_UnityViz.bin')).read_bytes()
            for face in normals:
                self.assertIn(f'Face {face} illumination'.encode(), contents)

        errors_geometry = [abs(row['displayed_percent'] - row['geometry_percent']) for row in rows]
        errors_native = [abs(row['displayed_percent'] - row['native_percent']) for row in rows]
        errors_power = [abs(row['actual_panel_w'] - row['expected_panel_w']) for row in rows
                        if row['actual_panel_w'] is not None]
        self.assertEqual(len({row['time_s'] for row in rows if row['random_sample']}), 256)
        self.assertTrue(any(row['eclipse_visibility'] == 0 for row in rows))
        self.assertTrue(any(row['eclipse_visibility'] == 1 for row in rows))
        self.assertTrue(any(0 < row['eclipse_visibility'] < 1 for row in rows))
        self.assertLess(max(errors_geometry), 1e-10)
        self.assertLess(max(errors_native), 1e-10)
        self.assertLess(max(errors_power), 1e-11)
        self.assertTrue(all(0 <= row['displayed_percent'] <= 100 for row in rows))
        summary = dict(seed=seed, random_timesteps=256,
            total_timesteps=len({row['time_s'] for row in rows}), face_comparisons=len(rows),
            sunlit_timesteps=len({row['time_s'] for row in rows if row['eclipse_visibility'] == 1}),
            eclipsed_timesteps=len({row['time_s'] for row in rows if row['eclipse_visibility'] == 0}),
            partial_timesteps=len({row['time_s'] for row in rows if 0 < row['eclipse_visibility'] < 1}),
            max_geometry_error_percentage_points=max(errors_geometry),
            max_native_error_percentage_points=max(errors_native),
            max_actual_panel_power_error_w=max(errors_power))
        print('\nFace illumination validation: ' + json.dumps(summary, sort_keys=True))
        report_dir = os.environ.get('PEROVSAT_VALIDATION_DIR')
        if report_dir:
            destination = Path(report_dir)
            destination.mkdir(parents=True, exist_ok=True)
            (destination / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
            with (destination / 'samples.csv').open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
