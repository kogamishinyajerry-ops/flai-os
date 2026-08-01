"""M8 P2 导引编排官验收走查（refuse + 多 Agent 自动路由的真浏览器渲染）。

M6 e2e 已覆盖单 Agent orchestrate 卡片；本脚本补 M8 编排官的两个新分支：
  ① refuse：平台接不住 → 显式拒绝卡片（理由 + 残留问题 + 重述建议），不产生
     任何开工入口；
  ② 多 Agent orchestrate：系统自动路由 2 个真实 Agent，摘要常驻、路由依据按需
     披露；任一成员输入未齐时整份方案 fail-closed，只给一个「继续说明缺失信息」
     主按钮，绝不出现成员级创建按钮或 /tasks/new 字段表。

自包含：自起后端（tmp）+ stub gateway（本机无内网 key）+ 真 chromium。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m8_guide_orchestrator_acceptance.py

截图落 docs/reviews/m8-orchestrator-shots/。
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
SHOTS = REPO / "docs" / "reviews" / "m8-orchestrator-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m8_orch_"))


class _SwitchableStub:
    """按 self.plan 返回一份计划块的 stub；测试在每段流程前设置 self.plan。"""

    def __init__(self) -> None:
        self.plan: dict[str, Any] | None = None
        self.lead = "我的判断如下。"

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        reply = self.lead if self.plan is None else (
            f"{self.lead}\n<<PLAN>>\n{json.dumps(self.plan, ensure_ascii=False)}\n<<END>>"
        )
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

stub = _SwitchableStub()
app.state.conversation_service.model_gateway = stub

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def _start_and_send(page, username: str, text: str) -> None:
    # ADR-0019 真鉴权时代：换身份=真实重新登录（context.request 与页面共享
    # cookie jar，新会话 cookie 覆盖旧的）。两次调用分别以王工/李工登录。
    login_context(page.context, BASE, username=username, password=E2E_PASSWORD)
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill(text)
    page.get_by_role("button", name="发送").click()



from _auth import E2E_PASSWORD, login_context, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工", username="wang_gong")
seed_user(WORK / "flai_os.db", "李工", username="li_gong")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移

    # ── ① refuse：平台接不住 → 显式拒绝卡片 ──
    stub.plan = {
        "decision": "refuse",
        "reason": "这是一次性的行政统计，不是工程智能体该接的活儿。",
        "residual_problems": ["你仍需人工整理这批表格", "口径不统一没解决"],
        "reframe": ["若拆成『按契约的性能盘批量计算』，performance_disk_agent 可接"],
    }
    _start_and_send(page, "wang_gong", "帮我把这堆杂事整理一下")
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    body = page.locator("body").inner_text()
    refuse_ok = (
        "平台暂时接不住" in body
        and "一次性" in body                     # reason
        and "口径不统一没解决" in body            # residual
        and "performance_disk_agent 可接" in body  # reframe
    )
    check("①refuse 卡片：拒绝理由+残留问题+重述建议", refuse_ok, body[-400:])
    # refuse 无可执行方案 → 不产生开工 CTA，也不回退到成员级创建表单。
    no_start = (
        page.locator(".open-plan-btn").count() == 0
        and page.get_by_role("button", name="去创建此任务").count() == 0
    )
    refuse_conv_id = (
        page.url.split("?c=", 1)[1].split("&", 1)[0]
        if "?c=" in page.url
        else None
    )
    refuse_tasks = (
        page.context.request.get(f"{BASE}/api/conversations/{refuse_conv_id}/tasks").json()
        if refuse_conv_id
        else []
    )
    check("①refuse 不产生开工入口、成员级创建按钮或后台任务（拒绝零副作用）",
          no_start and bool(refuse_conv_id) and len(refuse_tasks) == 0,
          f"conversation={refuse_conv_id} tasks={len(refuse_tasks)}")
    page.screenshot(path=str(SHOTS / "1_refuse.png"), full_page=True)

    # ── ② 多 Agent orchestrate：召集 2 个真实 Agent + 1 个幻觉（被剔除）──
    stub.plan = {
        "decision": "orchestrate",
        "analysis": "这个任务要先做控制逻辑，再做故障树。",
        "goal": "完成双通道供电的控制逻辑与故障树分析。",
        "workflow": "control_logic_agent 先出控制逻辑，fta_agent 再做故障树。",
        "agents": [
            {"agent_id": "control_logic_agent", "role": "生成控制逻辑状态机", "rationale": "结构化生成", "prefilled_inputs": {}},
            {"agent_id": "fta_agent", "role": "搭建并分析故障树", "rationale": "推理辅助", "prefilled_inputs": {"top_event": "供电完全丧失"}},
            {"agent_id": "ghost_agent", "role": "x", "rationale": "x", "prefilled_inputs": {}},
        ],
    }
    _start_and_send(page, "li_gong", "做双通道供电的控制逻辑和故障树")
    plan_card = page.locator(".plan-card")
    expect(plan_card).to_be_visible(timeout=8000)
    expect(plan_card.locator(".route-summary")).to_be_visible(timeout=5000)
    disclosure = plan_card.locator(".route-disclosure")
    collapsed_ok = (
        disclosure.get_attribute("open") is None
        and plan_card.locator(".agent-card").count() == 2
        and plan_card.locator(".agent-card").first.is_visible() is False
        and "已自动编排 · 2 个执行单元" in plan_card.locator(".route-summary").inner_text()
        and "还需通过对话补充执行信息" in plan_card.locator(".route-summary").inner_text()
    )
    check("②多 Agent 自动路由：摘要常驻、2 个执行单元的细节默认折叠", collapsed_ok)
    disclosure.locator("summary").click()
    expect(plan_card.locator(".agent-card").first).to_be_visible(timeout=3000)
    body = page.locator("body").inner_text()
    agent_cards = plan_card.locator(".agent-card").count()
    create_btns = plan_card.get_by_role("button", name="去创建此任务").count()
    multi_ok = (
        "协作方案" in body
        and "执行单元 · 2" in body  # 计数唯一承载点（披露 summary 不再重复人数）
        and agent_cards == 2          # 幻觉 ghost_agent 被剔除，只剩 2 张真实卡片
        and create_btns == 0          # 成员行不提供手工创建/填参数入口
        and "生成控制逻辑状态机" in body  # role
        and "搭建并分析故障树" in body
        and "ghost_agent" in body      # dropped 剔除告警如实记名
        and plan_card.locator("input, textarea, select").count() == 0
    )
    check("②按需披露：2 个路由结果+分工+幻觉剔除告警，零成员级按钮/字段表",
          multi_ok, f"cards={agent_cards} btns={create_btns} body={body[-400:]}")
    page.screenshot(path=str(SHOTS / "2_multi_agent.png"), full_page=True)

    # ── ③ 任一成员未 ready，整份方案不开工；唯一主动作回到同一个文字输入，
    # 不允许只启动 ready 子集，也不把工程师送去 /tasks/new 补字段。──
    continue_btn = plan_card.get_by_role("button", name="继续说明缺失信息")
    expect(continue_btn).to_be_visible(timeout=3000)
    check("③全方案 fail-closed：只有一个『继续说明缺失信息』主按钮",
          plan_card.locator(".plan-foot .cta-clay").count() == 1
          and plan_card.get_by_role("button", name="按方案开工").count() == 0)
    continue_btn.click()
    expect(page.locator(".composer textarea")).to_be_focused(timeout=3000)
    focus_ok = page.evaluate(
        "() => document.activeElement === document.querySelector('.composer textarea')"
    )
    check("③缺失信息通过对话继续补充：聚焦唯一 Composer，零 /tasks/new 跳转",
          focus_ok and "/tasks/new" not in page.url, page.url)
    page.screenshot(path=str(SHOTS / "3_continue_in_composer.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M8 ORCHESTRATOR P2 ALL GREEN' if not failed else 'M8 ORCHESTRATOR P2 FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
