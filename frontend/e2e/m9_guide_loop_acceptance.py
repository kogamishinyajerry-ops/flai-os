"""范式 2a 对话轴闭环验收（真浏览器）：召集任务零跳页 + 状态来找人全链。

把「零跳页」这一范式核心承诺纳入回归网（双镜头 P2：back=chat 回流分支此前
在 5 套 e2e 中执行次数=0，只有代码走读级信心）：
  ① 导引 orchestrate 方案（对话流内方案卡）；
  ② 从对话流点「去创建此任务」→ 创建页 URL 带 back=chat（GuidePage 专属，
     WorkbenchSession 召集不带——m8_collab_chain 断言④的详情页契约不受影响）；
  ③ 补全表单亲手提交 → **回流对话轴 /?c=conv_xxx**（不跳详情页）；
  ④ 回流后 hero 不闪现（restoring 门控）+ 对话流督战条原地亮起（排队中）；
  ⑤ 夹具把任务翻成 completed+产物 → 轮询窗口内「N 件产物」锚点行长出
     （夹具直写 temp DB：只为渲染路径提供 fixture，不冒充业务状态机行为）；
  ⑥ 点锚点 → 状态中心速览打开，产物区可见（加载失败也如实显示非静默）；
  ⑦ 对照组：workbench 路径召集 URL 不带 back=chat（回流不越界）。

自包含：自起后端（tmp DB）+ stub gateway + 真 chromium，不起 worker。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m9_guide_loop_acceptance.py

截图落 docs/reviews/m9-guide-loop-shots/。
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

WORK = Path(tempfile.mkdtemp(prefix="flai_m9_loop_"))


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


def flip_task_completed_with_artifact(task_id: str) -> None:
    """夹具（temp DB 直写）：把 queued 任务翻成 completed+产物——只为前端渲染
    路径提供 fixture（锚点行/速览的响应性），不冒充业务状态机行为（真实完成
    链路由 m2 的 worker 路径验收）。"""
    import sqlite3

    conn = sqlite3.connect(WORK / "flai_os.db")
    conn.execute(
        "UPDATE tasks SET status='completed', output_file_ids=?, started_at=?, finished_at=? WHERE id=?",
        (json.dumps(["file_probe_0001"]), "2026-07-11T02:00:00+00:00", "2026-07-11T02:01:35+00:00", task_id),
    )
    conn.commit()
    conn.close()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    page.add_init_script("localStorage.setItem('flai_user_name', '王工')")  # 身份门：预注入工作身份，WelcomeGate 不拦

    # ① 导引对话 → orchestrate 方案卡
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("做双通道供电的控制逻辑和故障树")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    convs = httpx.get(BASE + "/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    check("①对话流出方案卡+拿到会话id", bool(conv_id))
    page.screenshot(path=str(SHOTS / "1_plan_card.png"), full_page=True)

    # ② 对话流点 fta「去创建此任务」→ URL 带 back=chat
    page.locator(".agent-card").nth(1).get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    check("②GuidePage 召集路径带 back=chat", "back=chat" in page.url)

    # ③ 补全+亲手提交 → 回流对话轴（零跳页，2a 核心承诺）
    page.locator('textarea[placeholder="请填写系统描述"]').first.fill("双通道供电系统（发电机A/B + 汇流条 + 转换开关）")
    page.locator('input[placeholder="组件列表 第 1 项"]').first.fill("发电机A")
    page.get_by_placeholder("你的名字").fill("王工")
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"\?c=conv_[0-9a-f]+"), timeout=8000)
    check("③提交后回流对话轴 /?c=<conv>（零跳页）", f"c={conv_id}" in page.url)

    # ④ 回流后：hero 不闪现（restoring 门控）+ 督战条原地亮起
    check("④回流落地不露空态 hero（restoring 门控）", page.locator(".guide-hero").count() == 0)
    page.wait_for_selector(".agent-status", timeout=8000)
    body = page.locator("body").inner_text()
    check("④督战条原地亮起（排队中）", page.locator(".agent-status").count() >= 1 and "排队中" in body)
    page.screenshot(path=str(SHOTS / "2_returned_live_chip.png"), full_page=True)

    # ⑤ 夹具翻完成+产物 → 轮询窗口内锚点行长出
    tasks = httpx.get(BASE + f"/api/conversations/{conv_id}/tasks").json()
    flip_task_completed_with_artifact(tasks[0]["id"])
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

    # ⑦ 对照组：workbench 召集路径不带 back=chat（回流不越界；
    #    「提交后落详情页」由 m8_collab_chain 断言④实测覆盖，此处不重复）
    page.goto(BASE + f"/workbench/{conv_id}", wait_until="networkidle")
    page.wait_for_selector(".member", timeout=5000)
    page.locator(".member").nth(0).get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    check("⑦workbench 召集路径不带 back=chat（契约不越界）", "back=chat" not in page.url)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M9 GUIDE LOOP ALL GREEN' if not failed else 'M9 GUIDE LOOP FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
