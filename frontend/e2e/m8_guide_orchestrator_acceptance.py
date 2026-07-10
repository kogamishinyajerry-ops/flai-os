"""M8 P2 导引编排官验收走查（refuse + 多 Agent orchestrate 的真浏览器渲染）。

M6 e2e 已覆盖单 Agent orchestrate 卡片；本脚本补 M8 编排官的两个新分支：
  ① refuse：平台接不住 → 显式拒绝卡片（理由 + 残留问题 + 重述建议），无「去创建
     此任务」按钮（拒绝不产生任何可召集 Agent）；
  ② 多 Agent orchestrate：召集 2 个真实 Agent → 各带分工 role + 各自「去创建此
     任务」按钮，dropped_agents 剔除告警可见。

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


def _start_and_send(page, name: str, text: str) -> None:
    page.goto(BASE + "/", wait_until="networkidle")
    page.get_by_placeholder("你的名字（对话需具名）").fill(name)
    page.locator(".composer textarea").fill(text)
    page.get_by_role("button", name="发送").click()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # ── ① refuse：平台接不住 → 显式拒绝卡片 ──
    stub.plan = {
        "decision": "refuse",
        "reason": "这是一次性的行政统计，不是工程智能体该接的活儿。",
        "residual_problems": ["你仍需人工整理这批表格", "口径不统一没解决"],
        "reframe": ["若拆成『按契约的性能盘批量计算』，performance_disk_agent 可接"],
    }
    _start_and_send(page, "王工", "帮我把这堆杂事整理一下")
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    body = page.locator("body").inner_text()
    refuse_ok = (
        "平台暂时接不住" in body
        and "一次性" in body                     # reason
        and "口径不统一没解决" in body            # residual
        and "performance_disk_agent 可接" in body  # reframe
    )
    check("①refuse 卡片：拒绝理由+残留问题+重述建议", refuse_ok, body[-400:])
    # refuse 无可召集 Agent → 不出现「去创建此任务」按钮
    no_create_btn = page.get_by_role("button", name="去创建此任务").count() == 0
    check("①refuse 不产生任何『去创建此任务』按钮（拒绝零副作用）", no_create_btn,
          f"btn_count={page.get_by_role('button', name='去创建此任务').count()}")
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
    _start_and_send(page, "李工", "做双通道供电的控制逻辑和故障树")
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    page.wait_for_selector(".agent-card", timeout=5000)
    body = page.locator("body").inner_text()
    agent_cards = page.locator(".agent-card").count()
    create_btns = page.get_by_role("button", name="去创建此任务").count()
    multi_ok = (
        "协作方案" in body
        and "2 个 Agent 协作" in body
        and agent_cards == 2          # 幻觉 ghost_agent 被剔除，只剩 2 张真实卡片
        and create_btns == 2          # 每个真实 Agent 一个创建按钮
        and "生成控制逻辑状态机" in body  # role
        and "搭建并分析故障树" in body
        and "ghost_agent" in body      # dropped 剔除告警如实记名
    )
    check("②多 Agent orchestrate：2 张 Agent 卡+各自分工+各自创建按钮+幻觉剔除告警",
          multi_ok, f"cards={agent_cards} btns={create_btns} body={body[-400:]}")
    page.screenshot(path=str(SHOTS / "2_multi_agent.png"), full_page=True)

    # ── ③ 点某个 Agent 的「去创建此任务」→ 落创建页，仅带该 Agent 的预填 ──
    page.get_by_role("button", name="去创建此任务").nth(1).click()  # fta_agent（第二张）
    page.wait_for_url(lambda url: "/tasks/new" in url, timeout=5000)
    expect(page.locator(".prefill-note")).to_be_visible(timeout=5000)
    top_event_val = page.locator('input[placeholder="请填写顶事件"]').first.input_value()
    create_ok = "供电完全丧失" in top_event_val and "提交任务" in page.locator("body").inner_text()
    check("③点 Agent 的创建按钮→落创建页带该 Agent 预填（签发仍由人）", create_ok,
          f"top_event={top_event_val!r}")
    page.screenshot(path=str(SHOTS / "3_create_from_agent.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M8 ORCHESTRATOR P2 ALL GREEN' if not failed else 'M8 ORCHESTRATOR P2 FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
