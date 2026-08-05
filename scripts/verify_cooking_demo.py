"""生活场景 demo 种子闭环验证脚本:对 data/demo_scenarios/ 下的每个场景种子,
用其 expected_generalization 调 AssetDraftBuilder.preview(),验证能投影出带
digest 的完整 bundle,且四铁律声明(不写库/不执行/不注册/不晋级、确定性投影)
全部满足。

跑法:
cd /Users/Zhuanz/projects/aircraft-comac/flai-os-life-demo
python3 scripts/verify_cooking_demo.py            # 验证全部场景
python3 scripts/verify_cooking_demo.py cooking    # 只验证指定场景

conversation 由种子 seed_conversation 里的 user 轮确定性构造(助手轮是教学
提示不是真实消息,不进 Work Case 血缘)。
"""
import json
import re
import sys
from pathlib import Path

# 把仓库根目录加到 sys.path,让 backend.app.ontology 可 import
WORKTREE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WORKTREE))

from backend.app.ontology.asset_builder import AssetDraftBuilder

SCENARIO_DIR = WORKTREE / "data" / "demo_scenarios"
_DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")

_EFFECT_KEYS = ("writes_database", "executes_work", "registers_asset", "promotes_asset")


def build_conversation(seed: dict) -> dict:
    """从种子的 seed_conversation 提取 user 轮,构造最小 conversation。"""
    messages = []
    for idx, turn in enumerate(seed["seed_conversation"], start=1):
        if turn.get("role") != "user":
            continue  # assistant_expected_topic 是教学提示,不是真实消息
        messages.append(
            {
                "id": f"m{idx}",
                "role": "user",
                "content": turn["content"],
                "file_ids": [],
            }
        )
    return {
        "id": f"conv_demo_{seed['scenario_id']}_001",
        "agent_id": "life_guide_agent",
        "status": "concluded",
        "messages": messages,
    }


def verify_scenario(seed_path: Path) -> dict:
    with open(seed_path, encoding="utf-8") as f:
        seed = json.load(f)

    conversation = build_conversation(seed)
    assert conversation["messages"], f"{seed_path.name}: 种子里没有 user 轮,无法形成 Work Case"

    builder = AssetDraftBuilder()
    bundle = builder.preview(
        conversation=conversation, generalization=seed["expected_generalization"]
    )

    # ── 结构断言 ────────────────────────────────────────────────
    assert bundle["schema_version"] == "asset_draft_bundle.v1"
    assert bundle["status"] == "draft"
    assert _DIGEST_RE.match(bundle["draft_digest"]), "draft_digest 不是合法 sha256"
    assert bundle["work_case"]["user_message_count"] >= 1

    # ── 校验门:必须达到可交人审状态 ─────────────────────────────
    v = bundle["validation"]
    assert v["state"] == "ready_for_human_review", f"validation.state={v['state']}"
    assert v["blocking_count"] == 0, f"存在 blocking: {v['issues']}"
    assert bundle["review"]["required"] is True

    # ── 铁律自检:副作用四项必须全 False,投影必须确定性 ───────────
    e = bundle["effects"]
    for key in _EFFECT_KEYS:
        assert e[key] is False, f"effects.{key} 必须为 False(铁律:人审唯一签发)"
    g = bundle["generation"]
    assert g["kind"] == "deterministic_projection" and g["llm_used"] is False

    return {"seed": seed, "bundle": bundle}


def main() -> int:
    only = sys.argv[1] if len(sys.argv) > 1 else None
    paths = sorted(SCENARIO_DIR.glob("*.json"))
    if only:
        paths = [p for p in paths if p.stem == only]
    if not paths:
        print(f"没有找到场景种子(参数: {only!r})", file=sys.stderr)
        return 1

    for path in paths:
        result = verify_scenario(path)
        seed, bundle = result["seed"], result["bundle"]
        print(f"=== {seed['scenario_id']}({seed['scenario_name']})闭环验证成功 ===")
        print()
        print("draft_digest:", bundle["draft_digest"])
        wc = bundle["work_case"]
        print(
            "work_case: user_message_count=%d message_count=%d"
            % (wc["user_message_count"], wc["message_count"])
        )
        print("task_pattern.suggested_id:", bundle["task_pattern"]["suggested_id"])
        print("skill.suggested_id:", bundle["skill"]["suggested_id"])
        v = bundle["validation"]
        print(
            "validation: %s(blocking=%d warning=%d)"
            % (v["state"], v["blocking_count"], v["warning_count"])
        )
        e = bundle["effects"]
        print(
            "effects(铁律自检): writes_database=%s executes_work=%s registers_asset=%s promotes_asset=%s"
            % (
                e["writes_database"],
                e["executes_work"],
                e["registers_asset"],
                e["promotes_asset"],
            )
        )
        print(
            "generation: %s llm_used=%s"
            % (bundle["generation"]["kind"], bundle["generation"]["llm_used"])
        )
        print()
        print("桥接 FDE 提示(给教学用):")
        print("  ", seed["teaching_notes"]["bridge_to_fde"])
        print()

    print(
        "全部通过 = %d 个场景的本体论建模闭环可跑,可用于 FDE workshop。" % len(paths)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
