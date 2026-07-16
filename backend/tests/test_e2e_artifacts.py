"""浏览器验收截图只能经显式 opt-in 更新仓内金图。"""

from __future__ import annotations

import re
import runpy
import tempfile
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[2]
E2E_DIR = REPO / "frontend" / "e2e"


def _resolver():
    namespace = runpy.run_path(str(E2E_DIR / "_artifacts.py"))
    return namespace["resolve_shots_dir"]


def test_artifact_router_requires_explicit_golden_update(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    resolve_shots_dir = _resolver()

    monkeypatch.delenv("UPDATE_GOLDENS", raising=False)
    monkeypatch.setenv("FLAI_E2E_ARTIFACT_DIR", str(REPO / "docs" / "reviews"))
    with pytest.raises(RuntimeError, match="UPDATE_GOLDENS=1"):
        resolve_shots_dir(REPO, "contract-shots")

    monkeypatch.setenv("FLAI_E2E_ARTIFACT_DIR", str(tmp_path))
    assert resolve_shots_dir(REPO, "contract-shots") == tmp_path / "contract-shots"

    monkeypatch.setenv("UPDATE_GOLDENS", "1")
    assert resolve_shots_dir(REPO, "contract-shots") == (
        REPO / "docs" / "reviews" / "contract-shots"
    )


def test_default_artifact_resolution_has_no_filesystem_side_effect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resolve_shots_dir = _resolver()
    monkeypatch.delenv("UPDATE_GOLDENS", raising=False)
    monkeypatch.delenv("FLAI_E2E_ARTIFACT_DIR", raising=False)

    target = resolve_shots_dir(REPO, "contract-shots")

    assert target.parent.parent == Path(tempfile.gettempdir())
    assert not target.parent.exists()
    assert not target.exists()


def test_screenshot_suites_use_shared_artifact_router() -> None:
    screenshot_suites = []
    for path in sorted(E2E_DIR.glob("*_acceptance.py")):
        source = path.read_text(encoding="utf-8")
        if ".screenshot(" not in source:
            continue
        screenshot_suites.append(path)
        assert "from _artifacts import resolve_shots_dir" in source
        assert re.search(
            r'^SHOTS\s*=\s*resolve_shots_dir\(REPO,\s*["\'][^"\']+["\']\)\s*$',
            source,
            re.MULTILINE,
        )
        for line in source.splitlines():
            if ".screenshot(" in line:
                assert "SHOTS /" in line

    assert screenshot_suites, "至少应有一套浏览器验收生成截图"
