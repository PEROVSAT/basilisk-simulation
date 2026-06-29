# Passive Magnetic Attitude Control (PMAC) Module Design

## Objective

The Passive Magnetic Attitude Control (PMAC) module simulates the passive magnetic stabilization system planned for PEROVSAT.

The system consists of:

1. A permanent magnet aligned with the spacecraft body Z-axis.
2. Hysteresis rods used for passive detumbling.

The objective is to accurately model spacecraft interaction with Earth's magnetic field and predict:

* Alignment behavior
* Detumbling rate
* Final attitude stability
* Sensitivity to magnet strength
* Sensitivity to hysteresis rod properties

The module should support parameter sweeps to assist hardware selection and design.

---

# Module Structure

## Primary Interface

```python
add_pmac(
    scObject,
    magnet_dipole_moment,
    hysteresis_volume,
    hysteresis_coercivity,
    hysteresis_remanence
)
```

The function accepts an existing Basilisk spacecraft object and attaches PMAC behavior.

Example usage:

```python
scObject = create_perovsat(mu)

add_pmac(
    scObject,
    magnet_dipole_moment=0.15,
    hysteresis_volume=5e-7,
    hysteresis_coercivity=80,
    hysteresis_remanence=0.25
)
```

---

# Permanent Magnet Model

## Physical Behavior

The permanent magnet attempts to align its magnetic dipole moment with Earth's magnetic field.

The spacecraft experiences a magnetic torque.

Torque is:

τ = m × B

Where:

* τ = magnetic torque [N·m]
* m = spacecraft magnetic dipole moment [A·m²]
* B = local magnetic field vector [T]

Magnitude:

|τ| = |m||B|sin(θ)

where θ is the angle between the spacecraft magnet and Earth's magnetic field.

---

# Hysteresis Rod Model

## Purpose

Hysteresis rods dissipate rotational energy.

As the spacecraft rotates through Earth's magnetic field, the magnetic field experienced in body coordinates changes.

The rods repeatedly magnetize and demagnetize.

The energy represented by the hysteresis loop is converted into heat.

This produces passive damping.

---

# Hysteresis Loss Model

Energy loss per cycle:

E_loss = Volume × Area(B-H Loop)

The B-H loop area depends on:

* coercivity (Hc)
* remanence (Br)

Approximate:

Area ≈ 4 × Br × Hc

Resulting energy dissipation:

E_loss ≈ V × 4BrHc

---

# Damping Torque Approximation

For initial implementation:

τ_damp = -C_hyst ω

Where:

* ω = body angular velocity
* C_hyst = equivalent hysteresis damping coefficient

This provides a stable first-order approximation.

Future versions may replace this with a full B-H state model.

---

# Spacecraft Rotational Dynamics

Torque updates spacecraft angular motion.

Euler rotational dynamics:

Iω̇ + ω × (Iω) = τ_total

Where:

τ_total =
τ_magnet +
τ_hysteresis

The PMAC module contributes both torque terms.

---

# Applying Torque In Basilisk

Each simulation step:

1. Query Earth magnetic field vector.
2. Convert field into body frame.
3. Compute magnetic alignment torque.
4. Compute hysteresis damping torque.
5. Apply total torque to spacecraft.

Pseudo-flow:

```python
B = getEarthField()

tau_magnet = cross(m, B)

tau_hyst = -C_hyst * omega

tau_total = tau_magnet + tau_hyst

applyTorque(scObject, tau_total)
```

---

# Earth Magnetic Field Model

## World Magnetic Model (WMM)

Accurate simulation requires realistic magnetic field values.

Basilisk can use geomagnetic field models based on WMM data.

WMM provides:

* field strength
* declination
* inclination
* secular variation

based on:

* latitude
* longitude
* altitude
* date

For each simulation step:

1. Determine spacecraft position.
2. Convert position to geodetic coordinates.
3. Query WMM.
4. Obtain magnetic field vector.
5. Apply PMAC calculations.

This provides realistic field variation throughout the orbit.

---

# Required Parameters

Permanent Magnet

* magnetic dipole moment [A·m²]
* body-axis orientation

Hysteresis Rods

* volume
* coercivity
* remanence
* rod orientation

Simulation

* WMM epoch
* update rate

---

# Validation Strategy

Validation should occur in stages.

Stage 1

Permanent magnet only.

Verify spacecraft aligns with magnetic field.

Stage 2

Add damping.

Verify angular velocity decreases over time.

Stage 3

Compare detumble time against published CubeSat passive magnetic stabilization studies.

Stage 4

Compare simulation results against PEROVSAT hardware measurements.

---
