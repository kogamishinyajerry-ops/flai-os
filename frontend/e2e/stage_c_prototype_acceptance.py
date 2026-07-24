"""Stage C 工作台原型 UI 行为验收（SYNTHETIC ONLY）。

自包含：启动 frontend vite dev server（需先 npm ci）+ 真 chromium，
仅访问 /stage-c.html 原型页，不连后端、不打真 LLM、不碰 data/。

断言矩阵（对应工作项验证要求）：
  ① docx / meeting / cfd 三种夹具的 running：工作台可见、glyph 由
     data-motion="true" 驱动、步骤文案禁止虚构百分比；
  ② running / waiting_review / completed / failed / cancelled /
     evidence-missing / permission-denied / unknown / stale 全状态：
     终态、等待、unknown、stale 一律 data-motion="false"；
  ③ completed 不给可信绿：hero data-trust 必须是 terminal 而非 real；
  ④ evidence-missing / unknown / stale fail-closed：缺口卡如实显示原因码；
  ⑤ 1440px 与 1280px：无横向溢出；
  ⑥ prefers-reduced-motion：glyph computed animation-name 为 none；
  ⑦ 键盘：首页 textarea 聚焦输入后 Ctrl/⌘+Enter 提交进入工作台；
  ⑧ 真人签发入口：waiting_review 点击签发后出现 teal 人签徽标（原型演示）。

运行（仓根）：
  cd frontend && npm ci && cd ..
  uv run --no-project --with playwright python frontend/e2e/stage_c_prototype_acceptance.py
截图证据目录由环境变量 STAGE_C_SHOTS 指定，默认写入系统临时目录。
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
PORT = 8621
# 显式绑定 127.0.0.1：本机 vite 默认只绑 IPv6 ::1，会导致健康探测假阴性
BASE = f"http://127.0.0.1:{PORT}"
SHOTS = Path(os.environ.get("STAGE_C_SHOTS", tempfile.mkdtemp(prefix="stage-c-shots-")))

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

if not (FRONTEND / "node_modules").is_dir():
    sys.exit("诚实失败：frontend/node_modules 缺失。先执行 cd frontend && npm ci")


def wait_port(port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    sys.exit(f"诚实失败：vite dev server 端口 {port} 等待超时")


def goto(page, scene: str, state: str):
    page.goto(f"{BASE}/stage-c.html?scene={scene}&state={state}")
    page.wait_for_selector("[data-testid='workbench']")


failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if not ok:
        failures.append(f"{name}: {detail}")


server = subprocess.Popen(
    ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(PORT), "--strictPort"],
    cwd=FRONTEND,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,  # 独立进程组，保证 npm 的子进程 vite 也能被回收
)
try:
    wait_port(PORT)
    urllib.request.urlopen(f"{BASE}/stage-c.html", timeout=10)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - 需要诚实失败信息
            sys.exit(f"诚实失败：chromium 不可用：{exc}\n请先 uv run --no-project --with playwright python -m playwright install chromium")

        page = browser.new_page(viewport={"width": 1440, "height": 900})

        # ① 三场景 running + glyph 映射 + 无虚构百分比
        expected_glyph = {"docx": "rewrite", "meeting": "map", "cfd": "inspect"}
        for scene, glyph in expected_glyph.items():
            goto(page, scene, "running")
            check(
                f"{scene}:running glyph={glyph} 且动画开",
                page.get_attribute("[data-testid='hero'] .hero-glyph", "data-glyph") == glyph
                and page.get_attribute("[data-testid='hero'] .hero-glyph", "data-motion") == "true",
            )
            step = page.text_content("[data-testid='step-label']") or ""
            check(f"{scene}:running 步骤文案无百分比", "%" not in step, step)
            page.screenshot(path=str(SHOTS / f"{scene}-running.png"), full_page=True)

        goto(page, "cfd", "validating")
        check(
            "cfd:validating glyph=guard",
            page.get_attribute("[data-testid='hero'] .hero-glyph", "data-glyph") == "guard",
        )

        # ② 终态与异常状态一律停止动画
        still = {
            "waiting_review": "wait",
            "completed": "render",
            "failed": "failed",
            "cancelled": "cancelled",
            "evidence-missing": "unknown",
            "permission-denied": "failed",
            "unknown": "unknown",
            "stale": "unknown",
        }
        for state, glyph in still.items():
            goto(page, "docx", state)
            motion = page.get_attribute("[data-testid='hero'] .hero-glyph", "data-motion")
            check(f"docx:{state} 动画停止", motion == "false", f"glyph={glyph} motion={motion}")

        # ③ completed 不给可信绿
        goto(page, "docx", "completed")
        trust = page.get_attribute("[data-testid='hero']", "data-trust")
        check("completed hero 信任槽=terminal（非 real 绿）", trust == "terminal", trust or "")
        page.screenshot(path=str(SHOTS / "docx-completed.png"), full_page=True)

        # ④ fail-closed 缺口卡
        for state, reason in [
            ("evidence-missing", "observation_invalid"),
            ("unknown", "observation_missing"),
            ("stale", "observation_stale"),
        ]:
            goto(page, "meeting", state)
            gap = page.locator("[data-testid='gap-card']")
            check(f"meeting:{state} 缺口卡可见", gap.is_visible())
            check(f"meeting:{state} 原因码 {reason}", reason in (gap.text_content() or ""))
            page.screenshot(path=str(SHOTS / f"meeting-{state}.png"), full_page=True)

        goto(page, "meeting", "permission-denied")
        check(
            "permission-denied 信任槽=fail 且缺口可见",
            page.get_attribute("[data-testid='hero']", "data-trust") == "fail"
            and page.locator("[data-testid='gap-card']").is_visible(),
        )

        # ⑤ 1440 / 1280 无横向溢出
        for width in (1440, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            goto(page, "cfd", "running")
            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            check(f"{width}px 无横向溢出", not overflow)

        # ⑥ reduced motion 停动画
        page.emulate_media(reduced_motion="reduce")
        goto(page, "docx", "running")
        anim = page.eval_on_selector(
            "[data-testid='hero'] .hero-glyph .g-dash",
            "el => getComputedStyle(el).animationName",
        )
        check("reduced-motion 下 glyph 动画为 none", anim == "none", anim)
        page.emulate_media(reduced_motion="no-preference")

        # ⑦ 键盘提交：首页 → 工作台
        page.set_viewport_size({"width": 1440, "height": 900})
        page.goto(f"{BASE}/stage-c.html")
        page.wait_for_selector("[data-testid='home']")
        page.fill("[data-testid='composer'] textarea", "整理本周记录成周报")
        page.press("[data-testid='composer'] textarea", "Control+Enter")
        page.wait_for_selector("[data-testid='workbench']")
        check(
            "键盘 Ctrl+Enter 提交进入工作台且动画开",
            page.get_attribute("[data-testid='hero'] .hero-glyph", "data-motion") == "true",
        )
        page.screenshot(path=str(SHOTS / "home-submit.png"), full_page=True)

        # ⑧ 真人签发入口（原型演示）
        goto(page, "docx", "waiting_review")
        check("waiting_review 交付区可见", page.locator("[data-testid='delivery']").is_visible())
        page.click("[data-testid='sign-button']")
        check(
            "签发后出现 teal 人签徽标",
            page.locator("[data-testid='signed-badge']").is_visible()
            and page.get_attribute("[data-testid='hero']", "data-trust") == "sign",
        )
        page.screenshot(path=str(SHOTS / "docx-signed.png"), full_page=True)

        browser.close()
finally:
    try:
        os.killpg(server.pid, 15)
    except (ProcessLookupError, PermissionError):
        server.terminate()
    try:
        server.wait(timeout=10)
    except subprocess.TimeoutExpired:
        server.kill()

print(f"\n截图证据目录: {SHOTS}")
if failures:
    print(f"\n{len(failures)} 条断言失败：")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print("\n全部断言通过（仅证明外网合成原型 UI 行为，不证明内网已部署或 REAL）。")
