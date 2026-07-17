"""fault_history_agent workflow。

包内合成案例库由确定性代码检索；LLM 只在候选 fault_ref 白名单内排序并摘要。
输出在落盘前通过 output_schema.json，且任务由 agent.yaml 强制人工审核。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from jsonschema import validate

_JSON_NAME = "fault_history.json"
_MD_NAME = "fault_history.md"
_KNOWN_MODELS = ("XR-100", "XR-300", "巡线-7")


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _package_path(*parts: str) -> Path:
    return Path(__file__).resolve().parent.joinpath(*parts)


def _load_json(*parts: str) -> dict[str, Any]:
    data = json.loads(_package_path(*parts).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"包内 JSON 顶层必须是对象：{'/'.join(parts)}")
    return data


def _normalize(value: str) -> str:
    return re.sub(r"\s+", "", value).lower()


def _candidate_score(case: dict[str, Any], problem: str, model_type: str | None) -> int:
    haystack = _normalize(problem)
    matched = sum(1 for tag in case["tags"] if _normalize(tag) in haystack)
    if matched == 0:
        return 0
    model_bonus = 1 if model_type is not None and case["model"] == model_type else 0
    return matched * 10 + model_bonus


def _select_candidates(
    cases: list[dict[str, Any]], problem: str, model_type: str | None
) -> list[dict[str, Any]]:
    scored = [
        (_candidate_score(case, problem, model_type), case)
        for case in cases
    ]
    selected = [(score, case) for score, case in scored if score > 0]
    selected.sort(key=lambda item: (-item[0], item[1]["fault_ref"]))
    return [{**case, "retrieval_score": score} for score, case in selected[:8]]


def _ranking_message(
    problem: str, model_type: str | None, candidates: list[dict[str, Any]]
) -> str:
    compact = [
        {
            "fault_ref": case["fault_ref"],
            "model": case["model"],
            "title": case["title"],
            "symptoms": case["symptoms"],
            "cause": case["cause"],
            "disposition": case["disposition"],
            "tags": case["tags"],
        }
        for case in candidates
    ]
    return (
        f"当前型号：{model_type or '未指定'}\n"
        f"当前问题：{problem}\n\n"
        "候选合成记录（只能从这些 fault_ref 中选择）：\n"
        + json.dumps(compact, ensure_ascii=False, indent=2)
    )


def _parse_ranking(raw: str, candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    text = raw.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("排序模型回复中没有 JSON 对象")
    payload = json.loads(text[start : end + 1])
    ranked = payload.get("ranked") if isinstance(payload, dict) else None
    if not isinstance(ranked, list):
        raise ValueError("排序模型未返回 ranked 数组")

    by_ref = {case["fault_ref"]: case for case in candidates}
    accepted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in ranked:
        if not isinstance(item, dict):
            continue
        fault_ref = item.get("fault_ref")
        basis = item.get("similarity_basis")
        summary = item.get("disposition_summary")
        if (
            not isinstance(fault_ref, str)
            or fault_ref not in by_ref
            or fault_ref in seen
            or not isinstance(basis, str)
            or not basis.strip()
            or not isinstance(summary, str)
            or not summary.strip()
        ):
            continue
        seen.add(fault_ref)
        accepted.append(
            {
                "case": by_ref[fault_ref],
                "similarity_basis": basis.strip()[:500],
                "disposition_summary": summary.strip()[:1000],
            }
        )
        if len(accepted) == 5:
            break
    if not accepted:
        raise ValueError("排序模型没有返回任何候选白名单内的非空结果")
    return accepted


def _base_output(problem: str, model_type: str | None) -> dict[str, Any]:
    return {
        "problem_description": problem,
        "requested_model_type": model_type,
        "findings": [],
        "refusals": [],
        "cross_model_matches": [],
        "human_review_required": True,
        "artifacts": [_JSON_NAME, _MD_NAME],
    }


def _build_output(
    problem: str, model_type: str | None, ranked: list[dict[str, Any]]
) -> dict[str, Any]:
    output = _base_output(problem, model_type)
    evidence = []
    for row in ranked:
        case = row["case"]
        quote = f"合成原因：{case['cause']} 合成处置：{case['disposition']}"
        evidence.append(
            {
                "kind": "fault_case",
                "source_ref": f"合成排故记录#{case['fault_ref']}",
                "quote": quote[:300],
                "resolved": False,
            }
        )
    refs = "、".join(row["case"]["fault_ref"] for row in ranked)
    output["findings"] = [
        {
            "claim": f"检出 {len(ranked)} 条可供人工比对的合成历史记录（{refs}）；相似不等于适用。",
            "evidence": evidence,
            "confidence": {
                "level": "low",
                "basis": "多案例" if len(evidence) > 1 else "单源",
            },
        }
    ]

    baseline_model = model_type or ranked[0]["case"]["model"]
    output["cross_model_matches"] = [
        {
            "model": row["case"]["model"],
            "fault_ref": row["case"]["fault_ref"],
            "similarity_basis": row["similarity_basis"],
            "disposition_summary": row["disposition_summary"],
        }
        for row in ranked
        if row["case"]["model"] != baseline_model
    ]
    return output


def _render_markdown(output: dict[str, Any], ranked: list[dict[str, Any]]) -> str:
    lines = [
        "# 历史故障相似案例检索报告（合成演示）",
        "",
        "> ⚠ **demo 语料全合成，真实性未核。相似不等于适用；所有处置建议必须经人签发。**",
        "",
        "## 查询",
        "",
        f"- 问题描述：{output['problem_description']}",
        f"- 指定型号：{output['requested_model_type'] or '未指定'}",
        "",
    ]
    if output["refusals"]:
        lines.extend(["## 覆盖结果", ""])
        for refusal in output["refusals"]:
            lines.extend(
                [
                    f"- 拒答原因：{refusal['reason']}",
                    f"- 建议：{refusal['suggestion']}",
                ]
            )
        lines.append("")
    else:
        lines.extend(["## 推荐案例（待人工复核）", ""])
        for index, row in enumerate(ranked, start=1):
            case = row["case"]
            lines.extend(
                [
                    f"### {index}. {case['fault_ref']} · {case['model']}",
                    "",
                    f"- 标题：{case['title']}",
                    f"- 历史现象（合成）：{case['symptoms']}",
                    f"- 历史原因（合成）：{case['cause']}",
                    f"- 相似依据（AI 排序说明）：{row['similarity_basis']}",
                    f"- 处置摘要（AI 摘要，仅供参考）：{row['disposition_summary']}",
                    "",
                ]
            )
    lines.extend(
        [
            "## 人工审核边界",
            "",
            "本报告不得直接转化为维修指令、根因结论、适航判断或安全放行。审核人应回到正式故障记录、当前型号资料与现场证据逐项确认。",
            "",
        ]
    )
    return "\n".join(lines)


def _write_outputs(output_dir: str, output: dict[str, Any], ranked: list[dict[str, Any]]) -> None:
    schema = _load_json("output_schema.json")
    validate(output, schema)
    root = Path(output_dir)
    (root / _JSON_NAME).write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (root / _MD_NAME).write_text(_render_markdown(output, ranked), encoding="utf-8")


def run(context: dict[str, Any]) -> dict[str, Any]:
    event_logger = context["event_logger"]
    model_gateway = context["model_gateway"]
    inputs = context["inputs"]
    output_dir = context["output_dir"]
    agent_config = context["agent_config"]

    problem: str = inputs["problem_description"].strip()
    raw_model_type = inputs.get("model_type")
    model_type = raw_model_type.strip() if isinstance(raw_model_type, str) else None

    library = _load_json("data", "fault_cases.json")
    cases = library.get("cases")
    if library.get("synthetic") is not True or not isinstance(cases, list):
        return _fail("包内故障案例库缺少 synthetic=true 或 cases 数组，拒绝运行")

    if model_type is not None and model_type not in _KNOWN_MODELS:
        output = _base_output(problem, model_type)
        output["refusals"] = [
            {
                "question": f"检索型号 {model_type} 的历史故障",
                "reason": f"型号 {model_type} 未收录；当前仅覆盖 {', '.join(_KNOWN_MODELS)}。",
                "suggestion": "请核对型号，或转人工故障记录库查询；不得用其他型号直接替代。",
            }
        ]
        _write_outputs(output_dir, output, [])
        event_logger.log("fault_history_model_uncovered", {"model_type": model_type})
        return {"status": "success", "outputs": [output]}

    candidates = _select_candidates(cases, problem, model_type)
    event_logger.log(
        "fault_history_candidates_selected",
        {
            "model_type": model_type,
            "candidate_refs": [case["fault_ref"] for case in candidates],
        },
    )
    if not candidates:
        output = _base_output(problem, model_type)
        output["refusals"] = [
            {
                "question": problem[:1000],
                "reason": "合成案例库未检出包含相同现象或触发条件标签的记录。",
                "suggestion": "请补充触发条件、恢复方式和故障部位，或转人工故障记录库查询。",
            }
        ]
        _write_outputs(output_dir, output, [])
        return {"status": "success", "outputs": [output]}

    profile = agent_config["model"]["profile"]
    event_logger.log(
        "fault_history_ranking_started",
        {"profile": profile, "candidate_count": len(candidates)},
    )
    messages = [
        {"role": "system", "content": _package_path("prompt.md").read_text(encoding="utf-8")},
        {"role": "user", "content": _ranking_message(problem, model_type, candidates)},
    ]
    result = model_gateway.chat(profile, messages)
    raw = result.get("content")
    if not isinstance(raw, str) or not raw.strip():
        return _fail("排序模型返回空内容，无可核验结果可存（诚实失败）")
    if result.get("finish_reason") == "length":
        return _fail("排序模型输出被截断，拒绝把不完整排序写成报告")
    try:
        ranked = _parse_ranking(raw, candidates)
    except (json.JSONDecodeError, ValueError) as exc:
        return _fail(f"排序模型输出未通过候选白名单契约：{exc}")

    output = _build_output(problem, model_type, ranked)
    _write_outputs(output_dir, output, ranked)
    event_logger.log(
        "fault_history_report_generated",
        {
            "ranked_refs": [row["case"]["fault_ref"] for row in ranked],
            "cross_model_count": len(output["cross_model_matches"]),
            "artifacts": output["artifacts"],
        },
    )
    return {"status": "success", "outputs": [output]}
