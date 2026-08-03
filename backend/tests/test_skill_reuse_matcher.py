from __future__ import annotations

import copy
from typing import Any

import pytest

from backend.app.ontology.skill_reuse import SkillReuseMatcher


def _digest(char: str) -> str:
    return f"sha256:{char * 64}"


def _verified_item(
    *,
    package_id: str = "skill_package_0123456789abcdef01234567",
    title: str = "叶片疲劳评估：可复用方法",
    agent_id: str = "fatigue_agent",
    owner: str = "engineer",
    state: str = "approved",
    reuse_eligible: bool = True,
    package_digest: str = _digest("a"),
    candidate_digest: str = _digest("b"),
    skill_digest: str = _digest("c"),
) -> dict[str, Any]:
    skill_revision = {
        "schema_version": "skill_draft.v1",
        "status": "draft",
        "name": title,
        "description": "形成可复核的疲劳评估结果",
        "when_to_use": "需要评估叶片疲劳寿命时",
        "when_not_to_use": ["缺少载荷谱时"],
        "inputs": ["载荷谱"],
        "outputs": ["评估结果"],
        "instructions": ["核验载荷谱", "执行疲劳评估"],
        "verification": ["保留结果摘要"],
        "human_boundaries": ["工程师签发"],
        "content_digest": skill_digest,
    }
    return {
        "package": {
            "schema_version": "candidate_skill_package.v1",
            "id": package_id,
            "version": "0.1.0",
            "package_digest": package_digest,
            "state": state,
            "reuse_eligible": reuse_eligible,
            "source": {
                "candidate_digest": candidate_digest,
                "skill_digest": skill_digest,
                "agent_id": agent_id,
                "initiated_by_username": owner,
            },
        },
        "skill_revision": skill_revision,
        "skill_markdown": (
            "---\n"
            "name: blade-fatigue-assessment\n"
            "description: 形成可复核的疲劳评估结果\n"
            "---\n\n"
            "# 叶片疲劳评估\n"
        ),
    }


class _FakeMaterializer:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.calls: list[dict[str, Any]] = []

    def list_reuse_eligible(
        self,
        conn: object,
        *,
        username: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        self.calls.append({"conn": conn, "username": username, "limit": limit})
        return self.items


def test_exact_core_title_returns_trusted_package_ref_and_verified_method() -> None:
    conn = object()
    item = _verified_item()
    materializer = _FakeMaterializer([item])

    matched = SkillReuseMatcher(materializer).match(
        conn,
        username="engineer",
        segment_messages=[
            {"role": "assistant", "content": "不要采用叶片寿命快速估算"},
            {"role": "user", "content": "请复用叶片疲劳评估完成这份工作"},
        ],
        attachment_filenames=["blade-fatigue.csv"],
    )

    assert materializer.calls == [{"conn": conn, "username": "engineer", "limit": 101}]
    assert matched == {
        "ref": {
            "schema_version": "skill_reuse_ref.v1",
            "package_id": "skill_package_0123456789abcdef01234567",
            "package_version": "0.1.0",
            "package_digest": _digest("a"),
            "candidate_digest": _digest("b"),
            "skill_digest": _digest("c"),
            "skill_name": "叶片疲劳评估：可复用方法",
            "matched_agent_id": "fatigue_agent",
            "review_state": "approved",
            "match_policy_version": "skill_reuse_match.v1",
            "match_basis_digest": (
                "sha256:f9f7ac068f3e0fe7927399cb59f44a9bedaeb7369de921b0d495"
                "d7759e42fd14"
            ),
        },
        "method": {
            "skill_revision": item["skill_revision"],
            "skill_markdown": item["skill_markdown"],
        },
    }


def test_assistant_text_cannot_trigger_reuse() -> None:
    materializer = _FakeMaterializer([_verified_item()])

    matched = SkillReuseMatcher(materializer).match(
        object(),
        username="engineer",
        segment_messages=[
            {"role": "assistant", "content": "可以复用叶片疲劳评估"},
            {"role": "user", "content": "请帮我处理附件"},
        ],
    )

    assert matched is None


def test_pending_owner_mismatch_and_malformed_items_are_skipped_fail_soft() -> None:
    good = _verified_item()
    materializer = _FakeMaterializer(
        [
            _verified_item(state="pending_review", reuse_eligible=False),
            _verified_item(owner="another-engineer"),
            {"package": {"state": "approved"}},
            good,
        ]
    )

    matched = SkillReuseMatcher(materializer).match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "叶片疲劳评估"}],
    )

    assert matched is not None
    assert matched["ref"]["package_id"] == good["package"]["id"]


def test_equal_high_confidence_matches_are_rejected_as_ambiguous() -> None:
    materializer = _FakeMaterializer(
        [
            _verified_item(package_id="skill_package_111111111111111111111111"),
            _verified_item(
                package_id="skill_package_222222222222222222222222",
                package_digest=_digest("d"),
                candidate_digest=_digest("e"),
                skill_digest=_digest("f"),
            ),
        ]
    )

    matched = SkillReuseMatcher(materializer).match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "执行叶片疲劳评估"}],
    )

    assert matched is None


def test_english_token_match_requires_two_distinctive_tokens() -> None:
    english = _verified_item(title="Blade fatigue assessment: reusable method")
    materializer = _FakeMaterializer([english])
    matcher = SkillReuseMatcher(materializer)

    one_token = matcher.match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "Assess this blade"}],
    )
    two_tokens = matcher.match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "Check blade fatigue"}],
    )

    assert one_token is None
    assert two_tokens is not None


def test_real_attachment_filename_can_supply_distinctive_match_tokens() -> None:
    english = _verified_item(title="Blade fatigue assessment: reusable method")

    matched = SkillReuseMatcher(_FakeMaterializer([english])).match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "请处理这个文件"}],
        attachment_filenames=["blade_fatigue_loads.csv"],
    )

    assert matched is not None


def test_match_basis_is_nfc_stable_and_non_nfc_method_is_rejected() -> None:
    item = _verified_item(title="Café blade fatigue: reusable method")
    matcher = SkillReuseMatcher(_FakeMaterializer([item]))

    nfc = matcher.match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "Café blade fatigue"}],
    )
    nfd = matcher.match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "Cafe\u0301 blade fatigue"}],
    )

    assert nfc is not None
    assert nfd is not None
    assert nfc["ref"]["match_basis_digest"] == nfd["ref"]["match_basis_digest"]

    item["skill_revision"]["description"] = "Cafe\u0301"
    assert (
        matcher.match(
            object(),
            username="engineer",
            segment_messages=[{"role": "user", "content": "Café blade fatigue"}],
        )
        is None
    )


def test_unbounded_or_materializer_failure_fails_closed() -> None:
    materializer = _FakeMaterializer([_verified_item()])
    matcher = SkillReuseMatcher(materializer)

    assert (
        matcher.match(
            object(),
            username="engineer",
            segment_messages=[
                {"role": "user", "content": "叶片疲劳评估"} for _ in range(65)
            ],
        )
        is None
    )

    class _UnavailableMaterializer:
        def list_reuse_eligible(self, *args: Any, **kwargs: Any) -> list[Any]:
            raise RuntimeError("package store unavailable")

    assert (
        SkillReuseMatcher(_UnavailableMaterializer()).match(
            object(),
            username="engineer",
            segment_messages=[{"role": "user", "content": "叶片疲劳评估"}],
        )
        is None
    )


def test_101st_package_is_a_sentinel_and_cannot_manufacture_uniqueness() -> None:
    matching = _verified_item(
        package_id="skill_package_000000000000000000000001",
    )
    hidden_tie = _verified_item(
        package_id="skill_package_000000000000000000000065",
        package_digest=_digest("hidden-package"),
        candidate_digest=_digest("hidden-candidate"),
        skill_digest=_digest("hidden-skill"),
    )
    items = [matching]
    for index in range(2, 101):
        item = _verified_item(
            package_id=f"skill_package_{index:024x}",
            title=f"Unrelated calibration method {index}: reusable method",
            package_digest=_digest(f"package-{index}"),
            candidate_digest=_digest(f"candidate-{index}"),
            skill_digest=_digest(f"skill-{index}"),
        )
        items.append(item)
    items.append(hidden_tie)

    class _BoundedMaterializer(_FakeMaterializer):
        def list_reuse_eligible(
            self, conn: object, *, username: str, limit: int
        ) -> list[dict[str, Any]]:
            self.calls.append({"conn": conn, "username": username, "limit": limit})
            return self.items[:limit]

    materializer = _BoundedMaterializer(items)
    matched = SkillReuseMatcher(materializer).match(
        object(),
        username="engineer",
        segment_messages=[{"role": "user", "content": "执行叶片疲劳评估"}],
    )

    assert materializer.calls[0]["limit"] == 101
    assert matched is None


@pytest.mark.parametrize(
    "latest",
    [
        "不要复用叶片疲劳评估",
        "不再复用 叶片疲劳评估",
        "禁止复用叶片疲劳评估",
        "别复用叶片疲劳评估",
        "不要再复用叶片疲劳评估",
        "别再沿用叶片疲劳评估",
        "请勿采用叶片疲劳评估",
        "不得使用叶片疲劳评估",
        "严禁复用叶片疲劳评估",
        "叶片疲劳评估不要复用",
        "不要复用任何已有 Skill，请分析叶片疲劳评估",
        "不要复用叶片疲劳评估，但附件仍叫叶片疲劳评估",
        "不要复用现有方法，例如叶片疲劳评估",
    ],
)
def test_latest_explicit_negation_suppresses_that_skill(latest: str) -> None:
    matcher = SkillReuseMatcher(_FakeMaterializer([_verified_item()]))

    matched = matcher.match(
        object(),
        username="engineer",
        segment_messages=[
            {"role": "user", "content": "请复用叶片疲劳评估"},
            {"role": "user", "content": latest},
        ],
    )

    assert matched is None


@pytest.mark.parametrize(
    "latest",
    [
        "do not reuse blade fatigue assessment",
        "no reuse of blade fatigue assessment",
        "not reuse blade fatigue assessment",
    ],
)
def test_explicit_english_no_reuse_suppresses_that_skill(latest: str) -> None:
    item = _verified_item(title="Blade fatigue assessment: reusable method")
    matcher = SkillReuseMatcher(_FakeMaterializer([item]))

    matched = matcher.match(
        object(),
        username="engineer",
        segment_messages=[
            {"role": "user", "content": "Reuse blade fatigue assessment"},
            {"role": "user", "content": latest},
        ],
    )

    assert matched is None


def test_explicit_no_reuse_persists_across_ordinary_followup_turns() -> None:
    matcher = SkillReuseMatcher(_FakeMaterializer([_verified_item()]))

    matched = matcher.match(
        object(),
        username="engineer",
        segment_messages=[
            {"role": "user", "content": "先看叶片疲劳评估"},
            {"role": "user", "content": "不要复用任何已有 Skill"},
            {"role": "user", "content": "继续分析叶片疲劳评估和同名附件"},
        ],
        attachment_filenames=["叶片疲劳评估.csv"],
    )

    assert matched is None


def test_latest_positive_intent_can_supersede_earlier_negation() -> None:
    item = _verified_item()
    matcher = SkillReuseMatcher(_FakeMaterializer([copy.deepcopy(item)]))

    matched = matcher.match(
        object(),
        username="engineer",
        segment_messages=[
            {"role": "user", "content": "不要复用叶片疲劳评估"},
            {"role": "user", "content": "继续分析同名附件"},
            {"role": "user", "content": "现在可以复用叶片疲劳评估完成这次任务"},
        ],
    )

    assert matched is not None
    assert matched["ref"]["package_id"] == item["package"]["id"]
