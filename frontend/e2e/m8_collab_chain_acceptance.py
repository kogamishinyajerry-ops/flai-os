"""M8 P4 协作工作台全链验收：导引召集 → 工作台会话 → 召集 Agent → 任务归会话。

这是 M8 编排官愿景的端到端闭环（真浏览器）：
  ① 导引给出 orchestrate 协作方案（2 个 Agent）；
  ② 「进入协作工作台」→ 落 /workbench/:sessionId，见目标 + 分工架构（蓝图）+
     roster（2 个 Agent，均「尚未召集」）+ 进度 0/2；
  ③ 从蓝图点某 Agent「去创建此任务」→ 落创建页（带预填 + 会话归属）；
  ④ 补全输入、亲手「提交任务」→ 任务创建（人签发），详情页有「← 返回协作会话」；
  ⑤ 回工作台会话 → 该 Agent 变「已召集 · 1 个任务」，进度 1/2，任务归本会话；
  ⑥ 协作工作台首页出现该会话卡片。

自包含：自起后端（tmp）+ stub gateway（本机无内网 key）+ 真 chromium。**不起 worker**
（任务停在 queued 即可证分组，避免 fta 无内网 key 的非确定失败干扰断言）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m8_collab_chain_acceptance.py

截图落 docs/reviews/m8-collab-chain-shots/。
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
SHOTS = REPO / "docs" / "reviews" / "m8-collab-chain-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m8_chain_"))


class _StubGateway:
    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        plan = {
            "decision": "orchestrate",
            "analysis": "这个任务要先做控制逻辑，再做故障树。",
            "goal": "完成双通道供电的控制逻辑与故障树分析。",
            "workflow": "control_logic_agent 先出控制逻辑，fta_agent 再做故障树。",
            "agents": [
                {"agent_id": "control_logic_agent", "role": "生成控制逻辑状态机", "rationale": "结构化生成", "prefilled_inputs": {}},
                {"agent_id": "fta_agent", "role": "搭建并分析故障树", "rationale": "推理辅助", "prefilled_inputs": {"top_event": "供电完全丧失"}},
            ],
        }
        reply = f"这需要两个 Agent 接力协作。\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
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



from _auth import login_context, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ① 导引 → orchestrate 方案
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("做双通道供电的控制逻辑和故障树")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    check("①导引给出 orchestrate 协作方案", "协作方案" in page.locator("body").inner_text())

    # ② 进入协作工作台会话
    page.get_by_role("button", name="进入协作工作台 →").click()
    page.wait_for_url(re.compile(r"/workbench/conv_[0-9a-f]+"), timeout=5000)
    session_url = page.url
    page.wait_for_selector(".member", timeout=5000)
    body = page.locator("body").inner_text()
    sess_ok = (
        "协作会话" in body
        and "完成双通道供电的控制逻辑与故障树分析" in body  # goal
        and "分工架构" in body                              # blueprint
        and page.locator(".member").count() == 2            # roster 2 个 Agent
        and body.count("尚未召集") == 2                     # 都还没召集
        and "0 / 2" in body                                 # 进度
    )
    check("②工作台会话：目标+分工架构+roster(2)+进度0/2", sess_ok,
          f"members={page.locator('.member').count()} body={body[-500:]}")
    page.screenshot(path=str(SHOTS / "1_session_before.png"), full_page=True)

    # ③ 从蓝图召集 fta_agent（第 2 张 member 卡，带 top_event 预填）
    page.locator(".member").nth(1).get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    expect(page.locator(".prefill-note")).to_be_visible(timeout=5000)
    # 结构化表单：预填落在 top_event 字段（非 JSON 文本域）
    top_event_val = page.locator('input[placeholder="请填写顶事件"]').first.input_value()
    check("③召集→落创建页带预填草案", "供电完全丧失" in top_event_val, f"top_event={top_event_val!r}")

    # ④ 结构化表单补全剩余必填（系统描述 + 组件，无需手写 JSON）+ 亲手提交（人签发）
    page.locator('textarea[placeholder="请填写系统描述"]').first.fill("双通道供电系统（发电机A/B + 汇流条 + 转换开关）")
    page.locator('input[placeholder="组件列表 第 1 项"]').first.fill("发电机A")
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=8000)
    expect(page.get_by_role("heading", name="任务详情")).to_be_visible(timeout=5000)
    backlink_ok = page.get_by_role("button", name="← 返回协作会话").count() == 1
    check("④任务创建（人签发）+ 详情页有返回协作会话入口", backlink_ok,
          f"backlink={page.get_by_role('button', name='← 返回协作会话').count()}")
    page.screenshot(path=str(SHOTS / "2_task_created.png"), full_page=True)

    # ⑤ 返回会话 → fta 已召集，进度 1/2
    page.get_by_role("button", name="← 返回协作会话").click()
    page.wait_for_url(re.compile(r"/workbench/conv_"), timeout=5000)
    page.wait_for_selector(".member", timeout=5000)
    body = page.locator("body").inner_text()
    summoned_ok = (
        "已召集 · 1 个任务" in body
        and "尚未召集" in body           # control_logic 仍未召集
        and "1 / 2" in body              # 进度推进
        and page.locator(".task-chip").count() >= 1
    )
    check("⑤回会话：fta 已召集(1 任务)+进度 1/2+任务归本会话", summoned_ok,
          f"chips={page.locator('.task-chip').count()} body={body[-500:]}")
    page.screenshot(path=str(SHOTS / "3_session_after.png"), full_page=True)

    # ⑥ 结束协作 → 归档 + 召集入口消失（结束 = 真的结束；成员任务不受影响）
    assert page.get_by_role("button", name="结束协作").count() == 1, "active 会话应有结束协作入口"
    page.get_by_role("button", name="结束协作").click()
    page.get_by_role("button", name="确定结束").click()  # ElMessageBox 二次确认
    expect(page.locator(".sess-hero")).to_contain_text("已归档", timeout=6000)
    body = page.locator("body").inner_text()
    conclude_ok = (
        "已归档" in body
        and page.get_by_role("button", name="结束协作").count() == 0   # 归档后不再可结束
        and page.get_by_role("button", name="去创建此任务").count() == 0  # 归档后不再召集
        and "会话已归档" in body
        and "已召集 · 1 个任务" in body                                  # 已建任务仍在
    )
    check("⑥结束协作→归档只读（召集入口消失，成员任务不受影响）", conclude_ok,
          f"conclude_btn={page.get_by_role('button', name='结束协作').count()} summon={page.get_by_role('button', name='去创建此任务').count()} body={body[-400:]}")
    page.screenshot(path=str(SHOTS / "4_session_concluded.png"), full_page=True)

    # ⑦（2b 契约重立）：/workbench 旧深链重定向任务台，且左栏「最近对话」
    # 罗列该协作会话（会话列表随双 Surface 收敛进对话侧栏——WorkbenchHome
    # 一级页面已退役）；任务台列表含本链创建的成员任务。
    page.goto(BASE + "/workbench", wait_until="networkidle")
    page.wait_for_url(re.compile(r"/tasks$"), timeout=5000)
    page.wait_for_selector(".cl-item", timeout=5000)
    sidebar = page.locator(".sb-convos").inner_text()
    home_ok = (
        "完成双通道供电的控制逻辑与故障树分析" in sidebar  # 会话在对话侧栏（goal 作标题）
        and page.locator(".cl-item").count() >= 1          # 成员任务在任务台列表
    )
    check("⑦/workbench→任务台重定向 + 会话入对话侧栏 + 成员任务入列", home_ok,
          f"convos={sidebar[:200]} items={page.locator('.cl-item').count()}")
    page.screenshot(path=str(SHOTS / "5_console_home.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M8 COLLAB CHAIN ALL GREEN' if not failed else 'M8 COLLAB CHAIN FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
