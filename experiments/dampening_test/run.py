"""
experiments/dampening_test/run.py
Viscous damping comparison test.
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "PythonModules"))

from sim.core import ExperimentBase
from sim.plotting import plot_detumble_curve


class DampeningTestExperiment(ExperimentBase):
    EXPERIMENT_NAME = "dampening_test"
    SIM_DURATION_S = 5580.0
    TIMESTEP_S = 1.0
    RECORD_PERIOD_S = 1.0
    INCLUDE_HYSTERESIS_RODS = False     # use viscous damper instead
    INCLUDE_POWER_MANAGEMENT = False
    INCLUDE_VIZARD = False

    def build(self):
        super().build()
        # Attach a viscous damper
        from Basilisk.architecture import messaging, sysModel
        from Basilisk.simulation import extForceTorque

        C = 2.0e-4

        class _ViscousDamper(sysModel.SysModel):
            def __init__(self):
                super().__init__()
                self.ModelTag = "ViscousDamper"
                self.scStateInMsg = messaging.SCStatesMsgReader()
                self.cmdTorqueOutMsg = messaging.CmdTorqueBodyMsg()
            def Reset(self, ns): pass
            def UpdateState(self, ns):
                sc = self.scStateInMsg()
                if sc is None: return
                tau = -C * np.array(sc.omega_BN_B)
                payload = messaging.CmdTorqueBodyMsgPayload()
                payload.torqueRequestBody = tau.tolist()
                self.cmdTorqueOutMsg.write(payload, ns, self.moduleID)

        self.damper = _ViscousDamper()
        self.damper.scStateInMsg.subscribeTo(self.scObject.scStateOutMsg)
        self.scSim.AddModelToTask("simTask", self.damper)

        self.damper_effector = extForceTorque.ExtForceTorque()
        self.damper_effector.ModelTag = "DamperEffector"
        self.scObject.addDynamicEffector(self.damper_effector)
        self.scSim.AddModelToTask("simTask", self.damper_effector)
        self.damper_effector.cmdTorqueInMsg.subscribeTo(self.damper.cmdTorqueOutMsg)

    def postprocess(self, output_dir):
        plot_detumble_curve(self.recorders["scState"], output_dir)


if __name__ == "__main__":
    DampeningTestExperiment().run()