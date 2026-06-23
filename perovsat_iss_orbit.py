#
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
Simulates PEROVSAT in a low Earth orbit matching the ISS (400km altitude,
51.64 deg inclination). Outputs to Vizard for visualization.
"""
import sys

sys.path.append(r"C:\Users\abdul\orbit-library")

from orbit_library.iss_orbit import get_iss_orbit

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
    scSim.AddModelToTask(simTaskName, scObject)

    # Gravity
    gravFactory = simIncludeGravBody.gravBodyFactory()
    planet = gravFactory.createEarth()
    planet.isCentralBody = True
    mu = planet.mu
    gravFactory.addBodiesTo(scObject)

    # ISS orbit elements
    rN, vN = get_iss_orbit(mu)

    scObject.hub.r_CN_NInit = rN
    scObject.hub.v_CN_NInit = vN

    oe = orbitalMotion.rv2elem(mu, rN, vN)

    # Simulation time: 0.75 orbital periods
    n = np.sqrt(mu / oe.a ** 3)
    P = 2.0 * np.pi / n
    simulationTime = macros.sec2nano(0.75 * P)

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

    scSim.InitializeSimulation()
    scSim.ConfigureStopTime(simulationTime)
    scSim.ExecuteSimulation()

    posData = dataRec.r_BN_N
    velData = dataRec.v_BN_N

    figureList = plotOrbits(dataRec.times(), posData, velData, oe, mu, P)

    if show_plots:
        plt.show()
    plt.close("all")

    return figureList


def plotOrbits(timeAxis, posData, velData, oe, mu, P):
    plt.close("all")

    # Inertial position components
    plt.figure(1)
    fig = plt.gcf()
    ax = fig.gca()
    ax.ticklabel_format(useOffset=False, style="plain")
    for idx in range(3):
        plt.plot(
            timeAxis * macros.NANO2SEC / P,
            posData[:, idx] / 1000.0,
            color=unitTestSupport.getLineColor(idx, 3),
            label="$r_{BN," + str(idx) + "}$",
        )
    plt.legend(loc="lower right")
    plt.xlabel("Time [orbits]")
    plt.ylabel("Inertial Position [km]")

    figureList = {}
    figureList[fileName + "1"] = plt.figure(1)

    # Orbit in perifocal frame
    b = oe.a * np.sqrt(1 - oe.e ** 2)
    p = oe.a * (1 - oe.e ** 2)
    plt.figure(2, figsize=tuple(np.array((1.0, b / oe.a)) * 4.75), dpi=100)
    plt.axis(np.array([-oe.rApoap, oe.rPeriap, -b, b]) / 1000 * 1.25)
    fig = plt.gcf()
    ax = fig.gca()
    ax.add_artist(plt.Circle((0, 0), 6378.0, color="#008800"))  # Earth
    rData, fData = [], []
    for idx in range(len(posData)):
        oeData = orbitalMotion.rv2elem(mu, posData[idx], velData[idx])
        rData.append(oeData.rmag)
        fData.append(oeData.f + oeData.omega - oe.omega)
    plt.plot(np.array(rData) * np.cos(fData) / 1000, np.array(rData) * np.sin(fData) / 1000,
             color="#aa0000", linewidth=3.0)
    fFull = np.linspace(0, 2 * np.pi, 100)
    rFull = [p / (1 + oe.e * np.cos(f)) for f in fFull]
    plt.plot(np.array(rFull) * np.cos(fFull) / 1000, np.array(rFull) * np.sin(fFull) / 1000,
             "--", color="#555555")
    plt.xlabel("$i_e$ Cord. [km]")
    plt.ylabel("$i_p$ Cord. [km]")
    plt.grid()
    figureList[fileName + "2"] = plt.figure(2)

    return figureList


if __name__ == "__main__":
    run(True)