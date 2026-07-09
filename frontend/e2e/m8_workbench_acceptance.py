"""M8 协作工作台验收走查（P1 切片起，随 P2-P5 长大）。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/）+ Job Runner + 真 chromium。
除 frontend/dist 构建产物外无外部前置。

P1 覆盖（视觉地基 + IA 骨架）：
  ① 顶导航收敛为恰三个真入口（智能导引 / Agent 门户 / 协作工作台），旧的
     创建任务/任务历史/反馈**已从导航撤出**（路由仍在，上下文内可达）；
  ② /workbench 渲染协作工作台 hero + 最近任务列表（API 预置一个任务），
     到席灯（信任色锁：completed **不给绿**）可见；
  ③ 点任务行 → 落 /tasks/:id 详情；
  ④ 任务详情页顶导航高亮仍归属「协作工作台」（activeMenu 把 /tasks/* 映射过去）；
  ⑤ 诚实占位文案在页面可见（多 Agent 协作会话视图在建设中，不假装已有）。

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

# 预置一个任务喂工作台列表（走真实 API，非直插库）。
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

    # ── ① 顶导航恰三个真入口 ──
    page.goto(BASE + "/", wait_until="networkidle")
    nav_items = page.locator(".nav-menu .el-menu-item")
    nav_texts = [t.strip() for t in nav_items.all_inner_texts()]
    nav_ok = nav_texts == ["智能导引", "Agent 门户", "协作工作台"]
    check("①顶导航收敛为恰三入口（旧三页已撤出导航）", nav_ok, f"实际={nav_texts}")
    page.screenshot(path=str(SHOTS / "1_nav_three.png"))

    # ── ② /workbench 渲染 hero + 任务列表 + 到席灯 ──
    page.goto(BASE + "/workbench", wait_until="networkidle")
    page.wait_for_selector(".wb-row", timeout=5000)
    body = page.locator("body").inner_text()
    hero_ok = "协作工作台" in body and "从导引开始一个协作" in body
    row = page.locator(".wb-row", has_text="工作台验收样例任务").first
    lamp_visible = row.locator(".wb-lamp").is_visible()
    check("②工作台 hero + 最近任务列表 + 到席灯可见", hero_ok and row.is_visible() and lamp_visible,
          f"hero={hero_ok} row={row.is_visible()} lamp={lamp_visible}")
    # ⑤ 诚实占位：协作会话视图在建设中
    placeholder_ok = "协作会话" in body and "建设中" in body
    check("⑤多Agent协作会话视图诚实占位文案可见", placeholder_ok, body[:400])
    page.screenshot(path=str(SHOTS / "2_workbench.png"), full_page=True)

    # 工作台页顶导航高亮 = 协作工作台
    active_wb = page.locator(".nav-menu .el-menu-item.is-active").inner_text().strip()
    check("②'工作台页高亮归属协作工作台", active_wb == "协作工作台", f"active={active_wb}")

    # ── ③ 点任务行 → 落详情页 ──（SPA 客户端跳转，异步渲染需显式等标题出现）
    row.click()
    page.wait_for_url(re.compile(r"/tasks/task_[0-9a-f]+"), timeout=5000)
    expect(page.get_by_role("heading", name="任务详情")).to_be_visible(timeout=5000)
    landed_ok = page.url.endswith(SEED_TASK_ID)
    check("③点任务行→落任务详情页", landed_ok, f"url={page.url} seed={SEED_TASK_ID}")

    # ── ④ 详情页顶导航高亮仍归属协作工作台（activeMenu 把 /tasks/* 映射过去）──
    active_detail = page.locator(".nav-menu .el-menu-item.is-active").inner_text().strip()
    check("④任务详情页高亮仍归属协作工作台", active_detail == "协作工作台", f"active={active_detail}")
    page.screenshot(path=str(SHOTS / "3_detail_highlight.png"))

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M8 WORKBENCH P1 ALL GREEN' if not failed else 'M8 WORKBENCH P1 FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
