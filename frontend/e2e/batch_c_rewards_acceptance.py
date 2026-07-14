"""批C「成长激励」验收（批C Task 8）。

自包含：脚本自起后端（tmp 目录，绝不碰真实 data/ 与真实 agents/）+ Job Runner
+ 真 chromium。除 frontend/dist 构建产物外无外部前置。骨架（tmp 目录 / seed
agent / 起 uvicorn / 健康探测 / SHOTS 目录 / 保活 poke_wait）照抄
batch_b_today_acceptance.py；晋升 agent 变体（3 case 全绿评测集）+ 治理弹窗
promote 流程照抄 m10_governance_acceptance.py。

覆盖（spec §三 e2e）：
  ①成长档案+晋升史摊开：治理弹窗内 .gov-ladder / .gov-cases-count 可见；
    造好一条历史晋升审计行（record_promotion 直插，不改 agent.yaml）+ 一次
    真实live晋升 → .gov-promotion-card 数 >= 2（摊开全部而非只 [0]）。
  ②亲历动效：本会话内点「申请晋升 L1」成功 → 最新晋升卡出现 .promote-burst
    （非亲历历史卡不应带此 class）。
  ③/me 同源：/me 概览「累计发起」数字 === httpx 直查 /api/me/contributions
    （同 since，since 取页面 MePage 同款 weekStartIso JS 算式）。
  ④私有越权：第二账户 bob 的 /api/me/contributions 只统计 bob 自己的任务；
    alice 已登录 client 带 ?username=bob_e2e 查询仍返回 alice 自己的数据
    （query 越权被服务端忽略——归因主键只认会话身份，不认查询参数）。
  ⑤诚实缺口条：.me-honest-gap 文案在屏。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/batch_c_rewards_acceptance.py

截图落 docs/reviews/batch-c-shots/（每次重跑覆盖，保持证据与代码同步）。
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
SHOTS = REPO / "docs" / "reviews" / "batch-c-shots"

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
from backend.app.storage import repos
from backend.app.storage.db import get_conn

# ── 自起后端：tmp 包副本（hello_agent + governed_agent 变体：审核门+三 case
#    全绿评测集，照抄 m10 样板，保证「跑评测→3/3」能真走通晋升门）──
WORK = Path(tempfile.mkdtemp(prefix="flai_batch_c_rewards_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")
GOV_DIR = AGENTS_DIR / "governed_agent"
shutil.copytree(REPO / "agents" / "hello_agent", GOV_DIR)
_yaml = GOV_DIR / "agent.yaml"
_text = _yaml.read_text(encoding="utf-8")
assert "id: hello_agent" in _text and "requires_human_review: false" in _text
_yaml.write_text(
    _text.replace("id: hello_agent", "id: governed_agent")
    .replace("requires_human_review: false", "requires_human_review: true"),
    encoding="utf-8",
)
GOV_CASES = GOV_DIR / "eval_cases"
for f in GOV_CASES.glob("*.json"):
    f.unlink()
for name, case in (
    ("case_001.json", {"case_id": "case_001", "description": "正常路停审",
                       "inputs": {"name": "世界"},
                       "checks": [{"kind": "status_is", "value": "waiting_review"}]}),
    ("case_002.json", {"case_id": "case_002", "description": "缺字段失败路",
                       "inputs": {},
                       "checks": [{"kind": "status_is", "value": "failed"}]}),
    ("case_003.json", {"case_id": "case_003", "description": "非法类型失败路",
                       "inputs": {"name": 1},
                       "checks": [{"kind": "status_is", "value": "failed"}]}),
):
    (GOV_CASES / name).write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

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

DB_PATH = WORK / "flai_os.db"

seed_user(DB_PATH, "验收工程师")  # 默认 e2e_engineer/e2e-pass-flai（_auth 默认值）
seed_user(DB_PATH, "鲍勃", username="bob_e2e", password="bob-e2e-pass")


def _advance_to_completed(conn, task_id: str) -> None:
    """created → completed，走十态状态机合法路径（seed 用，非真实执行）。"""
    for st in ("queued", "validating", "running", "analyzing", "completed"):
        repos.set_task_status(conn, task_id, st)


def _seed_task(conn, *, created_by: str, created_by_username: str, name: str,
                completed: bool) -> str:
    task_id = f"task_{uuid.uuid4().hex}"
    repos.create_task(
        conn,
        task_id=task_id,
        agent_id="hello_agent",
        agent_version="0.1.0",
        name=name,
        created_by=created_by,
        created_by_username=created_by_username,
    )
    if completed:
        _advance_to_completed(conn, task_id)
    return task_id


# ── ①前置：历史晋升审计行（不改 agent.yaml，governed_agent 保持 L0——本次
#    live L0→L1 晋升仍能真的走通）+ alice/bob 的任务种子（③④用）──
_conn = get_conn(DB_PATH)
try:
    repos.record_promotion(
        _conn,
        agent_id="governed_agent",
        agent_version="0.1.0",
        from_maturity="L0",
        to_maturity="L1",
        eval_run_id="seed-hist",
        checks={},
        confirmations={},
        confirmed_by="历史签发人",
    )
    for i in range(3):
        _seed_task(_conn, created_by="验收工程师", created_by_username="e2e_engineer",
                   name=f"alice 种子任务 {i}", completed=(i < 2))
    for i in range(2):
        _seed_task(_conn, created_by="鲍勃", created_by_username="bob_e2e",
                   name=f"bob 种子任务 {i}", completed=(i < 1))
finally:
    _conn.close()

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
    判定为后台并冻结 setTimeout 轮询链（canon#50 实证坑，batch_a/b 同款手法）。"""
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.5)
        page.evaluate("1")
    return predicate()


with sync_playwright() as p:
    browser = p.chromium.launch()
    # pin 亮色：颜色/文案断言不许随 CI 环境漂移
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)  # ADR-0019：alice 本机浏览器会话

    # ── ①成长档案：打开 governed_agent 的治理弹窗 → 四版块（含 ladder/cases-count）──
    page.goto(BASE + "/portal", wait_until="networkidle")
    gov_card = page.locator(".agent-card", has_text="governed_agent")
    gov_card.locator(".gov-entry").click()
    expect(page.locator(".gov-dialog")).to_be_visible(timeout=5000)
    check("①治理弹窗内 .gov-ladder 可见", page.locator(".gov-ladder").count() > 0)
    check("①治理弹窗内 .gov-cases-count 可见", page.locator(".gov-cases-count").count() > 0)
    check("①晋升前：历史晋升行已在晋升史里可见（1 条）",
          page.locator(".gov-promotion-card").count() == 1,
          f"count={page.locator('.gov-promotion-card').count()}")
    page.screenshot(path=str(SHOTS / "1_growth_profile.png"), full_page=True)

    # ── ②亲历动效：跑评测 → 全绿 3/3 → 勾确认 → 申请晋升 L1 → 最新卡带 .promote-burst ──
    page.locator(".gov-run-btn").click()
    deadline = time.time() + 60
    summary = ""
    while time.time() < deadline:
        if page.locator(".gov-run-summary").count() > 0:
            summary = page.locator(".gov-run-summary").inner_text()
            if "3/3" in summary:
                break
        time.sleep(1)
    check("②跑评测→全绿摘要 3/3", "3/3" in summary, summary[:200])

    page.locator(".gov-promote-confirm").click()
    page.locator(".gov-promote-submit").click()
    burst_witnessed = False
    try:
        page.wait_for_selector(".gov-promotion-card.promote-burst", timeout=8000)
        burst_witnessed = True
    except Exception:
        burst_witnessed = False
    check("②本会话亲历晋升：最新晋升卡播放 .promote-burst", burst_witnessed is True)
    page.screenshot(path=str(SHOTS / "2_promote_burst.png"), full_page=True)

    # ── ①晋升史摊开：>=2 张卡（历史 1 + 本次 live 1），非只展示 [0] ──
    card_count = page.locator(".gov-promotion-card").count()
    check("①晋升史摊开：.gov-promotion-card 数 >= 2（历史+本次全展开）",
          card_count >= 2, f"count={card_count}")
    dialog_text = page.locator(".gov-dialog").inner_text()
    check("①晋升史含历史签发人与本会话签发人（验收工程师）双条",
          "历史签发人" in dialog_text and "验收工程师" in dialog_text, dialog_text[-400:])
    page.keyboard.press("Escape")

    # ── ③④⑤ /me：同源数字 + 私有越权 + 诚实缺口条 ──
    page.goto(BASE + "/me", wait_until="networkidle")
    poke_wait(page, lambda: page.locator(".me-overview").count() > 0, 10)
    check("③/me 页面 .me-overview 可见", page.locator(".me-overview").count() > 0)

    since_iso = page.evaluate(
        "() => { const n=new Date(); const d=(n.getDay()+6)%7;"
        " return new Date(n.getFullYear(),n.getMonth(),n.getDate()-d,0,0,0,0).toISOString(); }"
    )

    alice_api = login_httpx(BASE, username="e2e_engineer", password="e2e-pass-flai")
    api_contrib = alice_api.get("/api/me/contributions", params={"since": since_iso}, timeout=10).json()

    def _ui_total():
        return page.inner_text(".me-overview .me-stat:last-child .me-stat-num").strip()

    poke_wait(page, lambda: _ui_total() == str(api_contrib["total_created"]), 10)
    ui_total = _ui_total()
    check("③/me 累计发起 UI 数字 === httpx 直查 /api/me/contributions（同 since，同源）",
          ui_total == str(api_contrib["total_created"]),
          f"ui={ui_total!r} api_total_created={api_contrib['total_created']} since={since_iso}")
    page.screenshot(path=str(SHOTS / "3_me_overview.png"), full_page=True)

    # ── ⑤诚实缺口条 ──
    check("⑤诚实缺口条 .me-honest-gap 在屏", page.query_selector(".me-honest-gap") is not None)

    # ── ④私有越权：bob 自己的 contributions 只反映 bob 自己的任务 ──
    bob_api = login_httpx(BASE, username="bob_e2e", password="bob-e2e-pass")
    bob_contrib = bob_api.get("/api/me/contributions", params={"since": since_iso}, timeout=10).json()
    check("④bob 的 /api/me/contributions.total_created 只反映 bob 自己（seed=2）",
          bob_contrib.get("total_created") == 2 and bob_contrib.get("username") == "bob_e2e",
          f"bob_contrib={bob_contrib}")

    # ── ④alice 带 ?username=bob_e2e 查询越权：服务端忽略 query，仍返回 alice 自己 ──
    spoof = alice_api.get(
        "/api/me/contributions", params={"since": since_iso, "username": "bob_e2e"}, timeout=10
    ).json()
    check("④query 越权被忽略：alice 带 ?username=bob_e2e 仍返回 alice 自己的 username",
          spoof.get("username") == "e2e_engineer", f"spoof={spoof}")
    check("④query 越权被忽略：alice 带 ?username=bob_e2e 的 total_created 仍是 alice 自己的数（非 bob 的 2）",
          spoof.get("total_created") == api_contrib.get("total_created"),
          f"spoof_total={spoof.get('total_created')} alice_total={api_contrib.get('total_created')}")

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'BATCH C REWARDS ACCEPTANCE ALL GREEN' if not failed else 'BATCH C REWARDS ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
