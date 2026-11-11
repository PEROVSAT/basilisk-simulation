# PEROVSAT custom spacecraft model implementation plan

Prepared 2026-11-06. Original plan retained below for the later alignment work.

Implementation update: at the user's request, the centered model is now wired
directly into the existing `PerovSatSimulation._setup_vizard()` for live and
recorded runs. Path and rotation settings live in `perovsat/config.py`; there is
no separate model module or preparation script. Physical-axis and origin
verification are deferred to the user using the existing vectors. See
`docs/realtime.md` for current usage. The inspection and acceptance steps below
remain planned work, not completed validation.

The installed viewer subsequently logged `Loading glTF failed!`. The runtime
asset was changed to OBJ/MTL generated from the same centered GLB hierarchy,
preserving dimensions, normals, and material base colors. The GLB is retained
as an intermediate asset. Rendering of the OBJ awaits the user's restart/check.

## Findings and limits

- The spacecraft is named `PEROVSAT`. The shared integration point is
  `PerovSatSimulation._setup_vizard()` in `perovsat/simulation.py`, immediately
  after `enableUnityVisualization()`. Both live and recorded runs use this path.
- The repository pins Basilisk 2.10.2 and documents Windows Vizard 2.4 with
  Basilisk running in Docker/WSL. Confirm the actual viewer version before work.
- Existing body-axis labels, Sun vector, and six face-illumination gauges provide
  useful verification aids. Configured power-producing faces are +X, +Y, -Y;
  the permanent dipole is along +Z. These are simulation definitions, not proof
  of the CAD-to-body mapping.
- `G:\PEROVSAT_full_payload_ver.1.glb` is 40,027,912 bytes, glTF 2.0 exported by
  SOLIDWORKSGLTF: 191 nodes, 148 meshes, 28 materials, no images or animations.
  It uses transmission and volume material extensions. Its bus assembly node has
  translation approximately (0.025757, 1.052443, 0.001629), with further nested
  transforms. This is a node translation, not a measured center of mass.
- `G:\textured_lighted.blend` exists (22,078,931 bytes). Its scene, materials,
  units, and relationship to the GLB have not yet been inspected in Blender.
  No accessible Blender executable was found in PATH or the standard installation
  directory during this review. Do not infer contents from its filename.
- Current official Vizard documentation and the local Vizard source checkout
  support runtime GLB and OBJ import. This does not establish support in the
  installed executable. Start with GLB; retain OBJ/MTL/textures as a fallback.
- No authoritative physical-feature-to-body-axis definition has been established.
  Final rotation values must remain unset until this is resolved.

## 1. Establish the physical coordinate contract

Obtain the spacecraft drawing/ICD axis definition, or identify two nonparallel
signed body directions using unmistakable physical features (for example the
payload-face normal and a particular connector edge). Confirm a third asymmetric
landmark to catch a mirror or 180-degree ambiguity. Record the body origin B,
its relation to the center of mass, and one known physical length.

Create an annotated six-view reference that maps visible features to +X, -X,
+Y, -Y, +Z, -Z. Compare the actual bus arrays with the configured panel normals.
If they disagree, report the model/configuration discrepancy; do not rotate or
alter physics merely to force the three arrays to fit. Confirm whether payload
cells are distinct from the bus arrays modeled by the power subsystem.

Deliverable: a reviewed coordinate table and physical reference dimensions.
This is the prerequisite for an exact orientation claim.

## 2. Inspect and prepare a reproducible asset

Open both sources in Blender with automatic script execution disabled. Treat any
embedded text as asset data, not instructions. Preserve the originals. Compare
geometry revision, assembly/deployment state, material coverage, units, hierarchy,
negative scales, normals, and bounding extents after all parent transforms.

Choose the geometry that represents the actual spacecraft; prefer the Blender
appearance only if it matches that geometry. Export spacecraft meshes and needed
materials only, excluding scene cameras, lights, floors, and presentation objects.
Inspect transparency and material-extension compatibility in Vizard. Avoid baked
directional lighting that would make a shaded face appear Sun-facing.

Use a single documented CAD-to-body rigid transform:

`p_B = R_BM * (s * (p_M - o_M))`

Here p_M is a point after source hierarchy transforms, o_M is body origin B in
source coordinates, s is the verified uniform conversion to meters, and R_BM maps
model vectors into body coordinates. Derive rotation from the physical references;
check orthonormality and determinant +1. Reject accidental reflection. Do not use
the bounding-box center as a substitute for the defined body origin.

Bake this mapping into a derived asset where practical. Separately establish the
GLB exporter/importer's coordinate conversion using an asymmetric axis fixture;
do not assume that zero Vizard rotation means CAD axes already match body axes.
Apply any importer correction once, with a recorded derivation. Avoid trial-and-
error rotations scattered between Blender, export settings, and Vizard.

Proposed outputs under `assets/spacecraft/perovsat/`: viewer asset, provenance and
transform manifest, source hashes, exporter version/options, dimensions, feature
coordinates/normals, and preview images. Preserve visual landmarks if simplifying
internal hardware for performance. Keep source files outside Git or use the
repository's chosen large-file policy; do not silently commit large binaries.

## 3. Integrate through the shared Vizard setup

Add a small model configuration/helper (for example `perovsat/vizard_model.py`)
and call `vizSupport.createCustomModel()` after visualization creation, targeting
the actual `self.scObject.ModelTag`. Verify the installed 2.10.2 helper's argument
types and serialization before implementation. Set model path, scale, rotation,
and offset explicitly from the verified manifest. Document that scripted rotation
uses radians and the documented 3-2-1 convention; do not copy GUI degree values
without verifying the viewer's transform order.

Expose a viewer-side model path and an explicit placeholder/debug option through
run configuration and the relevant experiment/mission entry points. Make the
verified PEROVSAT asset the normal choice once acceptance tests pass. Keep the
existing axes and Sun vector available. Report missing/unsupported custom assets
clearly rather than silently treating a placeholder as successful integration.

Separate the local asset-validation path from the path serialized for Vizard:
Windows Vizard opens the file itself. A Docker `/workspace/...` or WSL `/mnt/g/...`
path is not a usable Windows model path. Use a Windows-visible absolute path for
live runs, including simultaneous recording. For portable playback, package the
asset alongside the recording and use a tested `./assets/...` path relative to
the playback file. The inspected viewer source recognizes dot-prefixed relative
paths in playback. Verify relocation on the actual executable.

Do not change spacecraft attitude, mass, inertia, dipole, or panel normals to
compensate for a visual mesh alignment. This integration changes rendering only.
It does not require the separate custom telemetry UI build.

## 4. Prove orientation and origin

Build a deterministic visualization fixture, independent of mission tumbling.

1. Verify source landmark positions and outward normals after the full transform.
   Use a documented numerical tolerance (initial target: 1e-6 for unit-vector
   residuals, with separate CAD-appropriate position/dimension tolerances).
2. Render identity attitude and inspect all six labeled faces in orthographic
   views. Check the body origin, scale, handedness, and asymmetric landmarks.
3. Exercise positive and negative 90-degree attitudes about each body axis, plus
   one nonsymmetric combined rotation. Independently calculate inertial landmark
   positions as `r_N = r_BN_N + C_NB * p_B`, with `C_NB = C_BN.T` for Basilisk's
   inertial-to-body attitude matrix. Check signs and rotation order explicitly.
4. Run a slow single-axis sweep to expose incorrect pivots or geometry orbiting
   around an offset origin. Keep the camera/inertial reference fixed for rotation
   checks; a body-following camera can conceal errors.
5. Use controlled Sun directions along all six body axes outside eclipse. Compare
   geometric outward normals to the existing incidence gauges and the three
   power-producing faces. Check a mixed-direction case as well. Shading is a
   supporting visual check, not numerical proof: materials and ambient light can
   mislead, and the power model excludes spacecraft self-shadowing.
6. Repeat the essential poses in live mode and saved playback on Windows Vizard.
   Record the viewer version, asset hash, transform, pose values, measured errors,
   and screenshots. Verify reloading starts with the same alignment.

Use an independent rotation calculation in tests rather than reusing the export
transform implementation as its own oracle. Automated geometry and serialized
settings tests do not replace the actual importer/viewer inspection.

## 5. Regression and completion criteria

- Verify the stream targets PEROVSAT and contains the intended asset settings.
- Test path handling for Windows live viewing, playback relocation, missing
  assets, and the explicit placeholder mode.
- Compare identical custom-model/placeholder runs: orbit, attitude, angular rates,
  power, and battery results must remain unchanged within existing tolerances.
- Run the existing relevant simulation and face-illumination regression checks.
- Measure startup/import time and rendering during a representative realtime
  run; simplify only if necessary, preserving external geometry and landmarks.
- Update usage docs with asset location, export reproduction, axis-reference
  images, and playback packaging instructions.

Complete only when the physical axis mapping is established, numerical checks
pass, and live/playback screenshots demonstrate correct signed face alignment,
origin, and scale. Until then the status is "alignment unverified," even if the
spacecraft looks plausible from one camera angle.

## References

- [Official Vizard custom model import guide](https://avslab.github.io/basilisk/Vizard/VizardGUI.html#import-a-custom-shape-model)
- [Official scripted model settings](https://avslab.github.io/basilisk/develop/Vizard/vizardAdvanced/vizardSettings.html)
- Local implementation: `perovsat/simulation.py`, `perovsat/config.py`,
  `perovsat/run_config.py`, `docs/realtime.md`, and
  `docs/face-illumination-validation.md`.
- Local viewer source reviewed: `ImportModelMethods.cs`,
  `AdjustModelPanelMethods.cs`, and `ScenarioSceneManager.cs` under
  `.build/vizard-ui-source/VizardUnityProject/Assets/Scripts/MainScene/`.
