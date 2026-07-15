"""对话轴「原地召集」验收（真浏览器）：单入口内联召集，宪法不破。

范式 2a 补刀（owner 2026-07-15 拍板）：多 Agent 方案 + 预填齐 + 无携带附件时，
人可在方案卡上两击（原地召集 → 确认召集）完成召集，零跳页。验收面：
  ① 预填齐 required 的 Agent 显示「原地召集」；**部分预填**的对照 Agent 不显示
     （POST /api/tasks 不做即时校验，就绪门必须在提供入口前咬住——Codex R0-P1）；
  ② 点「原地召集」只进入确认态——**此刻会话任务数=0（导引不代召集铁证）**；
  ③ 点「再想想」退出确认态，任务数仍=0（反悔无副作用）；
  ④ 重新武装 →「确认召集」→ 任务真实创建：agent_id / conversation_id / inputs 与预填一致；
  ⑤ 零跳页：URL 仍 /?c=<conv>，督战 chip（.agent-status）原地亮起；
  ⑥ e2e 锚点不破：「去创建此任务」按钮仍在（m9 back=chat 契约路径原样保留）；
  ⑦ 会话归档（concluded）后重开：内联入口整体消失（只读会话不可召集——Codex R0-P2）。

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
import re
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
    """两名成员：hello_agent 预填齐 required（应有原地召集）；fta_agent 只预填
    top_event（required 还差 system_description/components——就绪门应咬住不提供）。"""

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
                    "rationale": "参数已齐，可原地召集",
                    "prefilled_inputs": {"name": PREFILLED_NAME},
                },
                {
                    "agent_id": "fta_agent",
                    "role": "搭建并分析故障树",
                    "rationale": "参数未齐，走创建页补全",
                    "prefilled_inputs": {"top_event": "供电完全丧失"},
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

app.state.conversation_service.model_gateway = _StubGateway()

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

    # 方案卡起手
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("跑一遍示例链验证内联召集")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    convs = API.get("/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    assert conv_id, "诚实失败：拿不到会话 id"

    # ① 预填齐→有「原地召集」；预填空的对照成员没有
    hello_card = page.locator(".agent-card").nth(0)
    fta_card = page.locator(".agent-card").nth(1)
    check(
        "①预填齐的成员显示「原地召集」",
        hello_card.get_by_role("button", name="原地召集").count() == 1,
    )
    check(
        "①对照：部分预填（top_event 有、其余 required 缺）不显示「原地召集」",
        fta_card.get_by_role("button", name="原地召集").count() == 0,
    )
    page.screenshot(path=str(SHOTS / "1_plan_card_inline_cta.png"), full_page=True)

    # ② 武装只进确认态，不产生任何任务（导引不代召集铁证）
    hello_card.get_by_role("button", name="原地召集").click()
    expect(hello_card.get_by_role("button", name="确认召集")).to_be_visible(timeout=3000)
    check("②武装后出现「确认召集」确认态", True)
    check("②武装 ≠ 召集：会话任务数仍为 0", conv_task_count(conv_id) == 0)
    page.screenshot(path=str(SHOTS / "2_armed_confirm_row.png"), full_page=True)

    # ③ 反悔无副作用
    hello_card.get_by_role("button", name="再想想").click()
    expect(hello_card.get_by_role("button", name="原地召集")).to_be_visible(timeout=3000)
    check("③「再想想」退出确认态，任务数仍为 0", conv_task_count(conv_id) == 0)

    # ④ 确认召集 → 任务真实创建且归因正确
    hello_card.get_by_role("button", name="原地召集").click()
    hello_card.get_by_role("button", name="确认召集").click()
    deadline = time.time() + 8
    tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        raw = API.get(f"/api/conversations/{conv_id}/tasks").json()
        tasks = raw if isinstance(raw, list) else raw.get("items", [])
        if tasks:
            break
        time.sleep(0.4)
    check("④确认召集后任务真实创建（数=1）", len(tasks) == 1)
    t = tasks[0] if tasks else {}
    check("④agent_id 正确", t.get("agent_id") == "hello_agent", json.dumps(t, ensure_ascii=False)[:120])
    check("④conversation_id 归本会话", t.get("conversation_id") == conv_id)
    detail = API.get(f"/api/tasks/{t['id']}").json() if t else {}
    check(
        "④inputs 与预填一致",
        (detail.get("inputs") or {}).get("name") == PREFILLED_NAME,
        json.dumps(detail.get("inputs"), ensure_ascii=False),
    )

    # ⑤ 零跳页 + 督战 chip 原地亮起
    check("⑤零跳页：URL 仍在对话轴 /?c=<conv>", f"c={conv_id}" in page.url, page.url)
    page.wait_for_selector(".agent-status", timeout=8000)
    check("⑤督战 chip 原地亮起", page.locator(".agent-status").count() >= 1)
    page.screenshot(path=str(SHOTS / "3_summoned_live_chip.png"), full_page=True)

    # ⑥ 既有锚点不破：创建页路径仍在（m9 契约原样）
    check(
        "⑥「去创建此任务」按钮原样保留",
        page.get_by_role("button", name="去创建此任务").count() >= 2,
    )

    # ⑦ 归档会话重开 → 只读，不提供内联召集（创建必 409，入口就不该有）
    resp = API.post(f"/api/conversations/{conv_id}/conclude")
    check("⑦归档 API 生效", resp.status_code == 200, f"status={resp.status_code}")
    page.goto(BASE + f"/?c={conv_id}", wait_until="networkidle")
    page.wait_for_selector(".plan-card", timeout=8000)
    page.wait_for_timeout(800)  # schema 预取窗口——就绪也不该显示（status 门优先）
    check(
        "⑦concluded 会话不提供「原地召集」（只读）",
        page.get_by_role("button", name="原地召集").count() == 0,
    )
    page.screenshot(path=str(SHOTS / "4_concluded_readonly.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'INLINE SUMMON ALL GREEN' if not failed else 'INLINE SUMMON FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
