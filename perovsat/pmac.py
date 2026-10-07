"""Permanent magnet + hysteresis rods (passive magnetic ADCS)."""

from __future__ import annotations

from dataclasses import dataclass
from math import pi

import numpy as np

from perovsat import config
from perovsat._bsk import attach_recorder

try:
    import perovsat_plugins.messaging  # noqa: F401
    from perovsat_plugins.hyteresisRods import HysteresisRods
    from perovsat_plugins.permanentMagnet import PermanentMagnet
except ImportError as exc:
    raise ImportError(f"Compiled plugins not found: {exc}") from exc


@dataclass
class PmacStack:
    magnet: object
    rods: dict
    recorders: dict


def setup_pmac(scSim, scObject, mag_module, task_name, record_period_ns) -> PmacStack:
    mag_out = mag_module.envOutMsgs[0]

    magnet = PermanentMagnet()
    magnet.ModelTag = "PermanentMagnet"
    magnet.magDipole_B = np.array(config.DIPOLE_BODY_AM2)
    magnet.magFieldInMsg.subscribeTo(mag_out)
    scObject.addDynamicEffector(magnet)
    scSim.AddModelToTask(task_name, magnet)

    volume = pi * (config.ROD_DIAMETER_M / 2.0) ** 2 * config.ROD_LENGTH_M
    rods = {}
    torque_recs = {}
    hyst_recs = {}
    for spec in config.RODS:
        material = config.MATERIALS[spec.material]
        axis = np.array(spec.axis, dtype=float)
        axis = axis / np.linalg.norm(axis)

        rod = HysteresisRods()
        rod.ModelTag = spec.tag
        rod.Bs = material.Bs
        rod.Br = material.Br
        rod.Hc = material.Hc
        rod.M0 = material.M0
        rod.V = volume
        rod.u_B = axis
        rod.magFieldInMsg.subscribeTo(mag_out)
        scObject.addStateEffector(rod)
        scSim.AddModelToTask(task_name, rod)

        rods[spec.tag] = rod
        torque_recs[spec.tag] = attach_recorder(
            scSim, task_name, rod.torqueLogOutMsg, record_period_ns
        )
        hyst_recs[spec.tag] = attach_recorder(
            scSim, task_name, rod.hysteresisDebugOutMsg, record_period_ns
        )

    return PmacStack(
        magnet=magnet,
        rods=rods,
        recorders={
            "pmTorque": attach_recorder(
                scSim, task_name, magnet.cmdTorqueOutMsg, record_period_ns
            ),
            "rodTorques": torque_recs,
            "hysteresis": hyst_recs,
        },
    )
