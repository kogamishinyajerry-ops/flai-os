"""对话轴「照此方案开工」验收（真浏览器）：提案→一键开工，决策面零填空。

范式 2a 二刀（owner 2026-07-15 定向「像 Claude Desktop/Codex：去掉一切选择/填空面」，
披露语法=agent-ui-design disclosure-grammar「决策必露且收敛为一」）：方案卡是一份
完整提案，唯一决策=「照此方案开工」一键；成员行零交互（就绪=展示徽 / 未就绪=创建页
escape / 已召集=督战 chip）。验收面：
  ① 就绪成员（预填齐 required + params 型）零按钮、示「参数已齐 · 待开工」徽；
     部分预填的对照成员保留「去创建此任务」escape（就绪门 Codex R0-R2 全承袭）；
  ② 方案脚部出现「照此方案开工 · 召集 1 名就绪成员」主按钮；点击前会话任务数=0
     （导引不代召集铁证：按钮渲染 ≠ 召集）；
  ③ 点「照此方案开工」→ 只创建就绪成员的任务（数=1）：agent_id / conversation_id /
     inputs 与预填一致；未就绪成员绝不被带上（fail-closed 不越权）；
  ④ 零跳页：URL 仍 /?c=<conv>，督战 chip 原地亮起；开工按钮随「就绪待开工=0」消失；
  ⑤ e2e 锚点不破：未就绪成员的「去创建此任务」仍在（m9 back=chat 契约路径原样保留）；
  ⑥ 会话归档（concluded）后重开：开工按钮整体消失（只读会话不可召集）。
  ⑦ conversation task ledger 首载失败时 fail-closed：不把未知当“尚未召集”，
     批量与单项创建入口均隐藏；真实账恢复后才开放。

自包含：自起后端（tmp DB）+ stub gateway + 真 chromium，不起 worker。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/inline_summon_acceptance.py

截图默认落临时 artifact；仅 UPDATE_GOLDENS=1 更新 docs/reviews/inline-summon-shots/。
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

from _artifacts import resolve_shots_dir
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = resolve_shots_dir(REPO, "inline-summon-shots")

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

    def _abort_task_ledger(route) -> None:
        path = route.request.url.split("?", 1)[0]
        if route.request.method == "GET" and "/api/conversations/" in path and path.endswith("/tasks"):
            route.abort()
        else:
            route.continue_()

    # 在方案出现前先掐断会话任务账，证明 cold unknown 不会被解释成“零任务”。
    page.route("**/api/conversations/*/tasks*", _abort_task_ledger)
    page.locator(".composer textarea").fill("跑一遍示例链验证内联召集")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    convs = API.get("/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    assert conv_id, "诚实失败：拿不到会话 id"

    expect(page.locator(".connection-truth", has_text="当前无法同步")).to_be_visible(timeout=8000)
    check(
        "⑦任务账 cold failure 时显示尚未核对，批量与单项创建均 fail-closed",
        page.get_by_text("任务账尚未核对", exact=True).count() >= 1
        and page.locator(".open-plan-btn").count() == 0
        and page.get_by_role("button", name="去创建此任务").count() == 0,
    )
    page.unroute("**/api/conversations/*/tasks*", _abort_task_ledger)
    page.locator(".connection-retry").click()
    expect(page.locator(".connection-truth")).to_have_count(0, timeout=8000)

    # 首次账已成功（真实零任务）后再次断连：旧的“零”只能只读展示，不能继续
    # 授权依赖负结论的创建动作，因为断连期间另一会话可能已经召集。
    page.route("**/api/conversations/*/tasks*", _abort_task_ledger)
    expect(page.locator(".connection-truth", has_text="当前显示上次成功快照")).to_be_visible(
        timeout=8000
    )
    check(
        "⑦任务账 warm stale 时旧零值只读，批量与单项创建继续 fail-closed",
        page.get_by_text("任务账尚未核对", exact=True).count() >= 1
        and page.locator(".open-plan-btn").count() == 0
        and page.get_by_role("button", name="去创建此任务").count() == 0,
    )
    page.unroute("**/api/conversations/*/tasks*", _abort_task_ledger)
    page.locator(".connection-retry").click()
    expect(page.locator(".connection-truth")).to_have_count(0, timeout=8000)

    # ① 就绪成员=展示徽零按钮；未就绪对照保留创建页 escape。
    #    先 expect 等待（schema 预取是异步的，count() 不等待）。
    hello_card = page.locator(".agent-card").nth(0)
    fta_card = page.locator(".agent-card").nth(1)
    expect(hello_card.locator(".agent-readytag")).to_be_visible(timeout=8000)
    check(
        "①就绪成员示「参数已齐 · 待开工」徽且零按钮",
        "参数已齐" in hello_card.locator(".agent-readytag").inner_text()
        and hello_card.get_by_role("button", name="去创建此任务").count() == 0,
    )
    check(
        "①对照：部分预填（top_event 有、其余 required 缺）保留「去创建此任务」",
        fta_card.get_by_role("button", name="去创建此任务").count() == 1,
    )
    page.screenshot(path=str(SHOTS / "1_plan_card_open_cta.png"), full_page=True)

    # ② 开工主按钮在场且如实计数；渲染 ≠ 召集（任务数=0）
    open_btn = page.locator(".open-plan-btn")
    expect(open_btn).to_be_visible(timeout=3000)
    check("②「照此方案开工」计数=1 名就绪成员", "1 名就绪成员" in open_btn.inner_text())
    check("②按钮渲染 ≠ 召集：会话任务数仍为 0", conv_task_count(conv_id) == 0)
    page.screenshot(path=str(SHOTS / "2_open_plan_cta.png"), full_page=True)

    # ③ 一键开工 → 只创建就绪成员的任务
    open_btn.click()
    deadline = time.time() + 8
    tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        raw = API.get(f"/api/conversations/{conv_id}/tasks").json()
        tasks = raw if isinstance(raw, list) else raw.get("items", [])
        if tasks:
            break
        time.sleep(0.4)
    check("③开工后只创建就绪成员的任务（数=1，未就绪绝不带上）", len(tasks) == 1)
    t = tasks[0] if tasks else {}
    check("③agent_id 正确", t.get("agent_id") == "hello_agent", json.dumps(t, ensure_ascii=False)[:120])
    check("③conversation_id 归本会话", t.get("conversation_id") == conv_id)
    detail = API.get(f"/api/tasks/{t['id']}").json() if t else {}
    check(
        "③inputs 与预填一致",
        (detail.get("inputs") or {}).get("name") == PREFILLED_NAME,
        json.dumps(detail.get("inputs"), ensure_ascii=False),
    )

    # ④ 零跳页 + 督战 chip 原地亮起 + 开工按钮随就绪清零消失
    check("④零跳页：URL 仍在对话轴 /?c=<conv>", f"c={conv_id}" in page.url, page.url)
    page.wait_for_selector(".agent-status", timeout=8000)
    check("④督战 chip 原地亮起", page.locator(".agent-status").count() >= 1)
    expect(page.locator(".open-plan-btn")).to_have_count(0, timeout=8000)
    check("④就绪待开工=0 后开工按钮消失", page.locator(".open-plan-btn").count() == 0)
    page.screenshot(path=str(SHOTS / "3_summoned_live_chip.png"), full_page=True)

    # ⑤ 既有锚点不破：未就绪成员的创建页路径仍在（m9 契约原样）
    check(
        "⑤未就绪成员「去创建此任务」按钮原样保留",
        fta_card.get_by_role("button", name="去创建此任务").count() == 1,
    )

    # ⑥ 归档会话重开 → 只读，开工按钮整体消失（创建必 409，入口就不该有）
    resp = API.post(f"/api/conversations/{conv_id}/conclude")
    check("⑥归档 API 生效", resp.status_code == 200, f"status={resp.status_code}")
    page.goto(BASE + f"/?c={conv_id}", wait_until="networkidle")
    page.wait_for_selector(".plan-card", timeout=8000)
    page.wait_for_timeout(800)  # schema 预取窗口——就绪也不该显示（status 门优先）
    check(
        "⑥concluded 会话不提供「照此方案开工」（只读）",
        page.locator(".open-plan-btn").count() == 0,
    )
    page.screenshot(path=str(SHOTS / "4_concluded_readonly.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'INLINE SUMMON ALL GREEN' if not failed else 'INLINE SUMMON FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
