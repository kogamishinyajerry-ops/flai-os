"""批A「活的工作台」liveFeed 换轨验收（Task 4 先建骨架仅断言②；Task 7 补全①，
③留待其收口任务）。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/）+ Job Runner + 真 chromium。
除 frontend/dist 构建产物外无外部前置。

覆盖：
  ①全站任务清单单链：TaskConsole（/tasks）与状态中心抽屉（inbox）同屏开启，
    二者共享同一个 liveFeed 'tasks' channel（引用计数，非各自轮询）。30s 窗口
    内统计 `/api/tasks`（清单接口，路径精确匹配，天然排除 `/api/tasks/<id>`
    详情接口）请求次数，断言 ≤8（单链 5s 语义：首拉+6 tick+余量；旧双链
    TaskConsole/StatusCenter 各自轮询会 ≥12，此断言在旧实现上必然超限失败）。
  ②TaskDetail 跨会话人工放行免手动刷新：本机浏览器开着 waiting_review 任务
    的详情页（channel 已按 liveFeedCore.nextInterval 降频到 8s）；另一个
    httpx 会话（模拟另一位工程师，不共享浏览器 cookie）直接 POST
    /api/tasks/<id>/review 批准放行；页面全程不点任何按钮（不点「刷新」，
    不点批准），12 秒内应自行出现终态盖章文案「已完成」——验证的是
    TaskDetail 已并轨 task:<id> channel 而非自建轮询（旧实现 waiting_review
    时轮询整体停止，此断言在旧实现上必然超时失败）。
  TODO(Task 9) ③盖章动效场景（占位）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/batch_a_livefeed_acceptance.py
  # 首次需 playwright install chromium

截图落 docs/reviews/batch-a-livefeed-shots/（每次重跑覆盖，保持证据与代码同步）。
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
from urllib.parse import urlparse

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = REPO / "docs" / "reviews" / "batch-a-livefeed-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

# ── 自起后端：tmp 目录 + hello_agent + review_agent（requires_human_review=true）──
WORK = Path(tempfile.mkdtemp(prefix="flai_batch_a_livefeed_"))
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

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

from _auth import login_context, login_httpx, seed_user  # noqa: E402（须在后端就绪后种账户）

seed_user(WORK / "flai_os.db", "本机查看者")
# 第二个账户=「另一位工程师」，跨会话放行的动作方——与本机浏览器登录身份彻底
# 不同（不同 username/cookie jar），而非同一账户借第二个 httpx.Client 重登。
seed_user(WORK / "flai_os.db", "跨会话签发工程师", username="e2e_approver", password="e2e-approver-pass")

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)  # ADR-0019：本机浏览器会话——「等着看」的那一方

    # ── 断言①：全站任务清单单链——TaskConsole + 状态中心抽屉同屏订阅同一
    #    liveFeed 'tasks' channel，非各自轮询 ──
    list_requests: list[str] = []

    def _on_tasks_request(request) -> None:
        if request.method == "GET" and urlparse(request.url).path == "/api/tasks":
            list_requests.append(request.url)

    page.on("request", _on_tasks_request)
    window_start = time.time()
    page.goto(BASE + "/tasks", wait_until="networkidle")
    page.wait_for_selector(".console-list", state="visible", timeout=5000)
    page.get_by_role("button", name="打开状态中心").click()
    page.wait_for_selector(".status-center-drawer", state="visible", timeout=5000)

    # 纯 Python 侧 time.sleep() 不会给渲染进程任何 CDP 活动——无画面刷新需求的
    # headless 页签会被 Chromium 判定为后台而冻结 setTimeout 链（实测：单次大
    # sleep 下 5s 轮询在首拉后即停摆，30s 窗口只剩 1 次请求，双链/单链回归都
    # 测不出来，等于假绿）。每秒一次 page.evaluate 把渲染进程唤醒，讨回真实
    # 的 5s 轮询节奏，断言才咬得住旧双链回归。
    window_deadline = window_start + 30
    while time.time() < window_deadline:
        time.sleep(1)
        page.evaluate("1")
    page.remove_listener("request", _on_tasks_request)

    list_count = len(list_requests)
    check(
        "①全站清单单链：/tasks + 状态中心抽屉同屏 30s 内 /api/tasks 清单请求 ≤8"
        "（单链首拉+6tick+余量；旧双链会 ≥12）",
        list_count <= 8,
        f"count={list_count} urls={list_requests}",
    )
    page.screenshot(path=str(SHOTS / "0_single_chain_30s.png"), full_page=True)

    # ── 建 review_agent 任务，驱动到 waiting_review ──
    page.goto(BASE + "/tasks/new?agent_id=review_agent", wait_until="networkidle")
    page.wait_for_selector(".agent-preview", state="visible", timeout=5000)
    page.locator('input[placeholder="请填写姓名"]').first.fill("批A断言②")
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=8000)
    task_id = page.url.rsplit("/", 1)[-1]

    deadline = time.time() + 30
    while time.time() < deadline:
        if "等待人工审核" in page.locator("body").inner_text():
            break
        time.sleep(1)
    body = page.locator("body").inner_text()
    check("前置：任务进入 waiting_review 且详情页显示等待人工审核",
          "等待人工审核" in body, body[:400])
    page.screenshot(path=str(SHOTS / "1_waiting_review.png"), full_page=True)

    # ── 断言②：另一个 httpx 会话（不共享本机浏览器 cookie，模拟另一位工程师）
    #    直接 API 批准放行；本机页面全程零点击——不点「刷新」，不点「批准放行」──
    approver = login_httpx(BASE, username="e2e_approver", password="e2e-approver-pass")
    resp = approver.post(f"/api/tasks/{task_id}/review", json={"action": "approve", "comment": "跨会话放行验收"})
    check("跨会话 API 批准放行请求成功", resp.status_code == 200, f"status={resp.status_code} body={resp.text[:200]}")

    poke_deadline = time.time() + 12
    seen_completed = False
    while time.time() < poke_deadline:
        if "已完成" in page.locator("body").inner_text():
            seen_completed = True
            break
        time.sleep(0.5)
    body = page.locator("body").inner_text()
    check("②跨会话放行免手动刷新：12s 内页面自行出现「已完成」（零点击）",
          seen_completed is True, body[:400])
    page.screenshot(path=str(SHOTS / "2_auto_completed_no_click.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'BATCH A LIVEFEED ACCEPTANCE ALL GREEN' if not failed else 'BATCH A LIVEFEED ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
