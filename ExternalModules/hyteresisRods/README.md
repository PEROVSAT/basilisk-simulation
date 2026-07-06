# Continuous Hysteresis Rod Modeling with Jiles-Atherton
## Goal
Produce a module that can simulate hysteresis rods with as little dependence on timestep size as possible

## Math
### World Magnetic Model
Basilisk's `magneticFieldWMM` module only provides values discretely. However, since the WMM itself isn't discrete, there is an opportunity for a continuous model would help us avoid having to guess $\dot{\mathbf{B}}$

