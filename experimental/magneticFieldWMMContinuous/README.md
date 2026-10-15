# Continuous WMM: unfinished design

[Documentation index](../../README.md)

**Status: not built or used by the simulation.** This directory has no C++
implementation, and its base-class and SWIG interfaces are inconsistent. The
active vehicle uses Basilisk's standard `magneticFieldWMM` in
[environment.py](../../perovsat/environment.py).

## Intended purpose

The proposed model would supply both magnetic field and field rate at solver
stages. The current rod model estimates inertial field rate by finite difference
at task updates; see the [active rod model](../../ExternalModules/hysteresisRods/README.md).

The design starts from a WMM scalar potential `V` and derives field and spatial
gradient in a consistent Cartesian frame:

```text
B = -gradient(V)
gradient(B) = -Hessian(V)
dB/dt = partial(B)/partial(t) + gradient(B) * velocity
```

A working implementation must handle Earth rotation, frame transformations,
coefficient time dependence, and coordinate singularities. The expressions above
alone do not define an inertial-frame field-rate implementation.

## Files and remaining work

| File | Purpose |
| --- | --- |
| [magneticFieldWMMContinuous.h](magneticFieldWMMContinuous.h) | Proposed class and coefficient storage |
| [MagneticFieldBaseContinuous.h](MagneticFieldBaseContinuous.h) | Incomplete base interface; currently defines `MagneticFieldBase` |
| [magneticFieldWMMContinuous.i](magneticFieldWMMContinuous.i) | Draft SWIG interface with unresolved includes |
| [codeGenerator.py](codeGenerator.py) | Symbolic Cartesian derivative generation attempt; not a build step |

Before integration, reconcile interfaces, implement coefficient loading and
field/rate evaluation, define the message contract, and validate against the
active field model and numerical derivatives. Add build and simulation wiring
only after those checks. No accuracy or timestep improvement is established by
these design files.
