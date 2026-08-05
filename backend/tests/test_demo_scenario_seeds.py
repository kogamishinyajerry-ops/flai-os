"""demo 场景种子(data/demo_scenarios/*.json)的确定性投影门。

每个种子的 expected_generalization 必须能被 AssetDraftBuilder.preview() 投影成
完整草稿包:校验达到 ready_for_human_review、无 blocking、副作用四项全 False、
确定性投影不用 LLM。新增场景种子后此门自动覆盖(参数化按目录收集)。

与 scripts/verify_cooking_demo.py 同一口径;脚本给 workshop 现场跑,此测试进 CI。
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from backend.app.ontology.asset_builder import AssetDraftBuilder

REPO_ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = REPO_ROOT / "data" / "demo_scenarios"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
_EFFECT_KEYS = (
    "writes_database",
    "executes_work",
    "registers_asset",
    "promotes_asset",
)


def _seed_files() -> list[Path]:
    return sorted(SCENARIO_DIR.glob("*.json"))


def _build_conversation(seed: dict) -> dict:
    """种子 seed_conversation 的 user 轮构成 Work Case 血缘;assistant_expected_topic
    是教学提示不是真实消息,不参与投影。"""
    messages = [
        {"id": f"m{i}", "role": "user", "content": turn["content"], "file_ids": []}
        for i, turn in enumerate(seed["seed_conversation"], start=1)
        if turn.get("role") == "user"
    ]
    return {
        "id": f"conv_demo_{seed['scenario_id']}_001",
        "agent_id": "life_guide_agent",
        "status": "concluded",
        "messages": messages,
    }


def test_at_least_three_scenarios_seeded() -> None:
    """L1 demo 承诺三个场景(做饭/旅行/装修),种子缺失即测试红。"""
    ids = {p.stem for p in _seed_files()}
    assert {"cooking", "travel", "renovation"} <= ids, f"缺场景种子: {ids}"


@pytest.mark.parametrize("seed_path", _seed_files(), ids=lambda p: p.stem)
def test_seed_projects_clean_bundle(seed_path: Path) -> None:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    conversation = _build_conversation(seed)
    assert conversation["messages"], "种子必须至少含一条 user 轮"

    bundle = AssetDraftBuilder().preview(
        conversation=conversation, generalization=seed["expected_generalization"]
    )

    assert bundle["schema_version"] == "asset_draft_bundle.v1"
    assert bundle["status"] == "draft"
    assert _DIGEST_RE.match(bundle["draft_digest"])

    validation = bundle["validation"]
    assert validation["state"] == "ready_for_human_review"
    assert validation["blocking_count"] == 0, validation["issues"]
    assert bundle["review"]["required"] is True

    for key in _EFFECT_KEYS:
        assert bundle["effects"][key] is False, f"effects.{key} 必须为 False"
    assert bundle["generation"]["kind"] == "deterministic_projection"
    assert bundle["generation"]["llm_used"] is False


@pytest.mark.parametrize("seed_path", _seed_files(), ids=lambda p: p.stem)
def test_seed_same_generalization_is_digest_stable(seed_path: Path) -> None:
    """内容寻址铁律:同一种子投影两次,digest 必须逐字节一致。"""
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    conversation = _build_conversation(seed)
    builder = AssetDraftBuilder()
    first = builder.preview(
        conversation=conversation, generalization=seed["expected_generalization"]
    )
    second = builder.preview(
        conversation=conversation, generalization=seed["expected_generalization"]
    )
    assert first["draft_digest"] == second["draft_digest"]
    assert first["task_pattern"]["content_digest"] == second["task_pattern"]["content_digest"]
