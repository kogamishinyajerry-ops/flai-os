"""Browser acceptance artifact routing.

Routine development verification must not overwrite tracked review evidence.
Set ``UPDATE_GOLDENS=1`` explicitly when a reviewer intends to refresh it.
"""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path


def resolve_shots_dir(repo: Path, suite_name: str) -> Path:
    """Resolve one suite's screenshot directory without touching the filesystem."""

    if os.environ.get("UPDATE_GOLDENS") == "1":
        target = repo / "docs" / "reviews" / suite_name
    else:
        configured_root = os.environ.get("FLAI_E2E_ARTIFACT_DIR")
        run_root = (
            Path(configured_root)
            if configured_root
            else Path(tempfile.gettempdir()) / f"flai-os-e2e-{uuid.uuid4().hex}"
        )
        target = run_root / suite_name
        goldens_root = (repo / "docs" / "reviews").resolve()
        if target.resolve().is_relative_to(goldens_root):
            raise RuntimeError(
                "拒绝把临时 E2E 产物写入 docs/reviews；更新金图必须显式设置 "
                "UPDATE_GOLDENS=1"
            )

    return target
