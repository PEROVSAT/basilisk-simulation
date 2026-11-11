# PEROVSAT telemetry UI for Vizard

This is a custom **Unity viewer overlay**, not a change to simulation physics.
It replaces the stock storage pane for messages containing `Battery SOC` and
`Face +X illumination`. Other spacecraft storage panes and VR retain the
original Vizard UI. Existing live streams and saved Vizard files are supported.

## Design

- Barlow Regular for labels and Barlow SemiBold for large numerical readings.
- Slate background (`#101925`), inset surfaces (`#192637`), pale text (`#EDF3FA`).
- Teal battery/pacing accents, amber sunlight, blue secondary metrics, coral low SOC.
- Grouped power summary, a two-column six-face illumination grid, and timing rows.
- Values and state text are always expanded; no hover or expand action is required.
- On short screens, scroll inside the pane to reach timing; drag its header to move it.
- Existing close/menu controls are retained. `--compact-status` omits unavailable
  diagnostics; `--hide-status` continues to hide the entire pane.
- State text is read from each current frame, avoiding the stock UI's cached
  unit string. A paused/no-new-frame footer indicates that displayed values are held.

## Current status

The overlay and build helper are prepared and have been applied to the local
source checkout at `.build/vizard-ui-source/VizardUnityProject`. Four installer
safety/idempotency tests pass. **Unity is not installed on this machine: the C#
overlay has not been compiled, rendered or visually verified, and no custom
executable has been built.** The installed Vizard application is unchanged.

Source integration was inspected against upstream Vizard commit
`e6d3f600cf1e7f4022d93f1a3cf057acccbd0932`, which uses Unity **6000.0.68f1**.
The local checkout is sparse and large assets were deliberately not downloaded.

## 1. Install Unity on Windows

Install [Unity Hub](https://unity.com/download), sign in as required, and install
**6000.0.68f1** from the [Unity editor archive](https://unity.com/releases/editor/archive).
Include **Windows Build Support (Mono)**. Complete any license activation in Hub.
Choose a drive with enough free space for the editor, Vizard assets, package
cache, imported Library, and built player; this can require many gigabytes.

Follow [upstream Vizard's setup guide](https://github.com/AVSLab/vizard) for the
base project. Paid file-browser assets and optional HD planet bundles are not
required for this overlay.

## 2. Finish downloading the prepared checkout

Run in **Windows PowerShell**, not inside the simulation container:

```powershell
cd G:\basilisk-simulation
git -C .build/vizard-ui-source sparse-checkout disable
git -C .build/vizard-ui-source lfs pull
```

This retrieves the remaining project files and large assets while preserving
the applied UI change. If you cloned with `GIT_LFS_SKIP_SMUDGE` set, unset it
before importing assets or run `git lfs pull` explicitly as above.

For a fresh checkout on another machine:

```powershell
git clone https://github.com/AVSLab/vizard.git .build/vizard-ui-source
git -C .build/vizard-ui-source checkout e6d3f600cf1e7f4022d93f1a3cf057acccbd0932
git -C .build/vizard-ui-source lfs pull
py vizard-ui/install.py --project .build/vizard-ui-source/VizardUnityProject
```

The installer requires Python 3 and no third-party Python dependencies. If
Windows Python is unavailable, run this from **WSL**, with Docker running:

```bash
cd /mnt/g/basilisk-simulation
docker run --rm -v "$PWD:/workspace" -w /workspace perovsat-bsk \
  python vizard-ui/install.py --project .build/vizard-ui-source/VizardUnityProject
```

It installs two C# files and the licensed Barlow fonts, and inserts one call
into `GenericStoragePanelMethods.InitializePanel`. Re-running is safe; locally
edited overlay files are protected from silent overwrites. After editing this
repository's overlay, rerun the installer to update the Unity checkout.

## 3. Import and build the custom viewer

1. In Unity Hub, **Add project from disk** and select
   `G:\basilisk-simulation\.build\vizard-ui-source\VizardUnityProject`.
2. Open with Unity 6000.0.68f1 and let package/asset imports finish.
3. Import **TMP Essential Resources** if requested. Upstream recommends opening
   `VizardStartupScene` and selecting `StartUpCanvas/Panel/VersionText` to trigger
   the importer. Resolve any project import/compiler errors before continuing.
4. Choose **PEROVSAT → Build Windows Viewer** from the Unity menu.
5. The new player is written to `Builds/Perovsat/Vizard.exe` inside the Unity
   project. Run that executable, keeping the adjacent data files together.

After the first import and license setup, a command-line build is also available
in **Windows PowerShell**. Adjust the editor path if installed elsewhere:

```powershell
& 'C:\Program Files\Unity\Hub\Editor\6000.0.68f1\Editor\Unity.exe' `
  -batchmode -quit -buildTarget Win64 `
  -projectPath 'G:\basilisk-simulation\.build\vizard-ui-source\VizardUnityProject' `
  -executeMethod PerovsatBuild.BuildWindows `
  -perovsatOutput 'G:\basilisk-simulation\.build\vizard-custom\Vizard.exe' `
  -logFile 'G:\basilisk-simulation\.build\vizard-ui-build.log'
```

The helper requires a successful Unity build result. Inspect the log for compile
or license failures; the existence of this source overlay is not proof of a build.

## 4. Verify it with the real simulation

In **WSL**:

```bash
cd /mnt/g/basilisk-simulation
VIZARD_HOST=$(ip route show default | awk '{print $3; exit}')
echo "Vizard socket: tcp://${VIZARD_HOST}:5556"
make live VIZARD_ADDRESS="$VIZARD_HOST" ARGS='--duration 300 --factor 1 --viz-timeout 600'
```

Use the **new custom executable**, select Receive & Reply and Live Display,
and start visualization after the listener prompt. Verify:

- Battery, power and six face percentages are readable without expansion.
- Barlow fonts load, numerical text fits, and states update while the run advances.
- Dragging, scrolling, closing and reopening the pane work at your screen size.
- Pausing holds values and updates the footer; resuming clears the held indication.
- A recorded file can be played forward/backward without stale status strings.
- Compact mode omits diagnostics and the standard hidden-pane flag still works.

For a faster sunlight/eclipse cycle, use `--duration 6000 --factor 20`.
The same tested Python telemetry supplies both stock and custom viewers.

## Files and tests

`Runtime/PerovsatTelemetryPanel.cs` builds and updates the UI. The build entry
point is `Editor/PerovsatBuild.cs`. Font provenance and licensing are in `Fonts/`.
`install.py` applies the small source integration without vendoring the whole
Unity project into this repository.

```bash
python -m unittest discover -s tests -p test_vizard_ui_install.py -v
```

These tests validate installation safety, compatibility guards and idempotency.
They do not compile C#, substitute for Unity tests, or establish visual quality.
