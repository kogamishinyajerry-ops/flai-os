"""批A「活的工作台」与 P2.1 断连真实性验收。

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
  ③CompletionSeal 盖章动效——仪式只属于亲历者：③a 复用②的跨会话放行场景，
    本机页面全程开着观察到 waiting_review→completed 的迁移，应播放 .seal-animate
    合拢仪式；③b 另开新页面直接访问同一（已终态）任务，CompletionSeal 正常渲染
    但绝不播放（非亲历不放）。
  ④P2.1 warm disconnect 保留最后真实快照并显式标旧；恢复必须 sequence-zero。
  ⑤注入 event sequence gap 时可疑增量零落地；full resnapshot 失败继续标旧，人工
    重试仍从 sequence-zero 恢复。
  ⑥cold disconnect 不渲染任务假空态；首次恢复是静态权威快照。
  ⑦断连期间任务落定，双 channel 恢复都不得补播亲历完成动画。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/batch_a_livefeed_acceptance.py
  # 首次需 playwright install chromium

截图默认落临时 artifact；仅 UPDATE_GOLDENS=1 更新 docs/reviews/batch-a-livefeed-shots/。
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
from pathlib import Path

from _artifacts import resolve_shots_dir
from urllib.parse import parse_qs, urlparse

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = resolve_shots_dir(REPO, "batch-a-livefeed-shots")

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
from backend.app.storage import repos

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
        "①全站清单单链：/tasks + 状态中心抽屉同屏 30s 内 /api/tasks 清单请求为 2..8"
        "（下界拒绝死链假绿；上界拒绝旧双链 ≥12）",
        2 <= list_count <= 8,
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

    # ── 断言④：暖断连显式标旧；恢复必须先 sequence-zero ──
    live_pattern = "**/api/tasks/*/live-snapshot*"
    live_path = f"/api/tasks/{task_id}/live-snapshot"

    def _abort_live_snapshot(route) -> None:
        if urlparse(route.request.url).path == live_path:
            route.abort()
        else:
            route.continue_()

    page.route(live_pattern, _abort_live_snapshot)
    page.locator(".task-detail .refresh-btn").click()
    page.locator(".task-detail .connection-truth", has_text="当前显示上次成功快照").wait_for(
        state="visible", timeout=5000
    )
    warm_body = page.locator(".task-detail").inner_text()
    check("④暖断连：保留 waiting_review 真快照并明确显示上次成功快照",
          "等待人工审核" in warm_body and "当前显示上次成功快照" in warm_body,
          warm_body[:500])
    page.unroute(live_pattern, _abort_live_snapshot)

    reconnect_urls: list[str] = []

    def _capture_live_request(request) -> None:
        if urlparse(request.url).path == live_path:
            reconnect_urls.append(request.url)

    page.on("request", _capture_live_request)
    page.locator(".task-detail .connection-retry").click()
    page.locator(".task-detail .connection-truth").wait_for(state="detached", timeout=8000)
    page.remove_listener("request", _capture_live_request)
    check("④暖断连恢复：首轮含 after_sequence=0 的完整快照请求",
          any(parse_qs(urlparse(url).query).get("after_sequence") == ["0"] for url in reconnect_urls),
          f"urls={reconnect_urls}")

    # ── 断言⑤：缺号 delta 整批拒绝；自动 full 失败仍保旧，手动恢复 sequence-zero ──
    suspect_message = "GAP-SUSPECT-NEVER-PARTIAL"
    conn = app.state.conn_factory()
    try:
        repos.append_event(
            conn,
            task_id=task_id,
            agent_id="review_agent",
            event_type="agent_log",
            level="info",
            message=suspect_message,
            payload={"witness": "p2.1-gap"},
        )
        conn.commit()
    finally:
        conn.close()

    gap_state = {"forged": False, "full_failed": False}

    def _inject_gap(route) -> None:
        if urlparse(route.request.url).path != live_path:
            route.continue_()
            return
        params = parse_qs(urlparse(route.request.url).query)
        after = int(params.get("after_sequence", ["0"])[0])
        if after > 0 and gap_state["forged"] is False:
            upstream = route.fetch()
            payload = upstream.json()
            if payload.get("events"):
                payload["events"][0]["sequence"] += 1
                payload["cursor"]["sequence"] += 1
                gap_state["forged"] = True
                route.fulfill(
                    status=200,
                    content_type="application/json",
                    body=json.dumps(payload, ensure_ascii=False),
                )
                return
            route.fulfill(response=upstream)
            return
        if after == 0 and gap_state["forged"] is True and gap_state["full_failed"] is False:
            gap_state["full_failed"] = True
            route.fulfill(
                status=503,
                content_type="application/json",
                body=json.dumps({"detail": "gap-resnapshot-witness"}),
            )
            return
        route.continue_()

    page.route(live_pattern, _inject_gap)
    page.locator(".task-detail .refresh-btn").click()
    page.locator(".task-detail .connection-truth", has_text="当前显示上次成功快照").wait_for(
        state="visible", timeout=8000
    )
    gap_body = page.locator(".task-detail").inner_text()
    check("⑤gap 注入确实发生且自动 sequence-zero resnapshot 被故障注入拒绝",
          gap_state == {"forged": True, "full_failed": True}, f"state={gap_state}")
    check("⑤可疑 delta 零部分落地：完整重取成功前不显示 suspect event",
          suspect_message not in gap_body, gap_body[:600])
    page.unroute(live_pattern, _inject_gap)

    gap_recovery_urls: list[str] = []

    def _capture_gap_recovery(request) -> None:
        if urlparse(request.url).path == live_path:
            gap_recovery_urls.append(request.url)

    page.on("request", _capture_gap_recovery)
    page.locator(".task-detail .connection-retry").click()
    page.locator(".task-detail .connection-truth").wait_for(state="detached", timeout=8000)
    page.remove_listener("request", _capture_gap_recovery)
    recovered_body = page.locator(".task-detail").inner_text()
    check("⑤gap 后人工恢复：再次 sequence-zero 且权威快照最终包含真实事件",
          any(parse_qs(urlparse(url).query).get("after_sequence") == ["0"] for url in gap_recovery_urls)
          and suspect_message in recovered_body,
          f"urls={gap_recovery_urls} body={recovered_body[:500]}")

    # ── 断言②：另一个 httpx 会话（不共享本机浏览器 cookie，模拟另一位工程师）
    #    直接 API 批准放行；本机页面全程零点击——不点「刷新」，不点「批准放行」──
    approver = login_httpx(BASE, username="e2e_approver", password="e2e-approver-pass")
    resp = approver.post(f"/api/tasks/{task_id}/review", json={"action": "approve", "comment": "跨会话放行验收"})
    check("跨会话 API 批准放行请求成功", resp.status_code == 200, f"status={resp.status_code} body={resp.text[:200]}")

    # 批八 TaskConsole 新增「已完成 · 0」筛选 chip 后，body 级字符串会在任务仍
    # waiting_review 时产生假阳性。②必须盯任务详情的终态盖章这一精确产品事实，
    # 不能把同屏筛选标签冒充状态迁移完成。
    try:
        page.locator(".completion-seal", has_text="已完成").wait_for(
            state="visible", timeout=12_000
        )
        seen_completed = True
    except Exception:
        seen_completed = False
    body = page.locator("body").inner_text()
    check("②跨会话放行免手动刷新：12s 内页面自行出现「已完成」（零点击）",
          seen_completed is True, body[:400])
    page.screenshot(path=str(SHOTS / "2_auto_completed_no_click.png"), full_page=True)

    # ── 断言③：CompletionSeal 盖章动效——仪式只属于亲历者（Task 9）──
    # ③a 亲历：复用刚验证完的跨会话放行场景——本机页面全程开着（未刷新未点击），
    #    从 waiting_review 到自行出现「已完成」的这次迁移就是本会话「亲历」的
    #    活跃→终态过程，CompletionSeal 应播放合拢仪式（.seal-animate）。
    try:
        page.wait_for_selector(".completion-seal.seal-animate", state="visible", timeout=3000)
        seal_animate_witnessed = True
    except Exception:
        seal_animate_witnessed = False
    check("③a 亲历放行→自动到终态：CompletionSeal 播放 .seal-animate（仪式只属亲历者）",
          seal_animate_witnessed is True)
    page.screenshot(path=str(SHOTS / "3a_seal_animate_witnessed.png"), full_page=True)

    # ③b 历史直开：另开一个全新页面直接访问同一（此刻已是终态）任务——CompletionSeal
    #    组件应正常渲染（非终态渲染 null 的既有语义不变），但绝不播放合拢仪式，因为
    #    这个新页面从未亲历「活跃→终态」的迁移，只是冷启动直接看到已落定的结果。
    page2 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page2.context, BASE)
    page2.goto(BASE + f"/tasks/{task_id}", wait_until="networkidle")
    page2.wait_for_selector(".completion-seal", state="visible", timeout=5000)
    has_seal = page2.locator(".completion-seal").count() > 0
    has_seal_animate = page2.locator(".completion-seal.seal-animate").count() > 0
    check("③b 历史直开：CompletionSeal 正常渲染", has_seal is True)
    check("③b 历史直开：不播 .seal-animate（非亲历不放）", has_seal_animate is False)
    page2.screenshot(path=str(SHOTS / "3b_seal_static_cold_open.png"), full_page=True)
    page2.close()

    # ── 断言⑥：cold disconnect 零假数据；首次恢复只静态显影，不补播动画 ──
    page3 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page3.context, BASE)

    def _abort_cold(route) -> None:
        if urlparse(route.request.url).path == live_path:
            route.abort()
        else:
            route.continue_()

    page3.route(live_pattern, _abort_cold)
    page3.goto(BASE + f"/tasks/{task_id}", wait_until="domcontentloaded")
    page3.locator(".task-detail .connection-truth", has_text="当前无法同步").wait_for(
        state="visible", timeout=8000
    )
    check("⑥cold disconnect：无任务快照时不渲染 completion seal",
          page3.locator(".task-detail .completion-seal").count() == 0)
    page3.unroute(live_pattern, _abort_cold)
    cold_urls: list[str] = []
    page3.on("request", lambda request: cold_urls.append(request.url)
             if urlparse(request.url).path == live_path else None)
    page3.locator(".task-detail .connection-retry").click()
    page3.locator(".task-detail .completion-seal").wait_for(state="visible", timeout=8000)
    check("⑥cold reconnect：sequence-zero 恢复且历史完成只静态显示",
          any(parse_qs(urlparse(url).query).get("after_sequence") == ["0"] for url in cold_urls)
          and page3.locator(".task-detail .completion-seal.seal-animate").count() == 0,
          f"urls={cold_urls}")

    page3.close()

    # 全新页面首次成功冷载终态后只可能排 30s timer；此处再阻断带外刷新并观察
    # 8s 内第二次请求，排除复用 cold-recovery 5s timer 造成的假绿。
    page3b = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page3b.context, BASE)
    page3b.goto(BASE + f"/tasks/{task_id}", wait_until="networkidle")
    page3b.locator(".task-detail .completion-seal").wait_for(state="visible", timeout=5000)
    terminal_retry = {"attempts": 0}

    def _abort_terminal_retry(route) -> None:
        if urlparse(route.request.url).path == live_path:
            terminal_retry["attempts"] += 1
            route.abort()
        else:
            route.continue_()

    page3b.route(live_pattern, _abort_terminal_retry)
    page3b.locator(".task-detail .refresh-btn").click()
    page3b.locator(".task-detail .connection-truth", has_text="当前显示上次成功快照").wait_for(
        state="visible", timeout=5000
    )
    retry_deadline = time.time() + 8
    while terminal_retry["attempts"] < 2 and time.time() < retry_deadline:
        page3b.wait_for_timeout(250)
    check("⑥b 终态手动核对失败后 8s 内自动按断连节奏重试",
          terminal_retry["attempts"] >= 2, f"attempts={terminal_retry['attempts']}")
    page3b.unroute(live_pattern, _abort_terminal_retry)
    page3b.close()

    # ── 断言⑦：暖断连期间完成，task/list 双 authority 调和均不得补播亲历动画 ──
    offline_created = approver.post(
        "/api/tasks",
        json={
            "agent_id": "review_agent",
            "name": "P2.1 离线落定",
            "inputs": {"name": "P2.1 离线落定"},
        },
    )
    check("⑦前置：创建离线落定任务", offline_created.status_code == 200,
          offline_created.text[:300])
    offline_task_id = offline_created.json()["id"]
    offline_deadline = time.time() + 30
    while time.time() < offline_deadline:
        if approver.get(f"/api/tasks/{offline_task_id}").json().get("status") == "waiting_review":
            break
        time.sleep(0.5)
    check("⑦前置：离线落定任务进入 waiting_review",
          approver.get(f"/api/tasks/{offline_task_id}").json().get("status") == "waiting_review")

    page4 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page4.context, BASE)
    page4.goto(BASE + f"/tasks/{offline_task_id}", wait_until="networkidle")
    page4.get_by_text("等待人工审核", exact=False).first.wait_for(state="visible", timeout=8000)
    offline_live_path = f"/api/tasks/{offline_task_id}/live-snapshot"
    block_pattern = "**/api/tasks**"

    blocked_authorities = {"list": 0, "detail": 0}

    def _block_task_authorities(route) -> None:
        path = urlparse(route.request.url).path
        if path == "/api/tasks" or path == offline_live_path:
            blocked_authorities["list" if path == "/api/tasks" else "detail"] += 1
            route.abort()
        else:
            route.continue_()

    page4.route(block_pattern, _block_task_authorities)
    page4.locator(".task-detail .refresh-btn").click()
    page4.locator(".task-detail .connection-truth", has_text="当前显示上次成功快照").wait_for(
        state="visible", timeout=5000
    )
    # 让全局 tasks channel 也亲历一次失败，恢复时它会走 reconcile-suppressed 分支。
    for _ in range(6):
        time.sleep(1)
        page4.evaluate("1")
    check("⑦双 authority 断连注入实际命中 list 与 detail",
          blocked_authorities["list"] >= 1 and blocked_authorities["detail"] >= 1,
          str(blocked_authorities))
    offline_approved = approver.post(
        f"/api/tasks/{offline_task_id}/review",
        json={"action": "approve", "comment": "断连期间落定"},
    )
    check("⑦断连期间外部批准成功", offline_approved.status_code == 200,
          offline_approved.text[:300])
    recovered_authorities = {"list": 0, "detail": 0}

    def _capture_authority_recovery(request) -> None:
        path = urlparse(request.url).path
        if path == "/api/tasks":
            recovered_authorities["list"] += 1
        elif path == offline_live_path:
            recovered_authorities["detail"] += 1

    page4.on("request", _capture_authority_recovery)
    page4.unroute(block_pattern, _block_task_authorities)
    page4.locator(".task-detail .connection-retry").click()
    page4.locator(".task-detail .completion-seal").wait_for(state="visible", timeout=8000)
    for _ in range(6):
        time.sleep(1)
        page4.evaluate("1")
    page4.remove_listener("request", _capture_authority_recovery)
    check("⑦双 authority 恢复后 list 与 detail 都重新核对成功",
          recovered_authorities["list"] >= 1 and recovered_authorities["detail"] >= 1,
          str(recovered_authorities))
    page4.locator(".status-dock").click()
    recent_offline = page4.locator(
        ".sc-group:has(.sc-group-label:has-text('最近落定')) .sc-item-name",
        has_text="P2.1 离线落定",
    )
    recent_offline.wait_for(state="visible", timeout=5000)
    waiting_offline = page4.locator(
        ".sc-group:has(.sc-group-label.waiting) .sc-item-name",
        has_text="P2.1 离线落定",
    )
    check("⑦ list authority 真落地：离线落定任务已从待签迁到最近落定",
          recent_offline.count() == 1 and waiting_offline.count() == 0)
    check("⑦断连期间落定后恢复：显示权威 completed，但不补播 .seal-animate",
          page4.locator(".task-detail .completion-seal.seal-animate").count() == 0,
          page4.locator(".task-detail").inner_text()[:500])
    page4.close()

    # ── 断言⑧：任务清单 authority cold failure 时，Today/StatusCenter 都不得把
    #    未知解释成五个空版块或“没有待签任务”。只有 loaded 真快照才有空态资格。 ──
    page5 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page5.context, BASE)

    def _abort_cold_list(route) -> None:
        if urlparse(route.request.url).path == "/api/tasks":
            route.abort()
        else:
            route.continue_()

    page5.route("**/api/tasks*", _abort_cold_list)
    page5.goto(BASE + "/today", wait_until="domcontentloaded")
    page5.locator(".today .connection-truth", has_text="当前无法同步").wait_for(
        state="visible", timeout=8000
    )
    check("⑧ Today cold failure 不渲染任何 today-section 假空态",
          page5.locator(".today .today-section").count() == 0)
    page5.locator(".status-dock").click()
    page5.locator(".status-center-drawer .connection-truth", has_text="当前无法同步").wait_for(
        state="visible", timeout=5000
    )
    check("⑧ StatusCenter cold failure 不渲染 sc-group 或零任务结论",
          page5.locator(".status-center-drawer .sc-group").count() == 0)
    page5.close()

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'BATCH A LIVEFEED ACCEPTANCE ALL GREEN' if not failed else 'BATCH A LIVEFEED ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
