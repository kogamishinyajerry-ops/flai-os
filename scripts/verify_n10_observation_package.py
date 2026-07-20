#!/usr/bin/env python3
"""Check an exact N10 observation package without changing roadmap state."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.app.governance.n10_observation_gate import (  # noqa: E402
    evaluate_n10_observation_package,
)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Fail-closed completeness check for declared N10 observation records. "
            "It does not authenticate participants, prove usability, prove M4, "
            "or unlock the roadmap."
        )
    )
    parser.add_argument("--package", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    report = evaluate_n10_observation_package(args.package)
    rendered = json.dumps(
        report.as_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
        allow_nan=False,
    ) + "\n"
    sys.stdout.write(rendered)
    return 0 if report.structurally_complete is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
