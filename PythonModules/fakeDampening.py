"""
fakeDampening.py
----------------
Viscous angular-rate damper for quick visual verification of PMAC behavior.
NOT physically representative of hysteresis rods.

The torque is simply:
    tau = -C * omega_B

C is tuned for near-critical damping of the magnetic libration mode:
    k  ~ m|B| ~ 0.15 * 4.5e-5 ~ 6.75e-6 N·m/rad  (ISS LEO field strength)
    I  ~ 0.002 kg·m²
    wn = sqrt(k/I) ~ 0.058 rad/s  →  T_libration ~ 108 s
    C_crit = 2*sqrt(k*I) ~ 2.3e-4 N·m·s/rad

DEFAULT_C is set to 2e-4, which damps the libration to ~5% amplitude within
roughly one libration period (~108 s), well inside half an ISS orbit (~2790 s).
"""

import numpy as np

from Basilisk.architecture import messaging, sysModel
from Basilisk.simulation import extForceTorque

DEFAULT_C = 2.0e-4  # [N·m·s/rad] — near-critical for ISS-orbit magnet libration


class _ViscousDamperModel(sysModel.SysModel):
    def __init__(self, C):
        super().__init__()
        self.C = C
        self.scStateInMsg = messaging.SCStatesMsgReader()
        self.cmdTorqueOutMsg = messaging.CmdTorqueBodyMsg()

    def Reset(self, CurrentSimNanos):
        pass

    def UpdateState(self, CurrentSimNanos):
        sc = self.scStateInMsg()
        omega_B = np.array(sc.omega_BN_B)
        tau = -self.C * omega_B
        payload = messaging.CmdTorqueBodyMsgPayload()
        payload.torqueRequestBody = tau.tolist()
        self.cmdTorqueOutMsg.write(payload, CurrentSimNanos, self.moduleID)


class FakeDampener:
    """
    Packages a viscous rate-damping SysModel and its ExtForceTorque effector.

    Usage
    -----
        damper = FakeDampener(scSim, "simTask", scObject)
        # optionally tune: FakeDampener(..., C=1e-4)
    """

    def __init__(self, scSim, simTaskName, scObject, C=DEFAULT_C):
        self.C = C

        self._model = _ViscousDamperModel(C)
        self._model.ModelTag = "FakeDampener"
        scSim.AddModelToTask(simTaskName, self._model)

        self._effector = extForceTorque.ExtForceTorque()
        self._effector.ModelTag = "FakeDampener_Torque"
        scObject.addDynamicEffector(self._effector)
        scSim.AddModelToTask(simTaskName, self._effector)

        self._model.scStateInMsg.subscribeTo(scObject.scStateOutMsg)
        self._effector.cmdTorqueInMsg.subscribeTo(self._model.cmdTorqueOutMsg)

        print(f"FakeDampener: C = {C:.2e} N·m·s/rad  (near-critical viscous damping)")
