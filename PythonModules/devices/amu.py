"""
devices/amu.py
Simulated Aerospace Measurement Unit (AMU) -- reads PV cell I-V curves.

Follows the recommended flow for a new device:
  1. Subclass SimulatedDevice.
  2. Set power members + duty cycle in __init__.
  3. Add members for what the device is attached to (here: a PV cell / face).
  4. Implement onMessage(), dispatching each supported command to its own
     private _cmd_* method. For now only IV_SWEEP is implemented.

To test standalone (no full Basilisk sim needed), fake an onMessage call
with a small SimulationState-like object -- see sims/test_iv_sweep.py.
"""

import numpy as np

from devices.base import SimulatedDevice
from payload_iv import PVDevice


class SimulatedAMU(SimulatedDevice):
    def __init__(self, amu_id, pv_device: PVDevice = None,
                 power_idle=0.002, power_active=0.018, duty_cycle=0.05):
        super().__init__(f"AMU_{amu_id:02d}", power_idle=power_idle,
                         power_active=power_active, duty_cycle=duty_cycle,
                         initial_state='off')
        self.amu_id = amu_id
        self.pv_device = pv_device      # the PVDevice (payload_iv.py) this AMU sweeps
        self.last_sweep = None

    def onMessage(self, message, simulation):
        command = message.get('command') if isinstance(message, dict) else message
        if command == 'IV_SWEEP':
            return self._cmd_iv_sweep(message, simulation)
        raise ValueError(f"{self.name}: unsupported command '{command}'")

    # ------------------------------------------------------------------
    # Commands
    # ------------------------------------------------------------------
    def _cmd_iv_sweep(self, message, simulation):
        """Run an I-V sweep on the attached PV device given the current sun
        geometry from `simulation`, and cache/return the result."""
        if self.pv_device is None:
            raise RuntimeError(f"{self.name}: no PV device attached, can't sweep")

        self.set_state('active')

        cos_inc = max(0.0, float(np.dot(self.pv_device.normal,
                                        simulation.sun_direction_body)))
        irradiance_w_m2 = (1361.0 * cos_inc * simulation.shadow_factor *
                           simulation.sun_distance_factor)
        temp_c = message.get('temp_c', 25.0) if isinstance(message, dict) else 25.0
        num_points = message.get('num_points', 40) if isinstance(message, dict) else 40
        v_min_frac = message.get('v_min_frac', 0.0) if isinstance(message, dict) else 0.0

        V, I, voc = self.pv_device.curve(
            irradiance_w_m2, temp_c, num=num_points,
            v_min=v_min_frac * self.pv_device.voc_ref)
        summary = self.pv_device.summary(irradiance_w_m2, temp_c)

        self.last_sweep = {
            'sim_time_s': simulation.sim_time_s,
            'V': V, 'I': I, 'voc': voc, 'summary': summary,
            'irradiance_w_m2': irradiance_w_m2, 'temp_c': temp_c,
        }
        self.set_state('idle')
        return self.last_sweep
