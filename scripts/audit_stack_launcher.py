"""FLAi-OS 审计体验栈 launcher（dev-only，UI 切片 before/after 截图基线）。

真实后端 create_app + 临时 DB（/tmp/flai-audit-stack/）+ 关键词 stub 网关：
报错/慢/思考/拒绝/超出已审定/计划 + 常规轮按上下文多样回应（轮换四种形态、
回扣用户原话——单模板复述会被误判为产品 bug，2026-08-04 实测教训）。
链路真、内容假，如实标注。seeding 幂等（DB 持久，重启不重建）。

重启：cd /tmp/flai-audit-stack && UV_OFFLINE=1 uv run --no-project --with fastapi \
  --with uvicorn --with jsonschema --with pyyaml --with python-multipart \
  --with "pydantic>2" --with httpx --with jieba --with openpyxl python \
  <repo>/scripts/audit_stack_launcher.py
前端：npm run dev -- --port 5202；账户 tester/Tester#2026、audit/Audit#2026。
"""
from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path
from typing import Any

REPO = Path("/Users/Zhuanz/projects/aircraft-comac/flai-os-product-complete-v1")
sys.path.insert(0, str(REPO))

WORK = Path("/tmp/flai-audit-stack")
WORK.mkdir(parents=True, exist_ok=True)

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from backend.app.core.errors import ModelUpstreamError  # noqa: E402
from backend.app.main import create_app  # noqa: E402

PORT = 8620


def _plan_reply(prompt_text: str) -> str:
    plan: dict[str, Any] = {
        "decision": "orchestrate",
        "analysis": "你要对双通道供电系统做故障树分析。",
        "goal": "对双通道供电系统完成故障树分析，定位供电完全丧失的根因。",
        "workflow": "由故障树分析 Agent 独立完成。",
        "agents": [
            {
                "agent_id": "fta_agent",
                "role": "搭建并分析故障树",
                "rationale": "你的需求是对供电系统做故障树分析，fta_agent 正是做这个的。",
                "prefilled_inputs": {
                    "top_event": "供电完全丧失",
                    "system_description": "双通道供电系统（发电机 A/B、汇流条与转换开关）",
                    "components": ["发电机A", "发电机B", "汇流条", "转换开关"],
                },
            }
        ],
    }
    if '"label": "附件1"' in prompt_text:
        plan["agents"][0]["attachments"] = ["附件1"]
        plan["ignored_attachments"] = []
    return (
        "明白了，你要对双通道供电系统做故障树分析。系统已整理执行输入并自动路由。\n"
        f"<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
    )


_REFUSE_REPLY = (
    "这件事超出了当前平台已审定 Agent 的适用范围，我不能代为串联或猜测流程。\n\n"
    "你可以：\n"
    "- 把问题收敛到已审定的工程领域（如故障树、性能盘、CFD 后处理）；\n"
    "- 或补充材料后重新描述目标，我会在同一会话里继续。"
)


def _topic(last_user: str) -> str:
    t = last_user.strip().replace("\n", " ")
    return t[:24] + ("…" if len(t) > 24 else "")


def _normal_reply(last_user: str, round_no: int) -> str:
    """上下文回应占位回复：按轮次轮换四种形态、回扣用户原话、有时反问——
    杜绝「永远复述同一模板」，保体验栈作为阅读节奏评估基线的可信度。
    链路真、内容假，诚实标注保留。"""
    topic = _topic(last_user)
    kind = (round_no - 1) % 4
    if kind == 1:
        body = (
            f"关于「{topic}」，先对齐一个关键分叉：你手上是否有可直接使用的输入材料？\n\n"
            "有材料的话，上传并说明用途，我会从材料开始理解；"
            "没有的话，我们用一两轮把目标与约束聊清楚再走方案。"
        )
    elif kind == 2:
        body = (
            f"「{topic}」可以拆成三步推进：\n\n"
            "1. 先界定目标与不适用范围；\n"
            "2. 再用已有记录或工具执行补齐证据；\n"
            "3. 最后由你确认结论口径，未验证部分显式标注。\n\n"
            "哪一步是你现在最想先动的？"
        )
    elif kind == 3:
        body = (
            f"收到。我把「{topic}」的当前理解压缩成一句：目标清楚、证据待补、结论待签。\n\n"
            "若这句有偏差，直接纠正；没偏差的话，下一步建议补一份输入材料，"
            "或给我一个可执行的子问题。"
        )
    else:
        body = (
            f"## 对「{topic}」的初步梳理\n\n"
            "- **已明确的**：你的目标与当前讨论上下文；\n"
            "- **待补的**：输入材料、参数来源、验收口径；\n"
            "- **不会做的**：不猜测未建模流程，不替你做工程判断。\n\n"
            "想先看自动路由方案可以说「计划」；想验证失败路径可以说「报错」。"
        )
    return body + "\n\n> 诚实提示：stub 网关占位回复，链路真、内容假。"


class KeywordStubGateway:
    """关键词驱动 stub：报错/慢/思考/拒绝/计划，其余走常规 markdown 流式。"""

    def __init__(self) -> None:
        self.rounds = 0

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        *,
        on_delta=None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.rounds += 1
        last_user = next(
            (
                str(m.get("content") or "")
                for m in reversed(messages)
                if isinstance(m, dict) and m.get("role") == "user"
            ),
            "",
        )
        prompt_text = "\n".join(
            str(m.get("content") or "") for m in messages if isinstance(m, dict)
        )

        if "报错" in last_user:
            raise ModelUpstreamError("stub 注入的上游失败（报错关键词）")

        if "拒绝" in last_user:
            reply = _REFUSE_REPLY
        elif "超出已审定" in last_user:
            # 切片 3 after 截图：guide 级 refuse 裁决（三终点之一）造工作段边界。
            reply = (
                "当前没有形成可开工的协作方案。\n<<PLAN>>\n"
                + json.dumps({
                    "decision": "refuse",
                    "reason": "超出平台已审定能力，如实拒绝。",
                    "residual_problems": ["该需求仍待解决"],
                    "reframe": ["收敛到已审定工程域后重述"],
                }, ensure_ascii=False)
                + "\n<<END>>"
            )
        elif "计划" in last_user:
            reply = _plan_reply(prompt_text)
        else:
            reply = _normal_reply(last_user, self.rounds)

        if "思考" in last_user:
            time.sleep(5.0)  # 首 token 前沉默窗口

        slow = "慢" in last_user
        if callable(on_delta):
            step = 6
            for i in range(0, len(reply), step):
                on_delta(reply[i : i + step])
                time.sleep(0.25 if slow else 0.012)
        return {
            "content": reply,
            "token_usage": None,  # 部分未报，下界——诚实口径
            "model_name": "stub-audit",
            "finish_reason": "stop",
        }

    def embed(self, profile: str, text: str, **kwargs: Any) -> list[float]:
        raise ModelUpstreamError("审计栈不提供 embed（知识问答不在本轮走查范围）")

    def vision(self, profile: str, image_path: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        raise ModelUpstreamError("审计栈不提供 vision（不在本轮走查范围）")


app = create_app(
    agents_dir=REPO / "agents",
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=WORK / "flai.db",
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
)

server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()

for _ in range(80):
    try:
        if httpx.get(f"http://127.0.0.1:{PORT}/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.25)
else:
    sys.exit("诚实失败：后端 20s 内未就绪")

# 健康就绪后 app.state 已装配：注入 stub 网关。
app.state.conversation_service.model_gateway = KeywordStubGateway()

# 真实建账（等价 user_admin.py create），之后一律走 POST /api/auth/login。
from backend.app.auth import service as auth_service  # noqa: E402
from backend.app.storage.db import get_conn  # noqa: E402

conn = get_conn(WORK / "flai.db")
try:
    for uname, disp, pwd in (("tester", "测试工程师", "Tester#2026"), ("audit", "审计观察员", "Audit#2026")):
        try:
            auth_service.create_user(conn, username=uname, display_name=disp, password=pwd)
        except ValueError:
            pass  # 幂等：DB 持久，重启不重建
finally:
    conn.close()

print(f"审计栈就绪：http://127.0.0.1:{PORT}（stub 网关已注入；tester/audit 已建）", flush=True)

# 前台保活
while True:
    time.sleep(3600)
