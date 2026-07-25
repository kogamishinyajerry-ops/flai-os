"""信任语义与局部状态隔离的无截图浏览器验收。

自起临时后端与真 Chromium；所有数据只写 tempfile，绝不写 docs/reviews。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" python frontend/e2e/trust_ui_acceptance.py
"""
from __future__ import annotations

import json
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行 cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app
from backend.app.storage import repos
from backend.app.storage.db import get_conn


WORK = Path(tempfile.mkdtemp(prefix="flai_trust_ui_acceptance_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")

sock = socket.socket()
sock.bind(("127.0.0.1", 0))
PORT = sock.getsockname()[1]
sock.close()
BASE = f"http://127.0.0.1:{PORT}"
DB_PATH = WORK / "flai_os.db"

app = create_app(
    agents_dir=AGENTS_DIR,
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=DB_PATH,
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)
server = uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
)
threading.Thread(target=server.run, daemon=True).start()

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

from _auth import login_context, seed_user  # noqa: E402

seed_user(DB_PATH, "验收工程师")

TASK_A = f"task_feedback_a_{uuid.uuid4().hex}"
TASK_B = f"task_feedback_b_{uuid.uuid4().hex}"
conn = get_conn(DB_PATH)
try:
    for task_id, name in ((TASK_A, "反馈隔离任务 A"), (TASK_B, "反馈隔离任务 B")):
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name=name,
            created_by="验收工程师",
            created_by_username="e2e_engineer",
        )
    for task_id, message in (
        (TASK_A, "迟到反馈-A"),
        (TASK_B, "即时反馈-B"),
    ):
        repos.create_feedback(
            conn,
            task_id=task_id,
            agent_id="hello_agent",
            agent_version="0.1.0",
            rating="good",
            category="usability",
            message=message,
            created_by="验收工程师",
        )
finally:
    conn.close()

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


GOOD_RUN = {
    "id": "run_all_green",
    "status": "completed",
    "passed": 3,
    "failed": 0,
    "skipped": 0,
    "total": 3,
    "started_at": "2026-07-21T01:00:00Z",
    "finished_at": "2026-07-21T01:01:00Z",
    "case_results": [],
    "draft_cases": [],
}
FAILED_RUN = {
    **GOOD_RUN,
    "id": "run_with_failure",
    "passed": 2,
    "failed": 1,
}


def json_response(route, payload, status: int = 200) -> None:
    route.fulfill(status=status, content_type="application/json", body=json.dumps(payload))


with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    page = browser.new_page(
        viewport={"width": 1280, "height": 900}, color_scheme="light"
    )
    login_context(page.context, BASE)

    # 稳定制造 A 慢 / B 快 / A 后返：A 的真实 GET 先挂起，切换 B
    # 并等 B 列表落地后再放行 A。过期 A 不得覆盖 B，切换同时必须
    # 清空评分/分类/说明三项草稿；B 的主观 good 只用中性 info。
    held_a_feedback = []

    def hold_a_feedback(route) -> None:
        if route.request.method == "GET":
            held_a_feedback.append(route)
        else:
            route.continue_()

    task_a_feedback_pattern = f"**/api/tasks/{TASK_A}/feedback"
    page.route(task_a_feedback_pattern, hold_a_feedback)
    page.goto(BASE + "/feedback", wait_until="networkidle")
    page.locator(".task-select-form .el-select").click()
    page.get_by_role("option", name=re.compile("反馈隔离任务 A")).click()
    for _ in range(50):
        if held_a_feedback:
            break
        page.wait_for_timeout(20)
    if not held_a_feedback:
        raise RuntimeError("反馈 A 列表请求未被挂起")

    page.locator(
        ".feedback-form .el-radio", has_text=re.compile(r"^可用$")
    ).click()
    page.locator(".feedback-form .el-select").click()
    page.get_by_role("option", name="改进建议").click()
    page.locator(".feedback-form textarea").fill("不能串到任务 B")

    page.locator(".task-select-form .el-select").click()
    page.get_by_role("option", name=re.compile("反馈隔离任务 B")).click()
    expect(page.locator(".feedback-list", has_text="即时反馈-B")).to_be_visible(timeout=5000)
    held_a_feedback[0].continue_()
    page.wait_for_timeout(500)

    rating_empty = page.locator('.feedback-form input[type="radio"]:checked').count() == 0
    category_empty = page.locator(".feedback-form .el-select input").input_value() == ""
    message_empty = page.locator(".feedback-form textarea").input_value() == ""
    feedback_text = page.locator(".feedback-list").inner_text()
    check(
        "A 慢/B 快/A 后返仍保持 B，且清空 rating/category/message",
        rating_empty
        and category_empty
        and message_empty
        and "即时反馈-B" in feedback_text
        and "迟到反馈-A" not in feedback_text,
        f"rating={rating_empty} category={category_empty} message={message_empty} feedback={feedback_text!r}",
    )
    page.unroute(task_a_feedback_pattern, hold_a_feedback)
    neutral_good = (
        page.locator(".feedback-list .el-tag--info", has_text="可用").count() == 1
        and page.locator(".feedback-list .el-tag--success").count() == 0
    )
    check("主观 good 使用中性色而非绿色 REAL", neutral_good)

    # 治理接口在浏览器系统边界替身：先给一条全绿历史以启用晋升；本次评测故意
    # 回 failed=1；晋升 POST 成功后再令门户列表刷新 500，见证局部 L1 不回滚。
    route_state = {"fail_agent_refresh": False}

    def agents_route(route) -> None:
        if route_state["fail_agent_refresh"]:
            json_response(route, {"detail": "refresh failed after committed promotion"}, 500)
        else:
            route.continue_()

    def eval_runs_route(route) -> None:
        if route.request.method == "POST":
            json_response(route, {"id": FAILED_RUN["id"], "status": "queued"})
        elif route_state["fail_agent_refresh"]:
            json_response(route, {"detail": "governance refresh failed"}, 500)
        else:
            json_response(route, [GOOD_RUN])

    def promote_route(route) -> None:
        route_state["fail_agent_refresh"] = True
        json_response(route, {"from_maturity": "L0", "to_maturity": "L1"})

    page.route("**/api/agents", agents_route)
    page.route("**/api/agents/hello_agent/eval-runs", eval_runs_route)
    page.route(
        "**/api/agents/hello_agent/eval-runs/run_with_failure",
        lambda route: json_response(route, FAILED_RUN),
    )
    page.route(
        "**/api/agents/hello_agent/promotions",
        lambda route: json_response(route, []),
    )
    page.route(
        "**/api/agents/hello_agent/curated_cases_count",
        lambda route: json_response(route, {"count": 0}),
    )
    page.route("**/api/agents/hello_agent/promote", promote_route)

    page.goto(BASE + "/portal", wait_until="networkidle")
    card = page.locator(".agent-card", has_text="hello_agent")
    card.locator(".gov-entry").click()
    expect(page.locator(".gov-dialog")).to_be_visible(timeout=5000)
    expect(page.locator(".gov-promote-submit")).to_be_enabled(timeout=5000)

    page.locator(".gov-run-btn").click()
    warning = page.locator(
        ".el-message--warning", has_text="存在未通过或跳过"
    )
    expect(warning).to_be_visible(timeout=5000)
    failed_eval_not_green = page.locator(
        ".el-message--success", has_text="评测"
    ).count() == 0
    check("completed 但 failed>0 只提示 warning", failed_eval_not_green)

    page.locator(".gov-promote-confirm").click()
    page.locator(".gov-promote-submit").click()
    expect(page.locator(".gov-maturity-tag", has_text="L1")).to_be_visible(timeout=5000)
    expect(page.locator(".gov-promote-submit")).to_have_count(0)
    expect(
        page.locator(
            ".el-message--warning", has_text="晋升已成功，但治理信息刷新失败"
        )
    ).to_be_visible(timeout=5000)
    expect(page.locator(".error-state")).to_be_visible(timeout=5000)
    check(
        "晋升 POST 成功后即使列表刷新失败仍保持 L1 且隐藏按钮",
        "L1" in page.locator(".gov-maturity-tag").inner_text()
        and page.locator(".gov-promote-submit").count() == 0,
    )

    error_state = page.locator(".error-state")
    check(
        "ErrorState 仅由 el-alert 提供一个 live region",
        error_state.locator('[role="alert"]').count() == 1
        and page.locator('.error-state[role="alert"]').count() == 0,
    )

    browser.close()

server.should_exit = True
failed = [item for item in results if item[1] is not True]
print(
    f"\n{'TRUST UI ACCEPTANCE ALL GREEN' if not failed else 'TRUST UI ACCEPTANCE FAILED'} "
    f"({len(results) - len(failed)}/{len(results)})"
)
sys.exit(0 if not failed else 1)
