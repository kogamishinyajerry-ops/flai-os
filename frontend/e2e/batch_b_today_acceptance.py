"""批B「今日工作台」验收（批B Task 6）。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/）+ Job Runner + 真 chromium。
除 frontend/dist 构建产物外无外部前置。复用 batch_a_livefeed_acceptance.py
的登录/跨会话 approver/保活样板（同一份 _auth.py）。

覆盖（spec §五）：
  ①/today 渲染五版块（待你签发/进行中/今日交付/Agent 动态/团队总量）；待签发
    计数与全局 StatusDock 角标数同源相等（同页同一份 tasks channel 真值）。
  ②跨会话 approver 批准（httpx，不共享本机浏览器 cookie）→ /today 页面全程
    不动 → 12s 内该任务出现在「今日交付」且其卡播放 .seal-animate（本会话
    亲历「活跃→终态」迁移才播，判据同 TaskDetail T9）。
  ③团队总量条四格数字 === httpx 直查 /api/stats/overview（同 since，since
    从页面 JS 里 evaluate 取 TodayPage 同款「本地周一零点」算式，避免 Python
    侧重算口径漂移）。
  ④新导航直开 /today（全新 browser context，非同一会话）：今日交付里能看到
    历史终态任务，但其卡不播 .seal-animate（非亲历不放）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/batch_b_today_acceptance.py
  # 首次需 playwright install chromium

截图落 docs/reviews/batch-b-shots/（每次重跑覆盖，保持证据与代码同步）。
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
SHOTS = REPO / "docs" / "reviews" / "batch-b-shots"

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
WORK = Path(tempfile.mkdtemp(prefix="flai_batch_b_today_"))
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
# 第二个账户=「跨会话签发工程师」，与本机浏览器登录身份彻底不同（不同
# username/cookie jar），而非同一账户借第二个 httpx.Client 重登。
seed_user(WORK / "flai_os.db", "跨会话签发工程师", username="e2e_approver", password="e2e-approver-pass")

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def poke_wait(page, predicate, timeout_s: float) -> bool:
    """轮询等待 predicate() 为真，每秒 page.evaluate("1") 保活——纯 Python
    time.sleep() 不给渲染进程任何 CDP 活动，headless 后台 tab 会被 Chromium
    判定为后台并冻结 setTimeout 轮询链（canon#50 实证坑，batch_a 同款手法）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
        page.evaluate("1")
    return predicate()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)  # ADR-0019：本机浏览器会话——「等着看」的那一方

    # ── 建 review_agent 任务，驱动到 waiting_review（后续跨会话批准的目标）──
    page.goto(BASE + "/tasks/new?agent_id=review_agent", wait_until="networkidle")
    page.wait_for_selector(".agent-preview", state="visible", timeout=5000)
    page.locator('input[placeholder="请填写姓名"]').first.fill("批B今日交付验收")
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=8000)
    task_id = page.url.rsplit("/", 1)[-1]
    # DeliveryCard 显示 task.name || task.id.slice(0,12)——本任务未设 name（新建表单
    # 「姓名」字段是 hello_agent 的工具入参而非任务标题），故用短 id 作为定位串。
    task_short_id = task_id[:12]

    deadline = time.time() + 30
    while time.time() < deadline:
        if "等待人工审核" in page.locator("body").inner_text():
            break
        time.sleep(1)
    body = page.locator("body").inner_text()
    check("前置：任务进入 waiting_review 且详情页显示等待人工审核",
          "等待人工审核" in body, body[:400])

    # ── 断言①：/today 渲染五版块；待签发计数与全局 StatusDock 角标同源相等 ──
    # 此刻起页面开始「亲历」——onTransition 订阅从 /today 挂载这一刻起才捕捉
    # 后续迁移，早于此的 created→waiting_review 迁移不算数（本测试要验证的
    # 是后面的 waiting_review→completed 才需要被亲历，语义上没有影响）。
    page.goto(BASE + "/today", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".today-section").count() == 5, 10)
    section_count = page.locator(".today-section").count()
    check("①/today 渲染五版块（待你签发/进行中/今日交付/Agent 动态/团队总量）",
          section_count == 5, f"count={section_count}")

    def _counts_match():
        w = page.locator(".today-section-head.waiting").inner_text()
        d = page.locator(".dock-pill-waiting").inner_text() if page.locator(".dock-pill-waiting").count() else ""
        wm, dm = re.search(r"(\d+)$", w), re.search(r"(\d+)$", d)
        return bool(wm and dm and wm.group(1) == dm.group(1))

    matched = poke_wait(page, _counts_match, 10)
    waiting_text = page.locator(".today-section-head.waiting").inner_text()
    dock_text = page.locator(".dock-pill-waiting").inner_text() if page.locator(".dock-pill-waiting").count() else "(无角标)"
    check("①待签发计数 === StatusDock 角标数（同页同源 tasks channel）",
          matched is True, f"today='{waiting_text}' dock='{dock_text}'")
    page.screenshot(path=str(SHOTS / "1_today_five_sections.png"), full_page=True)

    # ── since 从页面 JS 取 TodayPage 同款「本地周一零点」算式，避免 Python
    #    侧重算口径漂移（brief 明示手法）──
    since_iso = page.evaluate(
        "() => { const d = new Date(); d.setHours(0,0,0,0); "
        "d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d.toISOString(); }"
    )

    # ── 断言②：跨会话 approver 批准（不共享本机浏览器 cookie）→ /today 全程
    #    不动 → 12s 内出现在「今日交付」且播放 .seal-animate（亲历）──
    approver = login_httpx(BASE, username="e2e_approver", password="e2e-approver-pass")
    resp = approver.post(f"/api/tasks/{task_id}/review", json={"action": "approve", "comment": "批B今日工作台验收放行"})
    check("跨会话 API 批准放行请求成功", resp.status_code == 200, f"status={resp.status_code} body={resp.text[:200]}")

    appeared = poke_wait(page, lambda: task_short_id in page.locator(".today-section", has_text="今日交付").inner_text(), 12)
    check("②12s 内任务出现在「今日交付」（零点击，页面自行同步）", appeared is True)

    try:
        page.wait_for_selector(".completion-seal.seal-animate", state="visible", timeout=3000)
        seal_animate_witnessed = True
    except Exception:
        seal_animate_witnessed = False
    check("②亲历 waiting_review→completed 迁移：交付卡播放 .seal-animate（仪式只属亲历者）",
          seal_animate_witnessed is True)
    page.screenshot(path=str(SHOTS / "2_delivery_seal_animate.png"), full_page=True)

    # ── 断言③：团队总量条四格 === httpx 直查 /api/stats/overview（同 since）──
    # 批准已在断言②确认落地（后端此刻已是终态，httpx 读到的值不会再变）；
    # 页面侧的 fetchStats() 由 onTransition 补拉纪律异步触发，存在一次网络
    # 往返延迟，故轮询等待页面数字收敛到 API 值，而非单次读取就下判断。
    # /api/stats/overview 需鉴权——复用已登录的 approver client（同 e2e_approver
    # 会话，任意已登录身份皆可读该只读聚合端点，不影响「同 since 同源」判据）。
    overview = approver.get("/api/stats/overview", params={"since": since_iso}, timeout=10)
    check("httpx 直查 /api/stats/overview 成功", overview.status_code == 200, f"status={overview.status_code}")
    body_json = overview.json() if overview.status_code == 200 else {}
    expected_nums = [
        str(body_json.get("tasks_completed")),
        str(body_json.get("reviews_approved")),
        str(body_json.get("curated_cases_total")),
        str(body_json.get("promotions")),
    ]

    def _page_nums():
        return [t.strip() for t in page.locator(".today-stat-num").all_inner_texts()]

    poke_wait(page, lambda: _page_nums() == expected_nums, 15)
    page_nums = _page_nums()
    check("③团队总量条四格数字 === httpx 直查 /api/stats/overview（同 since，同源）",
          page_nums == expected_nums, f"page={page_nums} api={expected_nums} since={since_iso}")
    page.screenshot(path=str(SHOTS / "3_stats_bar_match.png"), full_page=True)

    # ── 断言④：新导航直开 /today（全新 browser context，非同一会话）——今日
    #    交付里能看到该历史终态任务，但绝不播放 .seal-animate（非亲历不放）──
    page2 = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page2.context, BASE)
    page2.goto(BASE + "/today", wait_until="networkidle")
    poke_wait(page2, lambda: page2.locator(".delivery-card").count() > 0, 10)
    delivery_text = page2.locator(".today-section", has_text="今日交付").inner_text()
    has_task = task_short_id in delivery_text
    has_seal_animate = page2.locator(".completion-seal.seal-animate").count() > 0
    check("④新导航直开 /today：今日交付里能看到该历史终态任务", has_task is True, delivery_text[:400])
    check("④新导航直开 /today：交付卡不播 .seal-animate（非亲历不放）", has_seal_animate is False)
    page2.screenshot(path=str(SHOTS / "4_cold_open_no_seal_animate.png"), full_page=True)
    page2.close()

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'BATCH B TODAY ACCEPTANCE ALL GREEN' if not failed else 'BATCH B TODAY ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
