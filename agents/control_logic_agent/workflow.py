"""control_logic_agent workflow：纯确定性结构化生成（M5 泛化验证样板）。

零 LLM（model.profile=none）零工具（tools=[]）：把输入的状态/转移规则规范化
展开为 control_logic.json（状态机 + BFS 不可达态分析）与 control_logic.md
（人读版状态转移表），两产物落 output_dir 由 Runtime 注册。

语义校验（jsonschema 管形状，本文件管语义）：
- 状态不重名；transitions 的 from/to 必须在 states 内。
- 非法 → 诚实 failed，一次性列出**全部**问题（不是遇到第一个就停）。

不可达态分析：约定 states[0] 为初始态，沿声明转移做 BFS——纯图算法，
不理解 condition 的物理语义（条件互斥/覆盖性不在检查范围，见 limitations）。
"""

from __future__ import annotations

import json
import os
from collections import deque
from typing import Any

_LOGIC_JSON = "control_logic.json"
_LOGIC_MD = "control_logic.md"


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _md_escape(value: Any) -> str:
    """Markdown 表格单元格转义：状态名/条件为用户可控文本，`|` 破坏表格结构。"""
    return str(value).replace("|", "\\|")


def _semantic_problems(states: list[str], transitions: list[dict[str, Any]]) -> list[str]:
    problems: list[str] = []
    seen: set[str] = set()
    for s in states:
        if s in seen:
            problems.append(f"状态重名：{s!r}")
        seen.add(s)
    state_set = set(states)
    for i, t in enumerate(transitions):
        if t["from"] not in state_set:
            problems.append(f"transitions[{i}].from={t['from']!r} 不在 states 内")
        if t["to"] not in state_set:
            problems.append(f"transitions[{i}].to={t['to']!r} 不在 states 内")
    return problems


def _unreachable_states(states: list[str], transitions: list[dict[str, Any]]) -> list[str]:
    """BFS 可达性：自初始态（states[0]）沿声明转移可达的集合之外即不可达。"""
    adjacency: dict[str, list[str]] = {s: [] for s in states}
    for t in transitions:
        adjacency[t["from"]].append(t["to"])
    reachable: set[str] = {states[0]}
    queue: deque[str] = deque([states[0]])
    while queue:
        current = queue.popleft()
        for nxt in adjacency[current]:
            if nxt not in reachable:
                reachable.add(nxt)
                queue.append(nxt)
    return [s for s in states if s not in reachable]  # 保持输入顺序


def run(context: dict[str, Any]) -> dict[str, Any]:
    event_logger = context["event_logger"]
    inputs = context["inputs"]
    output_dir = context["output_dir"]

    system_name: str = inputs["system_name"]
    states: list[str] = inputs["states"]
    transitions: list[dict[str, Any]] = inputs["transitions"]

    # ── 1) 语义校验（形状校验已由 Runtime 按 input_schema.json 完成）─────
    event_logger.log("validation_started", {"state_count": len(states), "transition_count": len(transitions)})
    problems = _semantic_problems(states, transitions)
    if problems:
        return _fail("控制逻辑语义校验未通过：" + "；".join(problems))

    # ── 2) 结构化生成：规范化状态机 ─────────────────────────────────────
    unreachable = _unreachable_states(states, transitions)
    logic = {
        "system_name": system_name,
        "initial_state": states[0],
        "states": states,
        "transitions": [
            {"from": t["from"], "to": t["to"], "condition": t["condition"]}
            for t in transitions
        ],
        "analysis": {
            "unreachable_states": unreachable,
            "method": "BFS 自初始态沿声明转移；不解释 condition 语义",
        },
    }
    json_path = os.path.join(output_dir, _LOGIC_JSON)
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(logic, f, ensure_ascii=False, indent=2)
    event_logger.log("structure_generated", {"file": _LOGIC_JSON, "state_count": len(states)})

    # ── 3) 可达性结论 + 人读版 ──────────────────────────────────────────
    event_logger.log("reachability_checked", {"unreachable_states": unreachable})
    md_path = os.path.join(output_dir, _LOGIC_MD)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_render_md(system_name, states, transitions, unreachable))

    summary = {
        "system_name": system_name,
        "state_count": len(states),
        "transition_count": len(transitions),
        "unreachable_count": len(unreachable),
        "artifacts": [_LOGIC_JSON, _LOGIC_MD],
    }
    return {"status": "success", "outputs": [summary]}


def _render_md(
    system_name: str,
    states: list[str],
    transitions: list[dict[str, Any]],
    unreachable: list[str],
) -> str:
    lines: list[str] = []
    lines.append(f"# 控制逻辑描述：{system_name}")
    lines.append("")
    lines.append("> 本文件为输入规则的**确定性结构展开**（纯图算法，无 LLM 参与），"
                 "只保证结构一致性，不构成控制策略的工程结论。")
    lines.append("")
    lines.append(f"- 初始态（约定 states[0]）：`{states[0]}`")
    lines.append(f"- 状态数：{len(states)} ｜ 转移数：{len(transitions)}")
    lines.append("")
    lines.append("## 状态转移表")
    lines.append("")
    lines.append("| From | To | 条件 |")
    lines.append("|---|---|---|")
    for t in transitions:
        lines.append(f"| {_md_escape(t['from'])} | {_md_escape(t['to'])} | {_md_escape(t['condition'])} |")
    lines.append("")
    if unreachable:
        lines.append("## ⚠ 不可达态警告")
        lines.append("")
        lines.append("以下状态自初始态经声明转移不可达（可能缺转移规则，或本就是"
                     "外部事件才能进入的状态——请控制工程师核实）：")
        lines.append("")
        for s in unreachable:
            lines.append(f"- `{_md_escape(s)}`")
        lines.append("")
    else:
        lines.append("## 可达性")
        lines.append("")
        lines.append("全部状态自初始态可达（基于声明转移的 BFS 结论）。")
        lines.append("")
    return "\n".join(lines) + "\n"
