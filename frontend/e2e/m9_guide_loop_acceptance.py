"""范式 2a 对话轴闭环验收（真浏览器）：自动路由→整方案开工→状态来找人。

把「工程师零填表、执行零跳页」纳入回归网：
  ① 导引把自然语言自动路由成完整的两 Agent 方案，细节默认折叠；
  ② 全方案 ready 后只出现一个「按方案开始」主按钮，点击前任务数仍为 0；
  ③ 人确认一次后，系统通过 batch 全有全无地原地创建两项任务，并保留依赖；
  ④ URL 始终为 /?c=conv_xxx，督战状态在原对话轴亮起，无 /tasks/new 字段墙；
  ⑤ 夹具把首项任务翻成 completed+产物 → 轮询窗口内「N 件产物」锚点行长出
     （夹具直写 temp DB：只为渲染路径提供 fixture，不冒充业务状态机行为）；
  ⑥ 点锚点 → 状态中心速览打开，产物区可见（加载失败也如实显示非静默）。

自包含：自起后端（tmp DB）+ stub gateway + 真 chromium，不起 worker。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m9_guide_loop_acceptance.py

截图落 docs/reviews/m9-guide-loop-shots/。
"""
from __future__ import annotations

import hashlib
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
SHOTS = REPO / "docs" / "reviews" / "m9-guide-loop-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app
from backend.app.storage import repos
from backend.app.storage.db import get_conn

WORK = Path(tempfile.mkdtemp(prefix="flai_m9_loop_"))


class _StubGateway:
    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        plan = {
            "decision": "orchestrate",
            "analysis": "这个任务要先做控制逻辑，再做故障树。",
            "goal": "完成双通道供电的控制逻辑与故障树分析。",
            "workflow": "control_logic_agent 先出控制逻辑，fta_agent 再做故障树。",
            "agents": [
                {
                    "agent_id": "control_logic_agent",
                    "role": "生成控制逻辑状态机",
                    "rationale": "结构化生成",
                    "prefilled_inputs": {
                        "system_name": "双通道供电控制系统",
                        "states": ["双路供电", "单路供电", "供电丧失"],
                        "transitions": [
                            {"from": "双路供电", "to": "单路供电", "condition": "任一发电机失效"},
                            {"from": "单路供电", "to": "供电丧失", "condition": "剩余发电机失效"},
                        ],
                    },
                },
                {
                    "agent_id": "fta_agent",
                    "role": "搭建并分析故障树",
                    "rationale": "推理辅助",
                    "prefilled_inputs": {
                        "top_event": "供电完全丧失",
                        "system_description": "双通道发电机经汇流条与转换开关供电",
                        "components": ["发电机A", "发电机B", "汇流条", "转换开关"],
                    },
                    "after": [0],
                },
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
    except httpx.HTTPError:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

app.state.conversation_service.model_gateway = _StubGateway()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def flip_task_completed_with_artifact(task_id: str) -> None:
    """夹具（temp DB 直写）：把 queued 任务翻成 completed+产物——只为前端渲染
    路径提供 fixture（锚点行/速览的响应性），不冒充业务状态机行为（真实完成
    链路由 m2 的 worker 路径验收）。产物记录与 task.output_file_ids 必须双向一致；
    否则 owner-scoped 读取会按产品契约 fail-closed，而不是给 UI 假产物。"""
    file_id = "file_probe_0001"
    artifact_bytes = b'{"status":"fixture-only"}\n'
    artifact_path = WORK / "task_runs" / task_id / "artifact.json"
    artifact_path.parent.mkdir(parents=True, exist_ok=True)
    artifact_path.write_bytes(artifact_bytes)

    conn = get_conn(WORK / "flai_os.db")
    try:
        repos.create_file(
            conn,
            file_id=file_id,
            task_id=task_id,
            kind="output",
            filename="artifact.json",
            path=str(artifact_path),
            size_bytes=len(artifact_bytes),
            sha256=hashlib.sha256(artifact_bytes).hexdigest(),
            classification="internal",
        )
        updated = conn.execute(
            "UPDATE tasks SET status='completed', output_file_ids=?, started_at=?, finished_at=? WHERE id=?",
            (json.dumps([file_id]), "2026-07-11T02:00:00+00:00", "2026-07-11T02:01:35+00:00", task_id),
        ).rowcount
        if updated != 1:
            raise RuntimeError("M9 fixture task 不存在，不能伪造完成态")
        conn.commit()
    finally:
        conn.close()



from _auth import login_context, login_httpx, seed_user

seed_user(WORK / "flai_os.db", "王工")
API = login_httpx(BASE)  # 直连 API 的已登录客户端（ADR-0019）

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ① 导引对话 → 自动路由方案卡；详情默认折叠，壳层不出现 picker/字段表。
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("做双通道供电的控制逻辑和故障树")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    convs = API.get("/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    plan_card = page.locator(".plan-card")
    disclosure = plan_card.locator(".route-disclosure")
    check("①对话流出方案卡+拿到会话 id", bool(conv_id))
    check("①自动路由摘要常驻、2 位成员细节默认折叠",
          "已自动安排 · 2 位成员" in plan_card.locator(".route-summary").inner_text()
          and disclosure.get_attribute("open") is None
          and plan_card.locator(".agent-card").first.is_visible() is False)
    check("①壳层零手工编排/字段表",
          page.get_by_role("button", name="浏览可用 Agent").count() == 0
          and page.get_by_role("button", name="去创建此任务").count() == 0
          and plan_card.locator("input, textarea, select").count() == 0)
    disclosure.locator("summary").click()
    expect(plan_card.locator(".agent-card").first).to_be_visible(timeout=3000)
    page.screenshot(path=str(SHOTS / "1_plan_card.png"), full_page=True)

    # ② 全方案 ready 才只给一个主按钮；渲染不等于开工。
    open_btn = plan_card.get_by_role("button", name="按方案开始")
    expect(open_btn).to_be_visible(timeout=8000)
    before_tasks = API.get(f"/api/conversations/{conv_id}/tasks").json()
    check("②全方案 ready：只有一个『按方案开始』主按钮",
          plan_card.locator(".plan-foot .cta-clay").count() == 1)
    check("②按钮渲染不等于开工：点击前任务数=0", len(before_tasks) == 0)

    # ③ 一次确认 → batch 原子创建整份方案，不允许部分 ready 子集开工。
    open_btn.click()
    deadline = time.time() + 8
    tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        raw = API.get(f"/api/conversations/{conv_id}/tasks").json()
        tasks = raw if isinstance(raw, list) else raw.get("items", [])
        if len(tasks) == 2:
            break
        time.sleep(0.3)
    by_agent = {t.get("agent_id"): t for t in tasks}
    fta_detail = API.get(f"/api/tasks/{by_agent['fta_agent']['id']}").json() if "fta_agent" in by_agent else {}
    check("③一次确认原子创建完整 2-Agent 方案（恰好各一项）",
          len(tasks) == 2
          and set(by_agent) == {"control_logic_agent", "fta_agent"}
          and all(sum(t.get("agent_id") == agent_id for t in tasks) == 1 for agent_id in by_agent))
    check("③方案依赖保留：FTA 等待控制逻辑任务",
          fta_detail.get("depends_on") == [by_agent.get("control_logic_agent", {}).get("id")],
          json.dumps(fta_detail, ensure_ascii=False)[:240])

    # ④ 任务状态原地来找人：URL 不跳、hero 不闪、督战条亮起。
    check("④开工后仍在对话轴 /?c=<conv>，零 /tasks/new", f"c={conv_id}" in page.url and "/tasks/new" not in page.url, page.url)
    check("④执行中不露空态 hero", page.locator(".guide-hero").count() == 0)
    page.wait_for_selector(".agent-status", timeout=8000)
    body = page.locator("body").inner_text()
    check("④两名成员督战状态原地亮起", page.locator(".agent-status").count() == 2 and "排队中" in body)
    page.screenshot(path=str(SHOTS / "2_returned_live_chip.png"), full_page=True)

    # ⑤ 夹具翻完成+产物 → 轮询窗口内锚点行长出
    flip_task_completed_with_artifact(by_agent["control_logic_agent"]["id"])
    page.wait_for_selector(".status-artifact", timeout=12000)
    check("⑤产物锚点行长出（1 件产物）", "1 件产物" in page.locator(".status-artifact").inner_text())
    page.screenshot(path=str(SHOTS / "3_artifact_anchor.png"), full_page=True)

    # ⑥ 点锚点 → 速览面板打开，产物区如实可见
    page.locator(".status-artifact").click()
    page.wait_for_selector(".sc-shell", timeout=5000)
    check("⑥锚点直开速览面板", page.locator(".sc-back").count() == 1)
    check("⑥速览产物区可见（失败也如实显示非静默）", "产物" in page.locator(".sc-body").inner_text())
    page.screenshot(path=str(SHOTS / "4_peek_from_anchor.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M9 GUIDE LOOP ALL GREEN' if not failed else 'M9 GUIDE LOOP FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
