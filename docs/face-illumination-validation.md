# Per-face illumination validation

Validated on 2026-11-03 using the repository's Basilisk Docker runtime.

## What the pane now measures

The previous single Illumination gauge measured eclipse visibility only. It
did not distinguish faces. It is now labelled **Sun visible (eclipse)**.
Six additional gauges identify the body-fixed +X, -X, +Y, -Y, +Z and -Z faces.
Each shows direct incident irradiance as a percentage of the normal-incidence
irradiance at the spacecraft's current distance from the Sun:

`face_percent = 100 * eclipse_visibility * max(0, face_normal dot sun_direction)`

The implementation uses the current spacecraft-relative Sun position and
inertial-to-body MRP attitude transformation. A face without solar cells still
receives illumination; only the configured +X, +Y and -Y panels produce power.

## Independent checks

`tests/test_face_illumination.py` runs 6000 simulated seconds at a 0.5-second
physics timestep. Seed 20261103 selects 256 random physics ticks without
replacement. Every penumbra tick is also checked, producing 288 unique times:
153 in sunlight, 102 in full eclipse, and 33 in partial eclipse.

At each selected time, all six displayed values are compared with:

1. An independent axis-angle/Rodrigues rotation of each body normal into the
   inertial frame. This does not call the production MRP-to-DCM routine.
2. Six actual Basilisk `SimpleSolarPanel` reference models, each with unit area
   and efficiency, reading the same current state, Sun and eclipse messages.
   These test-only models are not connected to the battery.
3. For the three installed panels, the predicted electrical output is compared
   with the actual vehicle's power-node messages, including area and efficiency.

Reference irradiance uses the installed SDK constants: 1372.5398 W/m² at
149597870693 m, scaled by inverse square distance. The power documentation's
earlier illustrative 1361 W/m² value has been corrected to match this model.

## Results

All 1,728 face comparisons passed. The complete 43-test regression suite also
passed, including physics equivalence, paced execution and segmented missions.
Maximum absolute discrepancies:

| Comparison | Maximum error |
| --- | ---: |
| Display versus independent geometry | 4.2633e-14 percentage points |
| Display versus native reference panels | 7.1054e-14 percentage points |
| Predicted versus actual installed-panel electrical power | 1.3323e-15 W |

These differences are at floating-point rounding level. All displayed values
were between 0% and 100%. Separate controlled tests passed for normal incidence,
back-facing and edge-on faces, 25% eclipse visibility, full eclipse, a 90-degree
attitude rotation, nonzero spacecraft position, and degenerate Sun geometry.
The test also verifies that all six face labels reach the saved Vizard stream.

Example at the randomly selected simulation time 5.0 s, with no eclipse:

| Face | Display (%) | Independent geometry (%) | Native irradiance (W/m²) |
| --- | ---: | ---: | ---: |
| +X | 97.693826 | 97.693826 | 1298.567717 |
| -X | 0 | 0 | 0 |
| +Y | 15.060208 | 15.060208 | 200.183582 |
| -Y | 0 | 0 | 0 |
| +Z | 0 | 0 | 0 |
| -Z | 15.136267 | 15.136267 | 201.194577 |

## Reproduction and scope

From the repository root in WSL, enter the project Docker runtime:

```bash
cd /mnt/g/basilisk-simulation
make shell
```

Then run the focused checks inside that container:

```bash
PEROVSAT_VALIDATION_DIR=.build/face-illumination-validation \
python -m unittest discover -s tests -p test_face_illumination.py -v
```

This exports `samples.csv` (timestamps, face values, reference irradiance,
and actual/predicted panel power) and `summary.json` to that directory.
The mounted checkout makes these files available on Windows under
`G:\basilisk-simulation\.build\face-illumination-validation`. Run `exit` to
leave the container. From WSL, `make test` runs the entire regression suite.

The results establish agreement with the simulation's direct-sunlight model,
not flight measurements. Eclipse visibility is taken from the existing eclipse
model in all comparisons; its celestial geometry is not independently validated
here. Appendage self-shadowing, Earth albedo, scattering and finite-Sun effects
at grazing incidence are not modeled. The new values are connected to the same
live and playback publication path; the six-row addition has not been visually
inspected in Vizard during this validation.
