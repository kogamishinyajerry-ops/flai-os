"""monitor_adapter_gen_agent workflow（ADR-0020 R2 / ADR-0022）。

「产生工作流的工作流」的平台实体：给一个新求解器/新工作流的**真实历史 run 产物
目录**，起草它接入实时监控所需的全部件——**只起草，不生效**（注册是人的动作，
人是唯一签发者）。

分层（契约草案 §6 + docs/09 §3 智能展示红线）：
- **实质 = 确定性接地**：module.json 骨架 / parser 桩 / 三档证据（VERIFIED/PROPOSED/
  UNVERIFIED）全部来自承重核（sim-live-hub tools/adapter_gen.py，经 monitor_adapter_recon
  工具子进程），接地保证由核提供，本 agent 不重复实现、不改一字证据。核不可达/
  侦察失败 → 诚实 failed（实质产物拿不到就没有草案，绝不空壳顶替）。
- **叙事层 = 生成器建议**（可选）：由推理模型据接地报告 + display_hints 给出「当前展示
  什么曲线/场/参数信息量最大」的选择建议 + 审阅导语——**选择权可智能化（标注为
  生成器建议），数据权绝不**（模型绝不生成/插值/美化任何上屏数值）。模型不可达时
  诚实标注「叙述未生成」，**绝不因叙事层失败丢弃已接地的实质草案**（与 fta 不同：
  fta 的 LLM 是实质，本 agent 的 LLM 只是叙事）。

requires_human_review=true：workflow 正常返回 success，Runtime 转 waiting_review，
由工程师按诚实清单跑 tamper 实证 + 代码审后，人工注册进监控节点（draft 永不自动生效）。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

_MODULE_DRAFT = "module.json.draft"
_PARSER_STUB = "parser.py.stub"
_REVIEW_MD = "REVIEW.md"

_WATERMARK = (
    "> ⚠ **本 adapter 为 monitor_adapter_gen 生成的草案，PROPOSED/UNVERIFIED 项人工"
    "确认前不得注册；注册前必须按诚实清单跑 tamper 实证（篡改必咬红 + 真跑必绿）。"
    "「全绿但无咬合实证 = 假信心」，视同未验证（docs/09 §4）。**"
)


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _load_system_prompt() -> str:
    return Path(__file__).with_name("prompt.md").read_text(encoding="utf-8").strip()


def run(context: dict[str, Any]) -> dict[str, Any]:
    event_logger = context["event_logger"]
    tool_registry = context["tool_registry"]
    model_gateway = context["model_gateway"]
    inputs = context["inputs"]
    output_dir = context["output_dir"]
    agent_config = context["agent_config"]

    target_repo_path: str = inputs["target_repo_path"]
    sample_run_dir: str = inputs["sample_run_dir"]
    solver_hint = inputs.get("solver_hint")
    display_hints = inputs.get("display_hints") or []
    module_name = inputs.get("module_name")

    profile = agent_config["model"]["profile"]  # =reasoning（以 agent.yaml 声明为准）

    # ① 确定性接地侦察（承重=核，经 monitor_adapter_recon 工具子进程）
    recon_payload: dict[str, Any] = {"sample_run_dir": sample_run_dir}
    if module_name:
        recon_payload["module_name"] = module_name
    if solver_hint:
        recon_payload["solver_hint"] = solver_hint

    event_logger.log("recon_started", {"sample_run_dir": sample_run_dir,
                                        "target_repo_path": target_repo_path})
    recon = tool_registry.call("monitor_adapter_recon", recon_payload)
    if recon.get("status") == "failed":
        # 实质产物（接地草案）拿不到 → 诚实 failed，绝不空壳顶替
        return _fail(
            "侦察承重核未产出草案（core_available="
            f"{recon.get('core_available')}）：{recon.get('error_message')}"
        )

    draft = recon["draft"]
    grounding_ok = bool(recon.get("grounding_ok"))
    grounding_failures = recon.get("grounding_failures") or []
    module_json_draft = draft["module_json_draft"]
    parser_stub = draft["parser_stub"]

    n_verified = _count_verified(draft.get("verified") or {})
    n_proposed = len(draft.get("proposed") or [])
    n_unverified = len(draft.get("unverified") or [])
    event_logger.log("recon_grounded", {
        "grounding_ok": grounding_ok,
        "verified": n_verified, "proposed": n_proposed, "unverified": n_unverified,
    })

    # ② 叙事层「生成器建议」（可选，选择权可智能化/数据权绝不）——模型不可达诚实降级
    narrative, narrative_note = _maybe_narrative(
        model_gateway, profile, draft, solver_hint, display_hints, event_logger
    )

    # ③ 落草案三件（实质接地产物 + 审阅 REVIEW.md）
    (Path(output_dir) / _MODULE_DRAFT).write_text(
        json.dumps(module_json_draft, ensure_ascii=False, indent=2), encoding="utf-8")
    (Path(output_dir) / _PARSER_STUB).write_text(parser_stub, encoding="utf-8")
    (Path(output_dir) / _REVIEW_MD).write_text(
        _render_review(target_repo_path, sample_run_dir, solver_hint, display_hints,
                       draft, grounding_ok, grounding_failures, narrative, narrative_note),
        encoding="utf-8")

    event_logger.log("draft_written", {
        "artifacts": [_MODULE_DRAFT, _PARSER_STUB, _REVIEW_MD],
        "narrative_generated": narrative is not None,
    })

    summary = {
        "target_repo_path": target_repo_path,
        "sample_run_dir": sample_run_dir,
        "grounding_ok": grounding_ok,
        "verified": n_verified,
        "proposed": n_proposed,
        "unverified": n_unverified,
        "narrative_generated": narrative is not None,
        "human_review_required": True,
        "artifacts": [_MODULE_DRAFT, _PARSER_STUB, _REVIEW_MD],
    }
    # 返回 success ≠ completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}


def _count_verified(verified: dict[str, Any]) -> int:
    return sum(len(verified.get(k) or []) for k in
               ("text_evidence", "binary_evidence", "presence_evidence"))


def _maybe_narrative(model_gateway, profile, draft, solver_hint, display_hints,
                     event_logger) -> tuple[str | None, str]:
    """尝试生成「生成器建议」叙事；模型不可达则诚实降级（返回 None + 说明），
    绝不让叙事层失败丢弃已接地的实质草案。模型只据接地报告给『展示什么』的选择
    建议，绝不生成任何数值/数据（数据权红线）。"""
    context_report = _narrative_context(draft, solver_hint, display_hints)
    messages = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": context_report},
    ]
    try:
        event_logger.log("narrative_started", {"profile": profile})
        result = model_gateway.chat(profile, messages)
    except Exception as exc:  # noqa: BLE001 - 叙事层失败必须降级不能拖垮实质草案
        event_logger.log("narrative_skipped", {"reason": str(exc)[:200]})
        return None, f"AI 生成器建议未生成（模型不可达：{str(exc)[:120]}）——请直接审阅上方三档接地证据与诚实清单。"
    text = result.get("content")
    if not isinstance(text, str) or not text.strip():
        event_logger.log("narrative_skipped", {"reason": "empty_content"})
        return None, "AI 生成器建议未生成（模型返回空内容）——请直接审阅上方三档接地证据与诚实清单。"
    truncated = result.get("finish_reason") == "length"
    note = "（因长度上限截断，建议可能不完整）" if truncated else ""
    return text.strip(), note


def _narrative_context(draft: dict[str, Any], solver_hint, display_hints) -> str:
    """喂给模型的接地事实摘要（只给已接地的 aspect 名，不给模型编造空间）。"""
    verified = draft.get("verified") or {}
    aspects = [e.get("aspect") for e in verified.get("text_evidence") or []]
    aspects += [e.get("aspect") for e in verified.get("binary_evidence") or []]
    proposed = [f"{p.get('aspect')}={p.get('value')}" for p in (draft.get("proposed") or [])]
    unverified = [u.get("aspect") for u in (draft.get("unverified") or [])]
    lines = [
        "以下是确定性承重核对一个仿真 run 目录的接地侦察结果（你只能据此给『展示什么』"
        "的选择建议，绝不生成或猜测任何数值/数据）：",
        f"- 求解器提示：{solver_hint or '（未提供）'}",
        f"- 领域侧优先展示意愿 display_hints：{display_hints or '（未提供）'}",
        f"- VERIFIED（逐字接地）aspects：{aspects or '（无）'}",
        f"- PROPOSED（结构推断待人确认）：{proposed or '（无）'}",
        f"- UNVERIFIED（无法接地，如实报缺）：{unverified or '（无）'}",
    ]
    return "\n".join(lines)


def _render_review(target_repo_path, sample_run_dir, solver_hint, display_hints,
                   draft, grounding_ok, grounding_failures, narrative, narrative_note) -> str:
    verified = draft.get("verified") or {}
    L: list[str] = []
    L.append(f"# {draft.get('module_name') or '新模块'} · 监控接入草案（monitor_adapter_gen 生成）")
    L.append("")
    L.append(_WATERMARK)
    L.append("")
    L.append("## 接入对象")
    L.append("")
    L.append(f"- 目标工作流仓：`{target_repo_path}`（只读侦察，他仓神圣）")
    L.append(f"- 侦察样本 run：`{sample_run_dir}`")
    L.append(f"- 求解器提示：{solver_hint or '（未提供）'}")
    L.append(f"- 接地自检：{'全部通过 ✓' if grounding_ok else f'✗ {len(grounding_failures)} 条未通过：{grounding_failures}'}")
    L.append("")
    L.append("## ✅ VERIFIED（逐字/magic/存在性接地，来自承重核，未改一字）")
    for ev in verified.get("text_evidence") or []:
        L.append(f"- `{ev.get('aspect')}` ← `{ev.get('file')}`：`{ev.get('sample')}`")
    for ev in verified.get("binary_evidence") or []:
        L.append(f"- `{ev.get('aspect')}` ← `{ev.get('file')}`（二进制 magic=`{ev.get('magic')}`）")
    for ev in verified.get("presence_evidence") or []:
        L.append(f"- `{ev.get('aspect')}` ← `{ev.get('file')}`（文件存在）")
    L += ["", "## ⚙ PROPOSED（结构推断，需人工确认）"]
    for p in draft.get("proposed") or []:
        L.append(f"- `{p.get('aspect')}` = `{p.get('value')}` — {p.get('why')}")
    L += ["", "## ❓ UNVERIFIED（无法接地，如实报缺，绝不编造）"]
    for u in draft.get("unverified") or []:
        L.append(f"- `{u.get('aspect')}`：{u.get('reason')}")
    L += ["", "## 🔒 诚实清单（注册前必须逐条实证）"]
    for i, it in enumerate(draft.get("honesty_checklist") or [], 1):
        L.append(f"{i}. {it}")

    L += ["", "## 🤖 生成器展示建议（叙事层——选择权，数据权绝不智能化）"]
    if narrative is not None:
        if narrative_note:
            L.append(f"> {narrative_note}")
            L.append("")
        L.append("> 以下为 AI 生成器对「当前展示什么信息量最大」的**选择建议**，属叙事层，"
                 "采纳与否由人决定；它绝不生成/插值/美化任何上屏数值（数据权红线）。")
        L.append("")
        L.append(narrative)
    else:
        L.append(f"> {narrative_note}")
    L.extend(["", "---", "", *_REVIEW_GUIDE_LINES])
    return "\n".join(L) + "\n"


# 平台撰写的审核指引（非模型输出）——放行/注册前批判性阅读。
_REVIEW_GUIDE_LINES = [
    "## 放行/注册前审核指引（平台撰写，非模型输出）",
    "",
    "本草案由 monitor_adapter_gen 生成。**批准即视为你已作为工程师背书其接入正确性。**"
    "注册进监控节点前请至少逐条核对：",
    "",
    "1. **UNVERIFIED 项**：每条是否已通过人工确认或加 wrapper 解决？未解决绝不注册。",
    "2. **PROPOSED 项**：结构推断是否与目标仓真实落盘逻辑一致（尤其 run_discovery 的 glob "
    "层级、marker_file 的落盘顺序、帧序号→迭代号映射）？",
    "3. **tamper 实证**：是否已按诚实清单跑「杀进程/断源必咬红 + 真跑必绿」？未实证 = 假信心。",
    "4. **数据权红线**：parser 是否只读真源、零数值生成/插值？生成器建议只影响『展示什么』"
    "（选择权），绝不影响『展示的数值』（数据权）。",
    "",
    "> 如有任何一条无法确认，应**拒绝**并附理由，而非「先批了再说」。",
]
