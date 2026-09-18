import json
import math
import numpy as np

import perovsat_plugins.messaging  # noqa: F401
from perovsat_plugins.hyteresisRods import HysteresisRods


class HysteresisFactory:
    def __init__(self, scSim, scObject, magModule):
        self.sim = scSim
        self.scObject = scObject
        self.magModule = magModule

    def calculate_geometry(self, length_m, diameter_m):
        """
        Computes physical volume and the Bozorth demagnetization factor (Nd)
        for a cylindrical rod where L/D > 10.

        Nd is informational only under the Flatley–Henretty model: demagnetization
        is folded into the effective as-installed (Bs, Br, Hc) parameters.
        """
        volume = math.pi * (diameter_m / 2.0)**2 * length_m

        ratio = length_m / diameter_m
        if ratio < 10.0:
            print(f"Warning: L/D ratio is {ratio:.1f}. Bozorth approximation is best for L/D > 10.")

        Nd = (1.0 / (ratio**2)) * (math.log(2.0 * ratio) - 1.0)
        return volume, Nd

    def add_rod(self, length_m, diameter_m, axis_B, json_path, tag):
        """
        Reads Flatley–Henretty material properties from JSON, computes geometry,
        and attaches the rod.
        """
        with open(json_path, 'r') as f:
            params = json.load(f)

        vol, nd = self.calculate_geometry(length_m, diameter_m)

        rod = HysteresisRods()
        rod.ModelTag = tag

        # Flatley–Henretty effective / as-installed parameters
        rod.Bs = params.get("Bs", 0.75)
        rod.Br = params.get("Br", 0.001)
        rod.Hc = params.get("Hc", 5.0)
        rod.M0 = params.get("M0", 0.0)

        rod.V = vol

        axis = np.array(axis_B, dtype=float)
        axis = axis / np.linalg.norm(axis)
        rod.u_B = axis

        k_shape = (1.0 / rod.Hc) * math.tan((math.pi / 2.0) * (rod.Br / rod.Bs))
        ratio = length_m / diameter_m
        print(f"\n  ┌─ Rod: {tag}")
        print(f"  │  Geometry: {length_m*1000:.1f}mm x {diameter_m*1000:.1f}mm (L/D={ratio:.1f})")
        print(f"  │  Volume: {vol:.2e} m³")
        print(f"  │  Nd (info only): {nd:.4f}  →  1/Nd = {1.0/nd:.1f}")
        print(f"  │  Bs: {rod.Bs:.3f} T,  Br: {rod.Br:.4f} T,  Hc: {rod.Hc:.2f} A/m")
        print(f"  │  k_shape: {k_shape:.4e},  M0: {rod.M0:.0f} A/m")
        print(f"  └─ Axis: [{axis[0]:.3f}, {axis[1]:.3f}, {axis[2]:.3f}]")

        rod.magFieldInMsg.subscribeTo(self.magModule.envOutMsgs[0])
        self.scObject.addStateEffector(rod)
        self.sim.AddModelToTask("simTask", rod)

        return rod
