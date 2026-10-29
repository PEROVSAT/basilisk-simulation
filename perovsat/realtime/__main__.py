"""Run one real-time scenario: ``python -m perovsat.realtime SCENARIO.json``."""

from __future__ import annotations

import sys
from pathlib import Path

from perovsat.realtime.scenario import load_scenario


def _error_line(exc: BaseException) -> str:
    text = str(exc).strip()
    if not text:
        return type(exc).__name__
    return text.splitlines()[0]


def main(argv: list[str] | None = None) -> int:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if len(arguments) != 1:
        print("usage: python -m perovsat.realtime SCENARIO.json", file=sys.stderr)
        return 2
    try:
        scenario = load_scenario(Path(arguments[0]))
    except (OSError, ValueError) as exc:
        print(_error_line(exc), file=sys.stderr)
        return 2
    from perovsat.realtime.runner import run_scenario

    run_scenario(scenario, Path(arguments[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
