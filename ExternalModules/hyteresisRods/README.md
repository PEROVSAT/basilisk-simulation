# Continuous Hysteresis Rod Modeling — Flatley–Henretty

## Goal

Simulate hysteresis rods with as little dependence on timestep size as
possible, using a model that is RK4-friendly and well-behaved on the minor
loops a LEO CubeSat actually runs.

## Model

The rod magnetization uses the **Flatley–Henretty** empirical hysteresis model
in the **Burton AAS 12-169 S-substitution** form (`p = 2`, `q0 = 0`). This is
the de-facto standard for PMAC hysteresis rods (O/OREOS, RAX, etc.).

Material parameters (effective / as-installed — L/D demagnetization is folded in):

| Symbol | Unit | Meaning |
|--------|------|---------|
| `Bs`   | T    | Saturation flux density |
| `Br`   | T    | Remanence |
| `Hc`   | A/m  | Coercivity |
| `M0`   | A/m  | Initial magnetization (seeds `S`) |

Shaping factor (computed once in `Reset`):

```
k = (1/Hc) * tan( (π/2) * (Br/Bs) )
```

Substituted state (the integrated ODE variable):

```
S = tan( (π/2) * (B/Bs) )      ⇔      B = (2 Bs / π) * atan(S)
```

Recoil ODE:

```
σ = sign(Ḣ)
f = clamp( (σ (H − S/k) + Hc) / (2 Hc) , 0, 1 )   # 1 on active boundary
dS/dH = k f²
dS/dt = (dS/dH) Ḣ
```

Dipole recovery and torque (unchanged from prior plumbing):

```
M = B/μ₀ − H
m_rod = M · V · û
τ = m_rod × B_body
```

After each discrete sim step, `S` is projected onto the major-loop strip
`[k(H−Hc), k(H+Hc)]` so fixed-step RK4 cannot leave the admissible set
(Burton AAS 12-169).

## Why not Jiles–Atherton?

JA’s gated irreversible term is discontinuous across RK4 substeps, and classic
JA is known to misbehave on non-stationary minor loops. FH has a smooth
non-negative slope, trajectories that converge to the major loop by
construction, and parameters (`Bs`, `Br`, `Hc`) that map directly to rod
datasheets / lab measurements.

## Configs

See `hysteresis_configs/hymu80_z_axis.json` (narrow loop) and
`hymu80_xy_axis.json` (wide loop). Example HyMu80 as-installed starting points
for L/D ≈ 20:

- Z: `Bs=0.75 T`, `Br=0.001 T`, `Hc=5 A/m`
- XY: `Bs=0.75 T`, `Br=0.003 T`, `Hc=15 A/m`

Apparent susceptibility at these params matches the demag limit `1/Nd ≈ 149`
(Level 0 measured `χ_app ≈ 155`).

## Validation

```
python sims/level0_fh_test.py          # loop area, energy balance, |B|≤Bs
python sims/level0_fh_unit_tests.py    # derivative invariants + minor loops
```

## Field kinematics

Basilisk’s `magneticFieldWMM` is still discrete (ZOH). `Ḣ` is obtained from a
finite difference of the inertial field plus the `−ω × B` body-frame transport
term. A continuous WMM would remove that finite-difference approximation; the
FH ODE itself does not depend on how `Ḣ` is supplied.
