"""Execute one scenario with the vehicle's default Basilisk epoch.

The epoch is not overridden. After the run, ``summary.txt`` notes the selected
devices and that the epoch only places the orbit and the magnetic model.
"""

from __future__ import annotations

from pathlib import Path

from perovsat.realtime.scenario import Scenario, execution_settings
from perovsat.run_config import RunConfig

_EPOCH_LINE = (
    "Basilisk epoch: orbit and magnetic model only; not a FlatSat sample clock"
)


def _device_line(scenario: Scenario) -> str:
    label = ", ".join(scenario.devices) if scenario.devices else "none"
    return f"Devices: {label}"


def _append_summary(path: Path, scenario: Scenario) -> None:
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    present = set(text.splitlines())
    extra = [line for line in (_device_line(scenario), _EPOCH_LINE) if line not in present]
    if not extra:
        return
    with path.open("a", encoding="utf-8") as handle:
        if text and not text.endswith("\n"):
            handle.write("\n")
        handle.write("\n".join(extra) + "\n")


def run_scenario(scenario: Scenario, scenario_path: Path) -> None:
    """Run one vehicle execution and annotate ``summary.txt`` when it exists."""
    output_dir = Path(scenario_path).parent / "output"
    cfg = RunConfig(**execution_settings(scenario), output_dir=output_dir)
    try:
        from perovsat.simulation import PerovSatSimulation

        PerovSatSimulation(cfg).run()
    finally:
        _append_summary(output_dir / "summary.txt", scenario)
