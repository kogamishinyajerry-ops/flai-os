"""M2 §12.3 验收走查（可重跑评审证据，反方审查 P1-1/P1-2 的落点）。

自包含：脚本自起后端（tmp 目录注入,绝不碰真实 data/）+ 自跑 Job Runner
+ 真 chromium 走 UI。除 frontend/dist 构建产物外无外部前置。

覆盖：
  §12.3 六条——①前端连 FastAPI ②Agent 列表 ③创建任务 ④任务事件
  ⑤下载输出 ⑥提交反馈；
  附加——任务历史 / SPA 深链刷新 / **waiting_review 人工放行 UI 全链**
  （宪法「人是唯一签发者」的界面落点：tmp 复制 hello_agent 为
  requires_human_review=true 的 review_agent 驱动出该状态）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" python frontend/e2e/m2_acceptance.py
  # 首次需 playwright install chromium

截图落 docs/reviews/m2-acceptance-shots/（每次重跑覆盖,保持证据与代码同步）。
"""
from __future__ import annotations

import re
import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = REPO / "docs" / "reviews" / "m2-acceptance-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

# ── 自起后端：tmp 目录 + hello_agent + review_agent（requires_human_review=true）──
WORK = Path(tempfile.mkdtemp(prefix="flai_m2_acceptance_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")
review_dir = AGENTS_DIR / "review_agent"
shutil.copytree(REPO / "agents" / "hello_agent", review_dir)
_yaml = review_dir / "agent.yaml"
_text = _yaml.read_text(encoding="utf-8")
assert "id: hello_agent" in _text and "requires_human_review: false" in _text
_yaml.write_text(
    _text.replace("id: hello_agent", "id: review_agent")
    .replace("requires_human_review: false", "requires_human_review: true"),
    encoding="utf-8",
)

_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

app = create_app(
    agents_dir=AGENTS_DIR,
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=WORK / "flai_os.db",
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()

import httpx

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

from _auth import login_context, seed_user  # noqa: E402（须在后端就绪后种账户）

seed_user(WORK / "flai_os.db", "验收工程师")

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie，登录门不拦

    # ── ①②门户：连接后端 + Agent 列表（两个 agent 卡片）──
    # M6 起首页 "/" 是智能导引，Agent 门户移至 /portal（ADR-0012 前端路由）。
    page.goto(BASE + "/portal", wait_until="networkidle")
    body = page.locator("body").inner_text()
    check("①前端连接 FastAPI + ②Agent 列表可见",
          "hello_agent" in body and "review_agent" in body and "不适用范围" in body,
          body[:300])
    page.screenshot(path=str(SHOTS / "1_portal.png"), full_page=True)

    # ── ③创建任务（门户按钮→表单→提交,全真实点击链路）──
    page.get_by_role("button", name="创建任务").first.click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    expect(page.locator(".agent-preview")).to_be_visible(timeout=5000)
    # 结构化表单：hello_agent 的 name 字段（不再手写 JSON）；创建人=登录身份，无输入框
    page.locator('input[placeholder="请填写姓名"]').first.fill("M2验收")
    page.screenshot(path=str(SHOTS / "2_create_filled.png"), full_page=True)
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=8000)
    task_id = page.url.rsplit("/", 1)[-1]
    check("③创建 Hello Agent 任务", task_id.startswith("task_"), page.url)

    # ── ④任务事件（worker 驱动到 completed,页面 2s 轮询）──
    deadline = time.time() + 30
    while time.time() < deadline:
        if "已完成" in page.locator("body").inner_text():
            break
        time.sleep(1)
    body = page.locator("body").inner_text()
    events_ok = all(k in body for k in ("task_created", "tool_started", "tool_finished", "task_completed"))
    check("④任务事件时间轴可见且任务完成", "已完成" in body and events_ok, body[:500])
    page.screenshot(path=str(SHOTS / "3_detail_events.png"), full_page=True)

    # ── ⑤下载输出（页面链接→真 HTTP 验内容）──
    href = page.locator("a[href*='/download']").first.get_attribute("href")
    resp = page.request.get(BASE + href)
    check("⑤输出文件可下载", resp.ok is True and "greeting" in resp.text(),
          f"href={href} status={resp.status}")

    # ── ⑥提交反馈（终态详情页——细削后反馈折叠，先展开再填表）──
    page.locator(".feedback-collapse .el-collapse-item__header").click()
    page.wait_for_selector(".feedback-form", state="visible", timeout=3000)
    page.get_by_role("radio", name="可用").first.check()
    page.locator(".feedback-form .el-select").click()
    page.get_by_role("option", name="改进建议").click()
    page.locator(".feedback-form textarea").fill("M2 验收走查：整链路可用")
    page.get_by_role("button", name="提交反馈").click()
    page.wait_for_timeout(1200)
    body = page.locator("body").inner_text()
    check("⑥反馈提交成功且回显", "M2 验收走查：整链路可用" in body, body[-400:])
    page.screenshot(path=str(SHOTS / "4_feedback.png"), full_page=True)

    # ── 附加：历史页 + 深链刷新（静态托管 SPA fallback）──
    page.goto(BASE + "/tasks", wait_until="networkidle")
    hist_ok = "hello_agent" in page.locator("body").inner_text()
    page.screenshot(path=str(SHOTS / "5_history.png"), full_page=True)
    page.goto(BASE + f"/tasks/{task_id}", wait_until="networkidle")
    deep_ok = "任务详情" in page.locator("body").inner_text()
    check("附加:历史页+深链刷新", hist_ok and deep_ok, f"hist={hist_ok} deep={deep_ok}")

    # ── 附加(P1-2)：waiting_review 人工放行 UI 全链 ──
    page.goto(BASE + "/tasks/new?agent_id=review_agent", wait_until="networkidle")
    expect(page.locator(".agent-preview")).to_be_visible(timeout=5000)
    page.locator('input[placeholder="请填写姓名"]').first.fill("待人工审核")
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=8000)
    review_task_id = page.url.rsplit("/", 1)[-1]

    deadline = time.time() + 30
    while time.time() < deadline:
        if "等待人工审核" in page.locator("body").inner_text():
            break
        time.sleep(1)
    review_card_visible = page.locator(".review-card").is_visible()
    check("附加:任务进入 waiting_review 且放行卡片可见", review_card_visible,
          page.locator("body").inner_text()[:400])
    page.screenshot(path=str(SHOTS / "6_waiting_review.png"), full_page=True)

    # 签发人=登录身份（验收工程师），审核卡只余意见框——先断言身份行如实展示
    check("附加:签发人=登录身份展示", "验收工程师" in page.locator(".review-card").inner_text(),
          page.locator(".review-card").inner_text()[:200])
    page.locator(".review-card textarea").fill("结果核对无误，批准")
    page.get_by_role("button", name="批准放行").click()
    page.get_by_role("button", name="确定").click()  # ElMessageBox 二次确认
    page.wait_for_timeout(1500)
    body = page.locator("body").inner_text()
    check("附加:人工批准→completed+review_approved 事件上时间轴",
          "已完成" in body and "review_approved" in body, body[:600])
    page.screenshot(path=str(SHOTS / "7_review_approved.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M2 ACCEPTANCE ALL GREEN' if not failed else 'M2 ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
