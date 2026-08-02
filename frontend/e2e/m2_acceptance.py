"""M2 §12.3 验收走查（可重跑评审证据，反方审查 P1-1/P1-2 的落点）。

自包含：脚本自起后端（tmp 目录注入,绝不碰真实 data/）+ 自跑 Job Runner
+ 真 chromium 走 UI。除 frontend/dist 构建产物外无外部前置。

覆盖：
  §12.3 六条——①前端连 FastAPI ②Agent 能力目录 ③主对话单输入边界 ④任务事件
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
    from playwright.sync_api import sync_playwright
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

from _auth import login_context, login_httpx, seed_user  # noqa: E402（须在后端就绪后种账户）

seed_user(WORK / "flai_os.db", "验收工程师")
API = login_httpx(BASE)

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

    # ── ①②门户：连接后端 + Agent 能力目录（两个只读卡片）──
    # M6 起首页 "/" 是智能导引，Agent 门户移至 /portal（ADR-0012 前端路由）。
    page.goto(BASE + "/portal", wait_until="networkidle")
    body = page.locator("body").inner_text()
    check("①前端连接 FastAPI + ②Agent 列表可见",
          "hello_agent" in body and "review_agent" in body and "不适用范围" in body,
          body[:300])
    no_launch_controls = (
        page.get_by_role("button", name="创建任务").count() == 0
        and page.get_by_role("button", name="开始对话").count() == 0
        and page.get_by_role("button", name="召集此团队").count() == 0
        and page.locator(".gov-entry").count() == 2
    )
    check("②'Agent 门户只读：保留治理，零手工启动/团队填参入口", no_launch_controls,
          f"gov={page.locator('.gov-entry').count()}")
    page.screenshot(path=str(SHOTS / "1_portal.png"), full_page=True)

    # ── ③历史创建深链必须回主对话；工程师面只剩文字与附件。后续任务详情
    #    链的前置数据由已认证 API 创建，不把测试夹具冒充工程师交互。──
    page.goto(BASE + "/tasks/new?agent_id=hello_agent", wait_until="networkidle")
    redirected_to_conversation = (
        page.url.rstrip("/") == BASE
        and page.locator(".composer textarea").count() == 1
        and page.locator('input[type="file"]').count() == 1
        and page.locator(".agent-preview").count() == 0
    )
    check("③/tasks/new 旧深链回主对话，原始输入只有文字与附件", redirected_to_conversation, page.url)
    page.screenshot(path=str(SHOTS / "2_conversation_only.png"), full_page=True)

    created = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "M2验收"}})
    created_body = created.json() if created.status_code in (200, 201) else {}
    task_id = created_body.get("id", "")
    created_ok = (
        created.status_code in (200, 201)
        and re.fullmatch(r"task_[0-9a-f]{32}", task_id) is not None
    )
    check("③任务详情前置数据由认证 API 创建", created_ok,
          f"status={created.status_code} body={created.text[:200]}")
    if created_ok is not True:
        raise RuntimeError(f"M2 前置任务创建失败 {created.status_code}: {created.text[:200]}")
    page.goto(BASE + f"/tasks/{task_id}", wait_until="networkidle")

    # ── ④任务事件（worker 驱动到 completed,页面 2s 轮询）──
    deadline = time.time() + 30
    while time.time() < deadline:
        if "已完成" in page.locator("body").inner_text():
            break
        time.sleep(1)
    # 批次四 Q5：原始事件 token 移入 WorkLog 展开态（折叠态=人话扫读面）——
    # 断言改走展开路径取 token（幂等守卫：已展开则不再点）。
    if page.locator(".worklog-timeline").count() == 0:
        page.locator(".worklog-head").first.click()
        page.wait_for_selector(".worklog-timeline", timeout=3000)
    body = page.locator("body").inner_text()
    events_ok = all(k in body for k in ("task_created", "tool_started", "tool_finished", "task_completed"))
    check("④任务事件时间轴（展开态）可见且任务完成", "已完成" in body and events_ok, body[:500])
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
    review_created = API.post(
        "/api/tasks",
        json={"agent_id": "review_agent", "inputs": {"name": "待人工审核"}},
    )
    review_body = review_created.json() if review_created.status_code in (200, 201) else {}
    review_task_id = review_body.get("id", "")
    review_created_ok = (
        review_created.status_code in (200, 201)
        and re.fullmatch(r"task_[0-9a-f]{32}", review_task_id) is not None
    )
    check("附加:认证 API 创建待签任务成功", review_created_ok,
          f"status={review_created.status_code} body={review_created.text[:200]}")
    if review_created_ok is not True:
        raise RuntimeError(
            f"M2 待签前置任务创建失败 {review_created.status_code}: {review_created.text[:200]}"
        )
    page.goto(BASE + f"/tasks/{review_task_id}", wait_until="networkidle")

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
    # 批次四 Q5：review_approved 原始 token 在展开态时间轴——同款展开守卫。
    if page.locator(".worklog-timeline").count() == 0:
        page.locator(".worklog-head").first.click()
        page.wait_for_selector(".worklog-timeline", timeout=3000)
    body = page.locator("body").inner_text()
    check("附加:人工批准→completed+review_approved 事件上时间轴（展开态）",
          "已完成" in body and "review_approved" in body, body[:600])
    page.screenshot(path=str(SHOTS / "7_review_approved.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M2 ACCEPTANCE ALL GREEN' if not failed else 'M2 ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
