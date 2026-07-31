"""轻量 UI 验收台浏览器回归。

自包含：启动真实 Vite 开发服务器，不启动后端、不读写真实业务数据。验收台入口
是 development-only，生产构建故意不包含 ui-lab.html，因此本脚本不能复用 dist。

覆盖：
  ① 未知 case fail-closed；
  ② 六个固定镜头、精确 viewport 与桌面布局数值基线；
  ③ opaque-origin iframe + 只读边界阻止网络和主题偏好写入；
  ④ Agent 选择器宽高、单行边界和移动端左右各 12px 的对称贴边；
  ⑤ 流式快照使用真实 generating 标记，正文给固定 composer 留足空间；
  ⑥ 保存待核使用 amber，且发送、附件、Agent 共同锁定；
  ⑦ 375px 无横向溢出。

运行（仓根）：
  uv run --no-project --with playwright python frontend/e2e/ui_lab_acceptance.py

截图落 docs/reviews/ui-lab-shots/，每次重跑覆盖六个固定镜头。
"""
from __future__ import annotations

import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import urlopen

REPO = Path(__file__).resolve().parents[2]
FRONTEND = REPO / "frontend"
SHOTS = REPO / "docs" / "reviews" / "ui-lab-shots"

try:
    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")


def free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


PORT = free_port()
BASE = f"http://127.0.0.1:{PORT}"
NPM = "npm.cmd" if os.name == "nt" else "npm"
server = subprocess.Popen(
    [
        NPM,
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(PORT),
        "--strictPort",
    ],
    cwd=FRONTEND,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.STDOUT,
)

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(
        ("PASS" if ok is True else "FAIL"),
        name,
        ("| " + detail if detail and ok is not True else ""),
    )


def wait_for_server() -> None:
    for _ in range(80):
        if server.poll() is not None:
            sys.exit(f"诚实失败：Vite 提前退出（退出码 {server.returncode}）")
        try:
            with urlopen(BASE + "/ui-lab.html", timeout=0.5) as response:
                if response.status == 200:
                    return
        except Exception:
            time.sleep(0.1)
    sys.exit("诚实失败：Vite 8 秒内未就绪")


def embedded_frame(page, case_id: str):
    expect(page.locator("iframe")).to_have_attribute(
        "src",
        re.compile(rf"case={re.escape(case_id)}"),
    )
    for _ in range(80):
        handle = page.locator("iframe").element_handle()
        frame = handle.content_frame() if handle else None
        if (
            frame
            and f"embed=1" in frame.url
            and f"case={case_id}" in frame.url
        ):
            expect(frame.locator(".guide-page")).to_be_visible()
            return frame
        page.wait_for_timeout(100)
    raise AssertionError(f"找不到已挂载的验收 frame：{case_id}")


def select_case(page, case_id: str, label: str):
    page.locator(".case-button", has_text=label).click()
    frame = embedded_frame(page, case_id)
    if "picker" in case_id:
        expect(frame.locator(".agent-pick")).to_be_visible()
        page.wait_for_timeout(350)
    return frame


def capture(frame, name: str) -> None:
    frame.locator("body").screenshot(
        path=SHOTS / name,
        animations="disabled",
        caret="hide",
    )


try:
    wait_for_server()
    SHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        context = browser.new_context(
            viewport={"width": 1600, "height": 1000},
            color_scheme="light",
            reduced_motion="reduce",
            timezone_id="Asia/Shanghai",
        )
        # 固定问候时段与动画，截图只随 UI 代码变化，不随运行时刻/旋转帧漂移。
        context.add_init_script(
            """(() => {
              const NativeDate = Date;
              const fixedNow = NativeDate.parse('2026-07-31T06:00:00.000Z');
              class FixedDate extends NativeDate {
                constructor(...args) {
                  super(...(args.length ? args : [fixedNow]));
                }
                static now() { return fixedNow; }
              }
              FixedDate.parse = NativeDate.parse;
              FixedDate.UTC = NativeDate.UTC;
              window.Date = FixedDate;
            })()"""
        )
        page = context.new_page()
        api_requests: list[str] = []
        page.on(
            "request",
            lambda request: api_requests.append(request.url)
            if urlparse(request.url).path.startswith("/api/")
            else None,
        )

        # invalid inputs first：拼错场景必须明确停止，不能验收成默认起手页。
        page.goto(BASE + "/ui-lab.html?case=does-not-exist", wait_until="networkidle")
        invalid_body = page.locator("body").inner_text()
        check(
            "未知 case fail-closed",
            "验收已停止" in invalid_body
            and "未知 UI 验收场景：does-not-exist" in invalid_body
            and page.locator("iframe").count() == 0,
            invalid_body[:240],
        )

        page.goto(BASE + "/ui-lab.html", wait_until="networkidle")
        check(
            "固定六镜头与三项检查点",
            page.locator(".case-button").count() == 6
            and page.locator(".review-strip li").count() == 3,
        )

        frame = embedded_frame(page, "landing-desktop")
        viewport = frame.evaluate("() => ({ width: innerWidth, height: innerHeight })")
        sandbox = page.locator("iframe").get_attribute("sandbox") or ""
        boundary = frame.evaluate(
            "() => window.__FLAI_UI_ACCEPTANCE_BOUNDARY__ || null"
        )
        isolation = frame.evaluate(
            """() => {
              const probe = expression => {
                try {
                  expression();
                  return 'accessible';
                } catch (error) {
                  return error.name;
                }
              };
              return {
                origin: self.origin,
                localStorage: probe(() => localStorage.getItem('flai_theme_mode')),
                parentDocument: probe(() => parent.document.body),
              };
            }"""
        )
        check(
            "桌面镜头 1440×900 且 opaque 只读边界已安装",
            viewport == {"width": 1440, "height": 900}
            and sandbox.strip() == "allow-scripts"
            and boundary is not None
            and boundary.get("mode") == "read-only",
            (
                f"viewport={viewport} sandbox={sandbox!r} "
                f"boundary={boundary} isolation={isolation}"
            ),
        )
        check(
            "iframe 与共享存储、父文档确实隔离",
            isolation == {
                "origin": "null",
                "localStorage": "SecurityError",
                "parentDocument": "SecurityError",
            },
            str(isolation),
        )

        landing_signature = frame.evaluate(
            """() => {
              const rect = selector =>
                document.querySelector(selector).getBoundingClientRect();
              const cards = [...document.querySelectorAll('.intent-card')];
              return {
                sidebarWidth: rect('.sidebar').width,
                guideWidth: rect('.guide-page').width,
                heroTitlePx: parseFloat(
                  getComputedStyle(document.querySelector('.hero-title')).fontSize
                ),
                intentCount: cards.length,
                intentRows: new Set(cards.map(card =>
                  Math.round(card.getBoundingClientRect().top)
                )).size,
                intentCardPx: Math.max(...cards.map(card =>
                  card.getBoundingClientRect().height
                )),
                composerWidth: rect('.composer-shell').width,
                iconButtonPx: rect('.icon-btn').height,
              };
            }"""
        )
        check(
            "桌面起手页布局数值基线",
            abs(landing_signature["sidebarWidth"] - 264) <= 0.5
            and abs(landing_signature["guideWidth"] - 784) <= 0.5
            and landing_signature["heroTitlePx"] == 26
            and landing_signature["intentCount"] == 4
            and landing_signature["intentRows"] == 1
            and landing_signature["intentCardPx"] <= 44
            and abs(landing_signature["composerWidth"] - 784) <= 0.5
            and landing_signature["iconButtonPx"] == 36,
            str(landing_signature),
        )
        capture(frame, "landing-desktop.png")

        page.evaluate(
            "() => localStorage.setItem('flai_theme_mode', 'ui-lab-sentinel')"
        )
        before_api_count = len(api_requests)
        fetch_blocked = False
        try:
            frame.evaluate("() => fetch('/api/health')")
        except PlaywrightError as error:
            fetch_blocked = "已阻止 fetch" in str(error)
        frame.locator(".sb-theme").click()
        stored_theme = page.evaluate(
            "() => localStorage.getItem('flai_theme_mode')"
        )
        check(
            "网络与真实主题偏好均未被验收 iframe 污染",
            fetch_blocked
            and len(api_requests) == before_api_count
            and stored_theme == "ui-lab-sentinel",
            (
                f"fetch_blocked={fetch_blocked} "
                f"api_delta={len(api_requests) - before_api_count} "
                f"stored_theme={stored_theme!r}"
            ),
        )

        frame = select_case(page, "picker-desktop", "桌面 · Agent 选择器")
        picker_metrics = frame.locator(".agent-pick").evaluate(
            """element => {
              const rect = element.getBoundingClientRect();
              const details = [...element.querySelectorAll('.ap-detail')];
              const popperStyle = getComputedStyle(element.closest('.el-popper'));
              return {
                width: rect.width,
                height: rect.height,
                rows: element.querySelectorAll('.ap-item').length,
                details: details.length,
                opacity: parseFloat(popperStyle.opacity),
                background: popperStyle.backgroundColor,
                oneLine: details.every(item =>
                  item.scrollHeight <= item.clientHeight + 1 &&
                  getComputedStyle(item).whiteSpace === 'nowrap'
                ),
              };
            }"""
        )
        check(
            "桌面 Agent 选择器紧凑且每项仅一行边界",
            318 <= picker_metrics["width"] <= 322
            and picker_metrics["height"] <= 390
            and picker_metrics["rows"] == 4
            and picker_metrics["details"] == picker_metrics["rows"]
            and picker_metrics["opacity"] == 1
            and picker_metrics["background"] not in ("", "rgba(0, 0, 0, 0)")
            and picker_metrics["oneLine"] is True,
            str(picker_metrics),
        )
        capture(frame, "picker-desktop.png")

        frame = select_case(page, "streaming-desktop", "桌面 · 流式中")
        streaming_metrics = frame.evaluate(
            """() => {
              const composer = document.querySelector('.composer-fixed');
              const page = document.querySelector('.guide-page');
              const mark = document.querySelector(
                '.bubble-row.assistant .flai-bloom.is-generating'
              );
              return {
                hasGeneratingMark: Boolean(mark),
                pagePaddingBottom: parseFloat(getComputedStyle(page).paddingBottom),
                composerHeight: composer.getBoundingClientRect().height,
                assistantStreaming: Boolean(
                  document.querySelector('.bubble-row.assistant .ai-lead')
                ),
              };
            }"""
        )
        check(
            "流式快照用 generating 标记且 composer 不遮正文",
            streaming_metrics["hasGeneratingMark"] is True
            and streaming_metrics["assistantStreaming"] is True
            and streaming_metrics["pagePaddingBottom"]
            >= streaming_metrics["composerHeight"],
            str(streaming_metrics),
        )
        capture(frame, "streaming-desktop.png")

        frame = select_case(
            page,
            "persistence-unknown-desktop",
            "桌面 · 保存待核",
        )
        persistence = frame.evaluate(
            """() => {
              const notice = document.querySelector(
                '.stream-interrupted.is-unknown'
              );
              const rootStyle = getComputedStyle(document.documentElement);
              const noticeStyle = getComputedStyle(notice);
              const strongStyle = getComputedStyle(notice.querySelector('strong'));
              const probe = document.createElement('span');
              probe.style.color = rootStyle.getPropertyValue('--trust-pending');
              document.body.append(probe);
              const pending = getComputedStyle(probe).color;
              probe.remove();
              return {
                pendingToken: rootStyle.getPropertyValue(
                  '--trust-pending'
                ).trim().toLowerCase(),
                pending,
                border: noticeStyle.borderLeftColor,
                strong: strongStyle.color,
                background: noticeStyle.backgroundColor,
                sendDisabled: document.querySelector('.send-btn').disabled,
                attachDisabled: document.querySelector(
                  '.composer-attach .icon-btn'
                ).disabled,
                agentDisabled: document.querySelector(
                  '[aria-label="浏览可用 Agent"]'
                ).disabled,
                inputDisabled: document.querySelector(
                  '.composer-input textarea'
                ).disabled,
                hasReconcile: Boolean(
                  document.querySelector('.stream-reconcile-btn')
                ),
              };
            }"""
        )
        check(
            "保存待核为 amber，且发送/附件/Agent 共同锁定",
            persistence["pendingToken"] == "#a8761a"
            and persistence["pending"] == persistence["border"]
            and persistence["pending"] == persistence["strong"]
            and persistence["background"] not in ("", "rgba(0, 0, 0, 0)")
            and persistence["sendDisabled"] is True
            and persistence["attachDisabled"] is True
            and persistence["agentDisabled"] is True
            and persistence["inputDisabled"] is True
            and persistence["hasReconcile"] is True,
            str(persistence),
        )
        capture(frame, "persistence-unknown-desktop.png")

        frame = select_case(page, "landing-mobile", "移动端 · 起手页")
        mobile = frame.evaluate(
            """() => ({
              width: innerWidth,
              height: innerHeight,
              scrollWidth: document.documentElement.scrollWidth,
              clientWidth: document.documentElement.clientWidth,
              minTouch: Math.min(
                ...[...document.querySelectorAll(
                  '.intent-card, .send-btn, .icon-btn'
                )].map(item => item.getBoundingClientRect().height)
              ),
              touchCount: document.querySelectorAll(
                '.intent-card, .send-btn, .icon-btn'
              ).length,
            })"""
        )
        check(
            "移动起手页 375×812 无横向溢出",
            mobile["width"] == 375
            and mobile["height"] == 812
            and mobile["scrollWidth"] <= mobile["clientWidth"]
            and mobile["touchCount"] > 0
            and mobile["minTouch"] >= 40,
            str(mobile),
        )
        capture(frame, "landing-mobile.png")

        frame = select_case(page, "picker-mobile", "移动端 · Agent 选择器")
        mobile_picker = frame.locator(".agent-pick").evaluate(
            """element => {
              const rect = element.getBoundingClientRect();
              const popper = element.closest('.el-popper');
              const popperRect = popper.getBoundingClientRect();
              const popperStyle = getComputedStyle(popper);
              return {
                viewport: { width: innerWidth, height: innerHeight },
                left: popperRect.left,
                rightGap: innerWidth - popperRect.right,
                width: popperRect.width,
                height: rect.height,
                opacity: parseFloat(popperStyle.opacity),
                background: popperStyle.backgroundColor,
                scrollMode: getComputedStyle(
                  element.querySelector('.ap-scroll')
                ).overflowY,
                documentFits:
                  document.documentElement.scrollWidth <=
                  document.documentElement.clientWidth,
              };
            }"""
        )
        check(
            "移动 Agent 选择器左右各 12px 对称贴边且内部滚动",
            mobile_picker["viewport"] == {"width": 375, "height": 812}
            and abs(mobile_picker["left"] - 12) <= 0.5
            and abs(mobile_picker["rightGap"] - 12) <= 0.5
            and abs(mobile_picker["width"] - (mobile_picker["viewport"]["width"] - 24)) <= 1
            and mobile_picker["height"] <= 390
            and mobile_picker["opacity"] == 1
            and mobile_picker["background"] not in ("", "rgba(0, 0, 0, 0)")
            and mobile_picker["scrollMode"] == "auto"
            and mobile_picker["documentFits"] is True,
            str(mobile_picker),
        )
        capture(frame, "picker-mobile.png")

        check("验收加载期间未发真实 API 请求", len(api_requests) == 0, str(api_requests))
        browser.close()
finally:
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)

failures = [(name, detail) for name, ok, detail in results if ok is not True]
if failures:
    print("\n失败项：")
    for name, detail in failures:
        print(f"- {name}: {detail}")
    sys.exit(1)

print(f"\nUI 验收台浏览器回归通过；截图：{SHOTS}")
