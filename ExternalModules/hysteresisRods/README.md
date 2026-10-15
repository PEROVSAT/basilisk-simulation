# Hysteresis rod model

[Documentation index](../../README.md)

The active `HysteresisRods` C++ state effector models passive magnetic damping
using the Flatley-Henretty equations in the Burton S-substitution form
(`p = 2`, `q0 = 0`). Each rod has one integrated scalar state, `S`.

See [architecture](../../docs/architecture.md) for scheduling and frames, and
[config.py](../../perovsat/config.py) for installed values and rod geometry.

## Parameters

Material values are effective installed parameters: rod demagnetization is
already folded in. They should not be treated as unadjusted bulk material data.

| Symbol | Unit | Meaning |
| --- | --- | --- |
| `Bs` | T | Saturation flux density |
| `Br` | T | Remanent flux density; `0 < Br < Bs` |
| `Hc` | A/m | Positive coercivity |
| `M0` | A/m | Initial magnetization used to seed `S` near zero applied field |
| `V` | m^3 | Rod volume |
| `u_B` | unit vector | Rod axis in the body frame |

## Equations

`B_rod` is flux density inside the rod; `B_body` is the external field vector.
`H` is the external field projected along the rod axis, divided by vacuum
permeability `mu0`. `Hdot` is its time derivative.

```text
k = tan((pi / 2) * Br / Bs) / Hc
S = tan((pi / 2) * B_rod / Bs)
B_rod = (2 * Bs / pi) * atan(S)

sigma = sign(Hdot)
f = clamp((sigma * (H - S/k) + Hc) / (2 * Hc), 0, 1)
dS/dt = k * f^2 * Hdot

M = B_rod / mu0 - H
m_rod = M * V * u_B
torque_body = cross(m_rod, B_body)
```

The scheduled update projects `S` into the major-loop strip
`[k * (H - Hc), k * (H + Hc)]`. Torque evaluation projects a local copy;
derivative evaluation uses the integrator's stage state. The simulation uses
adaptive RKF45, not fixed-step RK4.

## Field rate and validation

Basilisk's WMM updates at the task period. Between updates, the inertial field
is held constant (zero-order hold). The rod field-rate estimate combines an
inertial finite difference with the body transport term `-cross(omega, B_body)`.
The unfinished continuous-WMM design is not used by this model.

From the repository root, run `make smoke` for imports and `make test` for
regressions and a short simulation. These checks do not establish physical
accuracy of hysteresis loops or multi-day damping. For model changes, compare
representative results at finer task periods; see [development](../../docs/development.md).
