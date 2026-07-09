"""fta_agent workflow：推理辅助型样板（M5）——平台首个真实走通
Model Gateway 调用链 + waiting_review 人工放行链的 Agent。

铁律边界（宪法铁律六 + §11.2）：
- LLM 返回的自由文本**原样**存为草案（fta_draft.md），本文件绝不解析它当
  确定性真值、绝不据此下任何工程结论——判定权在人。
- fta_draft.md 文件头强制水印（未经工程师确认不得用于安全性判断）。
- agent.yaml requires_human_review=true：workflow 只管正常返回 success，
  Runtime 会把任务转 waiting_review（不是 completed）等人工放行——这正是
  M5 要验证的链路。
- Gateway 无 key/上游失败时 chat 抛 ModelUpstreamError，本文件**不吞**：
  让其冒泡 → _ModelGatewayContext 记 model_call error 事件 → Runtime 把
  任务置 failed。诚实失败，绝不伪造草案顶替。

system prompt 的唯一版本化来源是包内 prompt.md（宪法铁律七：prompt 是行为
契约，改动必升版本），本文件运行时经 __file__ 定位读取，不内嵌副本。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_DRAFT_MD = "fta_draft.md"

_WATERMARK = (
    "> ⚠ **本故障树为 AI 辅助生成的草案，未经工程师确认，不得用于任何"
    "安全性判断或设计决策**（宪法第五条 / §11.2：LLM 不判最终工程结论，"
    "判定权在确定性代码与人）。"
)


def _fail(message: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": message}


def _load_system_prompt() -> str:
    return Path(__file__).with_name("prompt.md").read_text(encoding="utf-8").strip()


def run(context: dict[str, Any]) -> dict[str, Any]:
    event_logger = context["event_logger"]
    model_gateway = context["model_gateway"]
    inputs = context["inputs"]
    output_dir = context["output_dir"]
    agent_config = context["agent_config"]

    top_event: str = inputs["top_event"]
    system_description: str = inputs["system_description"]
    components: list[str] = inputs["components"]

    profile = agent_config["model"]["profile"]  # =reasoning（以 agent.yaml 声明为准，不硬编码）

    user_message = (
        f"顶事件：{top_event}\n\n"
        f"系统描述：\n{system_description}\n\n"
        f"组件列表：{'、'.join(components)}"
    )
    messages = [
        {"role": "system", "content": _load_system_prompt()},
        {"role": "user", "content": user_message},
    ]

    event_logger.log("fta_reasoning_started", {"top_event": top_event, "profile": profile})

    # ModelUpstreamError 刻意不捕获：冒泡 → model_call error 事件 + 任务 failed。
    result = model_gateway.chat(profile, messages)

    draft = result.get("content")
    if not isinstance(draft, str) or not draft.strip():
        # 上游 2xx 但内容为空/非文本：没有草案可存，诚实失败（绝不写空壳文件）。
        return _fail("模型返回空内容，无草案可存（诚实失败，不伪造草案）")

    draft_path = os.path.join(output_dir, _DRAFT_MD)
    with open(draft_path, "w", encoding="utf-8") as f:
        f.write(_render_draft(top_event, system_description, components, draft))

    event_logger.log("fta_draft_generated", {"file": _DRAFT_MD, "draft_chars": len(draft)})

    summary = {
        "top_event": top_event,
        "draft_chars": len(draft),
        "human_review_required": True,
        "artifacts": [_DRAFT_MD],
    }
    # 返回 success ≠ 任务 completed：requires_human_review=true，Runtime 转 waiting_review。
    return {"status": "success", "outputs": [summary]}


def _render_draft(
    top_event: str,
    system_description: str,
    components: list[str],
    draft: str,
) -> str:
    lines: list[str] = []
    lines.append("# 故障树分析草案（AI 辅助生成）")
    lines.append("")
    lines.append(_WATERMARK)
    lines.append("")
    lines.append("## 分析输入")
    lines.append("")
    lines.append(f"- 顶事件：{top_event}")
    lines.append(f"- 组件：{'、'.join(components)}")
    lines.append(f"- 系统描述：{system_description}")
    lines.append("")
    lines.append("## 模型草案（原样存档，未删改）")
    lines.append("")
    lines.append(draft)
    lines.append("")
    return "\n".join(lines) + "\n"
