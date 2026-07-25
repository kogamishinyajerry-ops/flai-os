"""M11-B1 真鉴权 UI 验收（ADR-0019 验收标准 7）。

覆盖：①未登录首访=登录门+API 401 ②错密码诚实报错（后端 detail 原文上屏）
③正确登录进入+身份上侧栏 ④登出回门+旧会话服务端已废 ⑤会话中途被吊销
（服务端删行模拟过期/停用）→ 任意 API 401 → 门自动重亮（flai:unauthorized 链）。

自包含：tmp 目录自起后端（绝不碰真实 data/）。运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" python frontend/e2e/m11_auth_acceptance.py
"""
from __future__ import annotations

import shutil
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from _artifacts import artifact_dir

DIST = REPO / "frontend" / "dist"
SHOTS = artifact_dir(REPO, "m11-auth-shots")

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m11_auth_"))
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

import httpx

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

from _auth import E2E_PASSWORD, E2E_USERNAME, seed_user  # noqa: E402
from backend.app.storage.db import get_conn  # noqa: E402

seed_user(WORK / "flai_os.db", "验收工程师")

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")

    # ── ① 未登录首访：登录门拦下，且 API 面 default-deny ──
    page.goto(BASE + "/", wait_until="networkidle")
    gate_seen = page.get_by_placeholder("用户名").is_visible()
    api_probe = page.context.request.get(BASE + "/api/agents")
    check("①未登录：登录门拦下 + API 401", gate_seen is True and api_probe.status == 401,
          f"gate={gate_seen} api={api_probe.status}")
    page.screenshot(path=str(SHOTS / "1_login_gate.png"))

    # ── ② 错密码：后端 detail 原文上屏（不粉饰） ──
    page.get_by_placeholder("用户名").fill(E2E_USERNAME)
    page.get_by_placeholder("密码").fill("wrong-password")
    page.locator(".welcome-gate__button").click()
    err = page.locator('[data-test="login-error"]')
    expect(err).to_be_visible(timeout=5000)
    check("②错密码诚实报错", "用户名或密码错误" in err.inner_text(), err.inner_text())
    page.screenshot(path=str(SHOTS / "2_wrong_password.png"))

    # ── ③ 正确登录：进入工作台，身份上侧栏 ──
    page.get_by_placeholder("密码").fill(E2E_PASSWORD)
    page.locator(".welcome-gate__button").click()
    page.wait_for_selector(".welcome-gate", state="detached", timeout=8000)
    sb_identity = page.locator(".sb-identity").inner_text()
    check("③登录进入且身份上侧栏", "验收工程师" in sb_identity, sb_identity)
    page.screenshot(path=str(SHOTS / "3_logged_in.png"))

    # ── ④ 登出：确认框→回登录门；旧 cookie 服务端已废 ──
    cookies = {c["name"]: c["value"] for c in page.context.cookies()}
    old_token = cookies.get("flai_session", "")
    page.locator(".sb-identity").click()
    page.get_by_role("button", name="退出登录").click()
    page.wait_for_selector(".welcome-gate", timeout=8000)
    replay = httpx.get(BASE + "/api/auth/me", headers={"Cookie": f"flai_session={old_token}"})
    check("④登出回门 + 旧会话服务端已废（重放 401）",
          old_token != "" and replay.status_code == 401, f"replay={replay.status_code}")
    page.screenshot(path=str(SHOTS / "4_logged_out.png"))

    # ── ⑤ 会话中途被吊销（服务端删行=停用/过期同路径）→ API 401 → 门自动重亮 ──
    page.get_by_placeholder("用户名").fill(E2E_USERNAME)
    page.get_by_placeholder("密码").fill(E2E_PASSWORD)
    page.locator(".welcome-gate__button").click()
    page.wait_for_selector(".welcome-gate", state="detached", timeout=8000)
    conn = get_conn(WORK / "flai_os.db")
    try:
        conn.execute("DELETE FROM auth_sessions")  # 服务端吊销（非伪造：只删不插）
    finally:
        conn.close()
    page.goto(BASE + "/tasks", wait_until="networkidle")  # 任意 API 调用触发 401
    gate_back = page.wait_for_selector(".welcome-gate", timeout=8000) is not None
    check("⑤会话中途吊销→任意 API 401→登录门自动重亮", gate_back)
    page.screenshot(path=str(SHOTS / "5_session_revoked_gate_back.png"))

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M11 AUTH ACCEPTANCE ALL GREEN' if not failed else 'M11 AUTH ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
