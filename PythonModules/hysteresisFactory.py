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
        Computes physical volume and the Bozorth Demagnetization Factor (Nd)
        for a cylindrical rod where L/D > 10.
        
        Parameters
        ----------
        length_m : float
            Rod length in meters
        diameter_m : float
            Rod diameter in meters
            
        Returns
        -------
        tuple
            (volume_m3, demagnetization_factor)
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
        
        Parameters
        ----------
        length_m : float
            Rod length in meters
        diameter_m : float
            Rod diameter in meters
        axis_B : list
            Rod axis direction in body frame (will be normalized)
        json_path : str
            Path to JSON configuration file
        tag : str
            Unique identifier for the rod
            
        Returns
        -------
        HysteresisRods
            The created rod object
        """
        with open(json_path, 'r') as f:
            params = json.load(f)

        vol, nd = self.calculate_geometry(length_m, diameter_m)

        rod = HysteresisRods()
        rod.ModelTag = tag

        # Core Jiles-Atherton material properties
        rod.Ms    = params.get("Ms", 1500000.0)
        rod.a     = params.get("a", 50.0)
        rod.alpha = params.get("alpha", 0.001)
        rod.k     = params.get("k", 40.0)
        rod.c     = params.get("c", 0.1)
        
        # Initial magnetization - use value from JSON, default to 0.0
        # M0=0 allows rods to magnetize naturally from the Earth's field
        rod.M0    = params.get("M0", 0.0)
        
        # Smoothing parameter for sgn(Hdot) transition
        rod.deltaSmoothing = params.get("deltaSmoothing", 0.1)

        # Computed geometric properties
        rod.V     = vol
        rod.Nd    = nd
        
        # Normalize axis vector to ensure it's a unit vector
        axis = np.array(axis_B, dtype=float)
        axis = axis / np.linalg.norm(axis)
        rod.u_B = axis

        # Debug output
        ratio = length_m / diameter_m
        print(f"\n  ┌─ Rod: {tag}")
        print(f"  │  Geometry: {length_m*1000:.1f}mm x {diameter_m*1000:.1f}mm (L/D={ratio:.1f})")
        print(f"  │  Volume: {vol:.2e} m³")
        print(f"  │  Nd: {nd:.4f}")
        print(f"  │  Ms: {rod.Ms:.0f} A/m")
        print(f"  │  M0: {rod.M0:.0f} A/m")
        print(f"  │  a: {rod.a:.1f}, k: {rod.k:.1f}, c: {rod.c:.2f}")
        print(f"  └─ Axis: [{axis[0]:.3f}, {axis[1]:.3f}, {axis[2]:.3f}]")

        # Attach to simulation
        rod.magFieldInMsg.subscribeTo(self.magModule.envOutMsgs[0])
        self.scObject.addStateEffector(rod)
        self.sim.AddModelToTask("simTask", rod)

        return rod