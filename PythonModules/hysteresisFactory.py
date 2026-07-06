import json
import math

import perovsat_plugins.messaging  # noqa: F401 — registers custom message recorders
from perovsat_plugins.hyteresisRods import HysteresisRods

class HysteresisFactory:
    def __init__(self, scSim, scObject, magModule):
        self.sim = scSim
        self.scObject = scObject
        self.magModule = magModule


    def calculate_geometry(self, length_m, diameter_m):
        """
        Computes physical volume and the Bozorth Demagnetization Factor (Nd)
        for a cylindrical rod where L/D > 10.
        """
        volume = math.pi * (diameter_m / 2.0)**2 * length_m

        ratio = length_m / diameter_m
        if ratio < 10.0:
            print(f"Warning: L/D ratio is {ratio:.1f}. Bozorth approximation is best for L/D > 10.")

        # Bozorth equation for long cylinders
        Nd = (1.0 / (ratio**2)) * (math.log(2.0 * ratio) - 1.0)
        return volume, Nd


    def add_rod(self, length_m, diameter_m, axis_B, json_path, tag):
        """
        Reads material properties from JSON, computes geometry, and attaches the rod.
        """
        with open(json_path, 'r') as f:
            params = json.load(f)

        vol, nd = self.calculate_geometry(length_m, diameter_m)

        rod = HysteresisRods()
        rod.ModelTag = tag

        # Core Jiles-Atherton material properties
        rod.Ms    = params.get("Ms", 517000.0)
        rod.a     = params.get("a", 3.0)
        rod.alpha = params.get("alpha", 0.0001)
        rod.k     = params.get("k", 1.5)
        rod.c     = params.get("c", 0.15)
        rod.M0    = params.get("M0", 0.0)

        # Computed geometric properties
        rod.V     = vol
        rod.Nd    = nd
        rod.u_B   = axis_B

        # Attach to simulation
        rod.magFieldInMsg.subscribeTo(self.magModule.envOutMsgs[0])
        self.scObject.addStateEffector(rod)
        self.sim.AddModelToTask("simTask", rod)

        return rod
