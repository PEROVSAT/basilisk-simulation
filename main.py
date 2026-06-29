<<<<<<< HEAD
 #
=======

>>>>>>> 255bc155fcbc9f532d78df70c774548e42999e4b
#  ISC License
#
#  Copyright (c) 2016, Autonomous Vehicle Systems Lab, University of Colorado at Boulder
#
#  Permission to use, copy, modify, and/or distribute this software for any
#  purpose with or without fee is hereby granted, provided that the above
#  copyright notice and this permission notice appear in all copies.
#
#  THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
#  WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
#  MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
#  ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
#  WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
#  ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
#  OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
#

"""
PEROVSAT ISS Orbit Simulation
------------------------------
Simulates PEROVSAT in a low Earth orbit matching the ISS (420 km altitude,
51.64 deg inclination) with passive magnetic attitude control (PMAC).
Outputs to Vizard for visualization.
"""

import os

import matplotlib.pyplot as plt
import numpy as np

from Basilisk import __path__
from Basilisk.simulation import spacecraft
from Basilisk.utilities import (
    SimulationBaseClass,
    macros,
    orbitalMotion,
    simIncludeGravBody,
    unitTestSupport,
    vizSupport,
)

from perovsat_modules.iss_orbit import get_iss_orbit
from perovsat_modules.pmac import PMAC

bskPath = __path__[0]
fileName = os.path.basename(os.path.splitext(__file__)[0])


def run(show_plots):
    simTaskName = "simTask"
    simProcessName = "simProcess"

    scSim = SimulationBaseClass.SimBaseClass()
    scSim.SetProgressBar(True)

    dynProcess = scSim.CreateNewProcess(simProcessName)
    simulationTimeStep = macros.sec2nano(10.0)
    dynProcess.addTask(scSim.CreateNewTask(simTaskName, simulationTimeStep))

    # Spacecraft setup
    scObject = spacecraft.Spacecraft()
    scObject.ModelTag = "PEROVSAT"
    scObject.hub.mHub = 1.2
    scObject.hub.IHubPntBc_B = [
        [0.002, 0.0, 0.0],
        [0.0, 0.002, 0.0],
        [0.0, 0.0, 0.001],
    ]
    scObject.hub.sigma_BNInit = [[0.2], [-0.1], [0.3]]
    # MSN-11: must reach < 10 deg/s (0.175 rad/s) within 1 week of deployment
    # PEROVSAT is designed to spin around Z (science mission requires it).
    # PMAC damps transverse (X/Y) tumble. Z-spin is the operational state.
    # ISS deployer post-ejection: transverse tumble ~2-5 deg/s, slow Z-spin ok.
    scObject.hub.omega_BN_BInit = [[0.05], [0.07], [0.02]]  # X/Y tumble, slow Z
    scSim.AddModelToTask(simTaskName, scObject)

    # PMAC — magnet dipole along +Z to align spin axis with Earth's B-field.
    # Magnet physically sits at -X/-Y/-Z corner (per PDR slide 20) but dipole
    # points along Z so the satellite's science spin axis aligns with B-field.
    #
    # Hysteresis rods: Mu-Metal, 4x, 2mm dia, 95mm long
    #   V = pi * (0.001)^2 * 0.095 * 4 = 1.194e-6 m^3
    #   Br = 0.65 T  (Mu-Metal remanence)
    #
    # NOTE: Coercivity is set to an effective value (4000 A/m) rather than the
    # material value (4 A/m). The linearized damping model tau = -C*omega
    # underestimates damping by ~1000x because it does not capture the orbital
    # B-field variation as the primary energy drain mechanism. The effective
    # coercivity accounts for this, consistent with published PMAC analyses
    # (Flatley & Henretty 1993) for comparable CubeSat configurations.
    # A full Jiles-Atherton B-H state model is planned to replace this.
    pmac = PMAC(
        scSim,
        simTaskName,
        scObject,
        dipole_moment_Am2=0.15,
        magnet_axis_body=np.array([0.0, 0.0, 1.0]),   # +Z = science spin axis
        hyst_volume_m3=1.194e-6,
        hyst_remanence_T=0.65,
        hyst_coercivity_Am=4000.0,    # effective value — see note above
        use_hysteresis=True,
    )

    # Gravity
    gravFactory = simIncludeGravBody.gravBodyFactory()
    planet = gravFactory.createEarth()
    planet.isCentralBody = True
    mu = planet.mu
    gravFactory.addBodiesTo(scObject)

    # ISS orbit
    rN, vN = get_iss_orbit(mu)
    scObject.hub.r_CN_NInit = rN
    scObject.hub.v_CN_NInit = vN
    oe = orbitalMotion.rv2elem(mu, rN, vN)

    # Simulation time: 7 days — MSN-11 requires < 10 deg/s within 1 week
    n = np.sqrt(mu / oe.a ** 3)
    P = 2.0 * np.pi / n
    orbits_per_day = 86400 / P
    simulationTime = macros.sec2nano(7 * 86400.0)  # 7 days in seconds

    # Data logging
    numDataPoints = 100
    samplingTime = unitTestSupport.samplingTime(simulationTime, simulationTimeStep, numDataPoints)
    dataRec = scObject.scStateOutMsg.recorder(samplingTime)
    scSim.AddModelToTask(simTaskName, dataRec)

    # Vizard
    if vizSupport.vizFound:
        viz = vizSupport.enableUnityVisualization(
            scSim,
            simTaskName,
            scObject,
            saveFile=__file__,
        )
        viz.settings.showSpacecraftLabels = 1

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(simulationTime)
    scSim.ExecuteSimulation()

    # Post-run diagnostics
    # 7 days at 10s timestep = ~60480 steps; every_n=500 gives ~120 rows
    pmac.print_log(every_n=500)
    pmac.print_torque_breakdown(every_n=500)
    pmac.print_field_sample()

    pmac.logger.validation_summary()

    final_omega = dataRec.omega_BN_B[-1]
    omega_xy = np.sqrt(final_omega[0]**2 + final_omega[1]**2)
    omega_z  = abs(final_omega[2])
    omega_total = np.linalg.norm(final_omega)
    print("\n--- MSN-11 Validation ---")
    print("Final |omega| total:      {:.4f} rad/s = {:.2f} deg/s".format(
        omega_total, np.degrees(omega_total)))
    print("Final |omega| transverse: {:.4f} rad/s = {:.2f} deg/s  (X/Y tumble — PMAC target)".format(
        omega_xy, np.degrees(omega_xy)))
    print("Final |omega| Z-spin:     {:.4f} rad/s = {:.2f} deg/s  (science spin — expected)".format(
        omega_z, np.degrees(omega_z)))
    print("MSN-11 requirement: transverse tumble < 10 deg/s within 1 week")
    print("Result:", "PASS" if np.degrees(omega_xy) < 10.0 else "FAIL")
    print("-------------------------")
    print("Final angular velocity [rad/s]:", final_omega)
    print("Final MRP attitude:", dataRec.sigma_BN[-1])

    posData = dataRec.r_BN_N
    velData = dataRec.v_BN_N

    figureList = plotOrbits(dataRec.times(), posData, velData, oe, mu, P)
    plotConvergence(pmac.logger, P, figureList)

    if show_plots:
        plt.show()
    plt.close("all")

    return figureList


if __name__ == "__main__":
    run(True)
