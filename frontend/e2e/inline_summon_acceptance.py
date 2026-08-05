"""对话轴「按方案开始」验收（真浏览器）：自动路由→整方案开工，决策面零填空。

范式 2a 二刀（owner 2026-07-15 定向「像 Claude Desktop/Codex：去掉一切选择/填空面」，
披露语法=agent-ui-design disclosure-grammar「决策必露且收敛为一」）：方案卡是一份
完整提案的唯一决策是「按方案开始」；成员行只展示系统整理状态，不提供 Agent
选择、参数字段或成员级创建入口。验收面：
  ① 任一成员输入未齐时，整份方案 fail-closed，只在唯一 Composer 自然追问；
  ② 工程师继续输入自然语言后，系统返回全员 ready 的完整方案；
  ③ 全方案 ready 后只有一个「按方案开始」主按钮，点击前任务数仍为 0；
  ④ 点击一次 → batch 原子创建全部 2 名成员，绝不只启动 ready 子集；
  ⑤ 零跳页：URL 仍 /?c=<conv>，督战状态原地亮起；
  ⑥ 会话归档（concluded）后重开：开工按钮整体消失（只读会话不可召集）。

自包含：自起后端（tmp DB）+ stub gateway + 真 chromium，不起 worker。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/inline_summon_acceptance.py

截图落 docs/reviews/inline-summon-shots/。
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = REPO / "docs" / "reviews" / "inline-summon-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_inline_summon_"))

PREFILLED_NAME = "内联召集验收"


class _StubGateway:
    """首轮给一名 ready、一名未 ready；第二轮模拟系统从自然语言补齐整份方案。"""

    def __init__(self) -> None:
        self.ready = False

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        plan = {
            "decision": "orchestrate",
            "analysis": "两名成员接力，第一步参数已可预填。",
            "goal": "验证对话轴内联召集。",
            "workflow": "hello_agent 先运行，fta_agent 需补全参数后运行。",
            "agents": [
                {
                    "agent_id": "hello_agent",
                    "role": "示例问候",
                    "rationale": "输入已从对话整理完成",
                    "prefilled_inputs": {"name": PREFILLED_NAME},
                },
                {
                    "agent_id": "fta_agent",
                    "role": "搭建并分析故障树",
                    "rationale": "等待通过对话补充系统边界与组件",
                    "prefilled_inputs": (
                        {
                            "top_event": "供电完全丧失",
                            "system_description": "双通道发电机经汇流条与转换开关供电",
                            "components": ["发电机A", "发电机B", "汇流条", "转换开关"],
                        }
                        if self.ready
                        else {"top_event": "供电完全丧失"}
                    ),
                    "after": [0],
                },
            ],
        }
        reply = f"两名成员接力协作。\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
        return {"content": reply, "token_usage": None, "model_name": "stub", "finish_reason": "stop"}


_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

app = create_app(
    agents_dir=REPO / "agents",
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=WORK / "flai_os.db",
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

stub = _StubGateway()
app.state.conversation_service.model_gateway = stub

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


from _auth import login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")
API = login_httpx(BASE)


def conv_task_count(conv_id: str) -> int:
    tasks = API.get(f"/api/conversations/{conv_id}/tasks").json()
    return len(tasks if isinstance(tasks, list) else tasks.get("items", []))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)

    # 首轮：一名 ready、一名未 ready。后端不得把半成品方案投影给工程师；
    # 只在同一文字/附件入口自然追问缺失的工程信息。
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("跑一遍示例链验证内联召集")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".ai-body").last).to_contain_text("系统描述", timeout=8000)
    convs = API.get("/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    assert conv_id, "诚实失败：拿不到会话 id"

    incomplete_body = page.locator(".ai-body").last.inner_text()
    incomplete_conv = API.get(f"/api/conversations/{conv_id}").json()
    incomplete_assistants = [
        m for m in incomplete_conv.get("messages", []) if m.get("role") == "assistant"
    ]
    check(
        "①任一成员未 ready：零半成品方案/成员卡/任务，只在唯一 Composer 追问",
        page.locator(".plan-card, .agent-card, .route-summary").count() == 0
        and page.get_by_role("button", name="按方案开始").count() == 0
        and page.get_by_role("button", name="去创建此任务").count() == 0
        and page.locator(".composer textarea").count() == 1
        and page.locator('.composer input[type="file"]').count() == 1
        and "系统描述" in incomplete_body
        and "组件列表" in incomplete_body
        and incomplete_conv.get("recommendation") is None
        and bool(incomplete_assistants)
        and incomplete_assistants[-1].get("recommendation") is None
        and conv_task_count(conv_id) == 0,
        incomplete_body[-360:],
    )
    page.screenshot(path=str(SHOTS / "1_plan_waiting_for_dialogue.png"), full_page=True)

    # ② 工程师仍只输入自然语言；系统自动补全、重新路由出全员 ready 方案。
    stub.ready = True
    page.locator(".composer textarea").fill("补充：系统是双通道发电机，经汇流条和转换开关供电，组件包括发电机A、发电机B、汇流条和转换开关")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_have_count(1, timeout=8000)
    ready_plan = page.locator(".plan-card").last
    ready_disclosure = ready_plan.locator(".route-disclosure")
    open_btn = ready_plan.get_by_role("button", name="按方案开始")
    expect(open_btn).to_be_visible(timeout=8000)
    check("②新方案仍先展示自动路由摘要，细节默认折叠",
          "信息已齐，等待你确认开始" in ready_plan.locator(".route-summary").inner_text()
          and ready_disclosure.get_attribute("open") is None)
    ready_disclosure.locator("summary").click()
    expect(ready_plan.locator(".agent-card").first).to_be_visible(timeout=3000)
    ready_tags = ready_plan.locator(".agent-readytag").all_inner_texts()
    ready_conv = API.get(f"/api/conversations/{conv_id}").json()
    ready_assistants = [
        m for m in ready_conv.get("messages", []) if m.get("role") == "assistant"
    ]
    ready_recommendation = ready_conv.get("recommendation") or {}

    # ③ 全方案 ready 才出现一个主按钮；渲染不等于开工。
    check("③全方案 ready：只有一个『按方案开始』主按钮",
          page.locator(".plan-foot .cta-clay").count() == 1
          and ready_plan.locator(".plan-foot .cta-clay").count() == 1
          and ready_plan.get_by_role("button", name="去创建此任务").count() == 0
          and ready_plan.locator(".agent-card").count() == 2
          and ready_tags == ["输入已自动整理 · 待开始", "输入已自动整理 · 待开始"]
          and len(ready_assistants) == 2
          and ready_assistants[-1].get("recommendation") is not None
          and [a.get("agent_id") for a in ready_recommendation.get("agents", [])]
          == ["hello_agent", "fta_agent"])
    check("③按钮渲染 ≠ 召集：会话任务数仍为 0", conv_task_count(conv_id) == 0)
    page.screenshot(path=str(SHOTS / "2_whole_plan_ready.png"), full_page=True)

    # ④ 一键开工 → 整份方案原子创建，绝不只创建首轮 ready 子集。
    open_btn.click()
    deadline = time.time() + 8
    tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        raw = API.get(f"/api/conversations/{conv_id}/tasks").json()
        tasks = raw if isinstance(raw, list) else raw.get("items", [])
        if len(tasks) == 2:
            break
        time.sleep(0.4)
    by_agent = {t.get("agent_id"): t for t in tasks}
    check("④开工后完整创建 2 名成员且各一项（无 ready 子集部分开工）",
          len(tasks) == 2
          and set(by_agent) == {"hello_agent", "fta_agent"}
          and all(sum(t.get("agent_id") == agent_id for t in tasks) == 1 for agent_id in by_agent),
          json.dumps(tasks, ensure_ascii=False)[:240])
    hello_task = by_agent.get("hello_agent", {})
    fta_task = by_agent.get("fta_agent", {})
    check("④conversation_id 均归本会话",
          bool(tasks) and all(t.get("conversation_id") == conv_id for t in tasks))
    detail = API.get(f"/api/tasks/{hello_task['id']}").json() if hello_task else {}
    fta_detail = API.get(f"/api/tasks/{fta_task['id']}").json() if fta_task else {}
    check(
        "④系统整理的 inputs 与方案一致",
        detail.get("inputs") == {"name": PREFILLED_NAME}
        and fta_detail.get("inputs") == {
            "top_event": "供电完全丧失",
            "system_description": "双通道发电机经汇流条与转换开关供电",
            "components": ["发电机A", "发电机B", "汇流条", "转换开关"],
        },
        json.dumps({"hello": detail.get("inputs"), "fta": fta_detail.get("inputs")}, ensure_ascii=False),
    )
    check(
        "④方案衔接关系由系统写入依赖血缘",
        bool(hello_task)
        and (fta_task.get("depends_on") or []) == [hello_task.get("id")],
        json.dumps(fta_task, ensure_ascii=False)[:240],
    )

    # ⑤ 零跳页 + 督战状态原地亮起；当前完整方案的开工按钮消失。
    check("⑤零跳页：URL 仍在对话轴 /?c=<conv>，无 /tasks/new",
          f"c={conv_id}" in page.url and "/tasks/new" not in page.url, page.url)
    expect(ready_plan.locator(".agent-status").first).to_be_visible(timeout=8000)
    check("⑤2 名成员督战状态原地亮起", ready_plan.locator(".agent-status").count() == 2)
    expect(ready_plan.get_by_role("button", name="按方案开始")).to_have_count(0, timeout=8000)
    check("⑤开工后不再提供重复开工入口",
          ready_plan.get_by_role("button", name="按方案开始").count() == 0)
    page.screenshot(path=str(SHOTS / "3_summoned_live_chip.png"), full_page=True)

    # ⑥ 用一条“全员 ready 但尚未开工”的新会话验证 concluded gate；若复用上方
    # 已有任务的会话，openableCount 本就为 0，会掩盖归档门失效造成假绿。
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("新建一份全员输入已齐、但先不执行的方案")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    expect(page.get_by_role("button", name="按方案开始")).to_be_visible(timeout=8000)
    readonly_conv_id = (
        page.url.split("?c=", 1)[1].split("&", 1)[0]
        if "?c=" in page.url
        else None
    )
    check("⑥归档前对照：全员 ready、尚未开工",
          bool(readonly_conv_id) and conv_task_count(readonly_conv_id) == 0)
    resp = API.post(f"/api/conversations/{readonly_conv_id}/conclude") if readonly_conv_id else None
    check("⑥归档 API 生效", resp is not None and resp.status_code == 200,
          f"status={resp.status_code if resp is not None else 'no-conversation'}")
    page.goto(BASE + f"/?c={readonly_conv_id}", wait_until="networkidle")
    page.wait_for_selector(".plan-card", timeout=8000)
    page.wait_for_timeout(800)  # schema 预取窗口——就绪也不该显示（status 门优先）
    check(
        "⑥concluded 会话不提供『按方案开始』（只读）",
        page.get_by_role("button", name="按方案开始").count() == 0,
    )
    page.screenshot(path=str(SHOTS / "4_concluded_readonly.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'INLINE SUMMON ALL GREEN' if not failed else 'INLINE SUMMON FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
