"""任务台（范式 2b 双 Surface）验收走查——原 M8 工作台契约在 2b 骨架手术后重立。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/）+ Job Runner + 真 chromium。
除 frontend/dist 构建产物外无外部前置。

2b 覆盖（双 Surface IA + 任务台三栏）：
  ① 左栏导航收敛为恰两个一级入口（对话 / 任务台）——门户/工作台已撤出导航；
  ② /workbench 深链重定向到 /tasks（旧链接不断）+ 任务台左栏列表渲染
     （API 预置一个任务），到席灯（信任色锁：completed **不给绿**）可见，
     诚实脚注（100 条窗口口径）常驻；②''到席灯颜色级真咬合；
     ②'''/②''''完成未读点（2c）：baseline 后新完成任务亮 clay 点、点开即灭；
  ③ 点任务行 → URL /tasks/:id + 中栏「任务详情」叙事流（TaskDetail 复用，
     m2 全部详情契约由 m2_acceptance 继续把守）；
  ④ 任务视图导航高亮归属「任务台」；
  ⑤ /portal 深链仍可达（门户降级为 composer 选择器后不失联）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m8_workbench_acceptance.py

截图落 docs/reviews/m8-workbench-shots/（每次重跑覆盖）。
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
SHOTS = REPO / "docs" / "reviews" / "m8-workbench-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

# ── 自起后端：tmp 目录 + hello_agent ──
WORK = Path(tempfile.mkdtemp(prefix="flai_m8_workbench_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")

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

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

# 预置一个任务喂任务台列表（走真实 API，非直插库）。
_created = httpx.post(
    BASE + "/api/tasks",
    json={"agent_id": "hello_agent", "name": "工作台验收样例任务", "inputs": {"name": "M8"}, "created_by": "验收工程师"},
    timeout=5,
)
if _created.status_code not in (200, 201):
    sys.exit(f"诚实失败：预置任务失败 {_created.status_code} {_created.text[:200]}")
SEED_TASK_ID = _created.json()["id"]

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # ── ① 左栏导航恰两个一级入口（双 Surface）──
    page.goto(BASE + "/", wait_until="networkidle")
    nav_items = page.locator(".sidebar-nav .nav-link")
    nav_texts = [t.strip() for t in nav_items.all_inner_texts()]
    nav_ok = nav_texts == ["对话", "任务台"]
    check("①左栏导航收敛为双 Surface（对话/任务台）", nav_ok, f"实际={nav_texts}")
    page.screenshot(path=str(SHOTS / "1_nav_two.png"))

    # ── ② /workbench 旧深链重定向 /tasks + 任务台左栏列表 + 到席灯 + 诚实脚注 ──
    page.goto(BASE + "/workbench", wait_until="networkidle")
    page.wait_for_url(re.compile(r"/tasks$"), timeout=5000)
    page.wait_for_selector(".cl-item", timeout=5000)
    body = page.locator("body").inner_text()
    row = page.locator(".cl-item", has_text="工作台验收样例任务").first
    lamp_visible = row.locator(".cl-lamp").is_visible()
    foot_ok = "最近任务窗口" in body  # 诚实脚注：窗口外不虚报
    check("②/workbench→/tasks 重定向 + 任务台列表 + 到席灯 + 诚实脚注",
          row.is_visible() and lamp_visible and foot_ok,
          f"row={row.is_visible()} lamp={lamp_visible} foot={foot_ok}")
    page.screenshot(path=str(SHOTS / "2_console.png"), full_page=True)

    # 任务台页导航高亮 = 任务台
    active_console = page.locator(".sidebar-nav .nav-link.is-active").inner_text().strip()
    check("②'任务台页高亮归属任务台", active_console == "任务台", f"active={active_console}")

    # 信任色锁真咬合（2b 双镜头指出旧断言只查可见性=声明超出证据）：
    # 等 hello_agent 跑到 completed，到席灯必须中性墨 --ink-soft #6b6259——
    # completed 永远不给绿（绿仅真实 REAL 结果）。
    for _ in range(60):
        if httpx.get(BASE + f"/api/tasks/{SEED_TASK_ID}", timeout=2).json()["status"] == "completed":
            break
        time.sleep(0.2)
    page.reload(wait_until="networkidle")
    page.wait_for_selector(".cl-item", timeout=5000)
    row = page.locator(".cl-item", has_text="工作台验收样例任务").first
    expect(row.locator(".cl-lamp")).to_have_css("background-color", "rgb(107, 98, 89)", timeout=8000)
    check("②''completed 到席灯=中性墨非绿（信任色锁真咬合）", True)

    # ── ②''' 完成未读点（2c）：baseline 之后新完成且没打开过 → clay 点；点开即灭 ──
    # baseline 已在首次进任务台时锚定（上方 goto /workbench），此后创建的任务
    # 完成时刻必然晚于 baseline——不依赖 SEED_TASK 的完成/首访时序。
    _t2 = httpx.post(
        BASE + "/api/tasks",
        json={"agent_id": "hello_agent", "name": "未读点样例任务", "inputs": {"name": "unseen"}, "created_by": "验收工程师"},
        timeout=5,
    )
    if _t2.status_code not in (200, 201):
        sys.exit(f"诚实失败：未读点样例任务创建失败 {_t2.status_code}")
    T2_ID = _t2.json()["id"]
    for _ in range(60):
        if httpx.get(BASE + f"/api/tasks/{T2_ID}", timeout=2).json()["status"] == "completed":
            break
        time.sleep(0.2)
    row2 = page.locator(".cl-item", has_text="未读点样例任务").first
    expect(row2.locator(".cl-unseen-dot")).to_be_visible(timeout=9000)  # 等 5s 轮询翻面
    check("②'''baseline 后新完成任务亮未读点", True)
    row2.click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=5000)
    expect(row2.locator(".cl-unseen-dot")).to_have_count(0)  # select 即 markSeen，当行立即熄灭
    check("②''''点开任务未读点即灭", True)
    page.screenshot(path=str(SHOTS / "2b_unseen_dot_cleared.png"))

    # ── ③ 点任务行 → /tasks/:id 中栏叙事流（TaskDetail 复用）──
    row.click()
    # 精确等 SEED 的 URL——②''' 已把 URL 带到 /tasks/:T2，宽 regex 会立即误过
    page.wait_for_url(re.compile(rf"/tasks/{SEED_TASK_ID}$"), timeout=5000)
    expect(page.get_by_role("heading", name="任务详情")).to_be_visible(timeout=5000)
    landed_ok = page.url.endswith(SEED_TASK_ID)
    check("③点任务行→中栏任务叙事流（URL /tasks/:id）", landed_ok, f"url={page.url} seed={SEED_TASK_ID}")

    # ── ④ 任务视图高亮仍归属任务台 ──
    active_detail = page.locator(".sidebar-nav .nav-link.is-active").inner_text().strip()
    check("④任务视图高亮归属任务台", active_detail == "任务台", f"active={active_detail}")
    page.screenshot(path=str(SHOTS / "3_detail_in_console.png"), full_page=True)

    # ── ⑤ /portal 深链仍可达（门户降级不失联）──
    page.goto(BASE + "/portal", wait_until="networkidle")
    portal_ok = "Agent" in page.locator("body").inner_text()
    check("⑤/portal 深链仍可达（门户降级不失联）", portal_ok)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'TASK CONSOLE 2B ALL GREEN' if not failed else 'TASK CONSOLE 2B FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
