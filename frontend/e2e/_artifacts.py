"""Shared screenshot destination contract for browser acceptance scripts."""

from __future__ import annotations

import os
from pathlib import Path


ARTIFACT_ROOT_ENV = "FLAI_E2E_ARTIFACT_ROOT"


def artifact_dir(repo_root: Path, suite_dir: str) -> Path:
    """Return one suite's screenshot directory.

    Direct script runs retain the historical ``docs/reviews/<suite>`` location.
    Verification gates can set ``FLAI_E2E_ARTIFACT_ROOT`` to keep generated
    evidence outside the tracked worktree.
    """

    configured_root = os.environ.get(ARTIFACT_ROOT_ENV)
    root = Path(configured_root).expanduser() if configured_root else repo_root / "docs" / "reviews"
    return root / suite_dir
