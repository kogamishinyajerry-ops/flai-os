"""轻量 UI 验收台浏览器回归。

自包含：启动真实 Vite 开发服务器，不启动后端、不读写真实业务数据。验收台入口
是 development-only，生产构建故意不包含 ui-lab.html，因此本脚本不能复用 dist。

覆盖：
  ① 未知 case fail-closed；
  ② 二十个固定镜头、精确 viewport 与桌面布局数值基线；
  ③ opaque-origin iframe + 只读边界阻止网络和主题偏好写入；
  ④ 自动路由摘要默认收敛，Agent/模型/工具依据按需披露；
  ⑤ 流式快照使用真实 fast（高速档）标记，正文给固定 composer 留足空间；
  ⑥ 保存待核使用 amber，且发送、附件、Agent 共同锁定；
  ⑦ completed 单任务的对话轴资产候选与只读决定抽屉；
  ⑧ Asset Builder 单焦点九问、待审桌面/移动与 needs_revision 阻断；
  ⑨ 功能/资产地图默认收起、ready 重读、503 整体停披露；
  ⑩ 375px 无横向溢出。

运行（仓根）：
  uv run --no-project --with playwright python frontend/e2e/ui_lab_acceptance.py

截图落 docs/reviews/ui-lab-shots/，每次重跑覆盖固定镜头与焦点过渡证据。
"""
from __future__ import annotations

import os
import re
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


def cached_headless_shell() -> str | None:
    """Best-effort local fallback when the Python/browser revisions drift."""

    roots = [
        Path.home() / "Library" / "Caches" / "ms-playwright",
        Path.home() / ".cache" / "ms-playwright",
    ]
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        roots.append(Path(local_app_data) / "ms-playwright")
    candidates: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for name in ("chrome-headless-shell", "headless_shell"):
            candidates.extend(
                path
                for path in root.rglob(name)
                if path.is_file() and os.access(path, os.X_OK)
            )
    return str(sorted(set(candidates))[-1]) if candidates else None


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


def embedded_frame(page, case_id: str, ready_selector: str = ".guide-page"):
    expect(page.locator("iframe")).to_have_attribute(
        "src",
        re.compile(rf"case={re.escape(case_id)}"),
    )
    stable_frame = None
    stable_ticks = 0
    stable_ticks_required = 8 if ready_selector != ".guide-page" else 1
    for _ in range(240):
        try:
            handle = page.locator("iframe").element_handle()
            frame = handle.content_frame() if handle else None
            if (
                frame
                and "embed=1" in frame.url
                and f"case={case_id}" in frame.url
                and frame.locator(ready_selector).is_visible()
            ):
                if frame == stable_frame:
                    stable_ticks += 1
                else:
                    stable_frame = frame
                    stable_ticks = 1
                if stable_ticks >= stable_ticks_required:
                    return frame
            else:
                stable_frame = None
                stable_ticks = 0
        except PlaywrightError:
            # Cold Vite dependency optimization may replace the iframe once;
            # reacquire the current frame instead of waiting on a detached one.
            stable_frame = None
            stable_ticks = 0
        page.wait_for_timeout(100)
    raise AssertionError(
        f"找不到已挂载的验收 frame：{case_id}（锚点 {ready_selector}）"
    )


def select_case(page, case_id: str, label: str):
    page.locator(".case-button", has_text=label).click()
    # These surfaces are deliberately split into async chunks.  Await the real
    # acceptance anchor before returning, including a cold Vite transform/reload.
    ready_selector = ".guide-page"
    if case_id.startswith("feature-asset-map-"):
        ready_selector = ".feature-asset-map"
    elif case_id.startswith(("asset-candidate-", "asset-package-")):
        ready_selector = ".asset-candidate-callout"
    elif case_id in {
        "asset-intake-desktop",
        "asset-review-desktop",
        "asset-review-mobile",
        "asset-blocked-mobile",
    }:
        ready_selector = ".asset-builder-drawer"
    frame = embedded_frame(page, case_id, ready_selector)
    if ready_selector == ".asset-builder-drawer":
        page.wait_for_timeout(250)
    return frame


def capture(frame, name: str) -> None:
    frame.locator("body").screenshot(
        path=SHOTS / name,
        animations="disabled",
        caret="hide",
    )


def capture_element(locator, name: str) -> None:
    locator.screenshot(
        path=SHOTS / name,
        animations="disabled",
        caret="hide",
    )


try:
    wait_for_server()
    SHOTS.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser_override = os.environ.get("FLAI_UI_LAB_BROWSER", "").strip()
        if browser_override:
            browser = playwright.chromium.launch(executable_path=browser_override)
        else:
            try:
                browser = playwright.chromium.launch()
            except PlaywrightError as error:
                # 本地 Playwright Python 包与已缓存 Chromium 修订可能短暂错位；
                # 先复用已安装 headless shell，再退到系统 Chrome。其他失败继续抛出。
                if "Executable doesn't exist" not in str(error):
                    raise
                cached_browser = cached_headless_shell()
                browser = (
                    playwright.chromium.launch(executable_path=cached_browser)
                    if cached_browser
                    else playwright.chromium.launch(channel="chrome")
                )
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
        lazy_component_requests: list[str] = []
        page.on(
            "request",
            lambda request: api_requests.append(request.url)
            if urlparse(request.url).path.startswith("/api/")
            else None,
        )
        page.on(
            "request",
            lambda request: lazy_component_requests.append(
                Path(urlparse(request.url).path).name
            )
            if Path(urlparse(request.url).path).name
            in {"AssetCandidateCallout.vue", "FeatureAssetMapBody.vue"}
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
            "固定二十镜头与逐项检查点",
            page.locator(".case-button").count() == 20
            and page.locator(".review-strip li").count() >= 3,
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
              const send = document.querySelector('.send-btn');
              const tokenProbe = document.createElement('span');
              tokenProbe.style.background = 'var(--paper-rail)';
              tokenProbe.style.color = 'var(--ink-faint)';
              document.body.append(tokenProbe);
              const sendStyle = getComputedStyle(send);
              const tokenStyle = getComputedStyle(tokenProbe);
              const sendSurface = sendStyle.backgroundColor;
              const sendInk = sendStyle.color;
              const neutralSurface = tokenStyle.backgroundColor;
              const faintInk = tokenStyle.color;
              tokenProbe.remove();
              return {
                sidebarWidth: rect('.sidebar').width,
                guideWidth: rect('.guide-page').width,
                guideMainWidth: rect('.guide-main').width,
                heroTitlePx: parseFloat(
                  getComputedStyle(document.querySelector('.hero-title')).fontSize
                ),
                composerWidth: rect('.composer-shell').width,
                iconButtonPx: rect('.icon-btn').height,
                textInputs: document.querySelectorAll(
                  '.composer-input textarea'
                ).length,
                attachmentInputs: document.querySelectorAll(
                  '.composer-attach input[type="file"]'
                ).length,
                otherEditable: document.querySelectorAll(
                  '.guide-page input:not([type="file"]), .guide-page select, '
                  + '.guide-page form, .guide-page [contenteditable="true"]'
                ).length,
                intentCount: document.querySelectorAll('.intent-card').length,
                contextRails: document.querySelectorAll('.guide-context-rail').length,
                agentPickers: document.querySelectorAll(
                  '[aria-label="浏览可用 Agent"]'
                ).length,
                sendDisabled: send.disabled,
                sendSurface,
                sendInk,
                neutralSurface,
                faintInk,
                promise: document.querySelector('.hero-routing-promise')?.innerText || '',
                humanBoundaryCount: (
                  document.body.innerText.match(/开始与放行由你确认/g) || []
                ).length,
              };
            }"""
        )
        check(
            "桌面起手页只有一个文字/附件入口且无手工路由控件",
            abs(landing_signature["sidebarWidth"] - 264) <= 0.5
            and abs(landing_signature["guideWidth"] - 784) <= 0.5
            and abs(landing_signature["guideMainWidth"] - 784) <= 0.5
            and landing_signature["heroTitlePx"] == 26
            and abs(landing_signature["composerWidth"] - 784) <= 0.5
            and landing_signature["iconButtonPx"] == 36
            and landing_signature["textInputs"] == 1
            and landing_signature["attachmentInputs"] == 1
            and landing_signature["otherEditable"] == 0
            and landing_signature["intentCount"] == 0
            and landing_signature["contextRails"] == 0
            and landing_signature["agentPickers"] == 0
            and landing_signature["sendDisabled"] is True
            and landing_signature["sendSurface"] == landing_signature["neutralSurface"]
            and landing_signature["sendInk"] == landing_signature["faintInk"]
            and landing_signature["humanBoundaryCount"] == 1
            and "系统会在后台安排所需能力" in landing_signature["promise"],
            str(landing_signature),
        )
        check(
            "起手页未请求候选卡或折叠地图正文异步模块",
            lazy_component_requests == [],
            str(lazy_component_requests),
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

        frame = select_case(
            page,
            "routing-desktop",
            "桌面 · 自动路由待确认",
        )
        route_disclosure = frame.locator(".route-disclosure")
        route_before = frame.evaluate(
            """() => ({
              textInputs: document.querySelectorAll('textarea').length,
              attachmentInputs: document.querySelectorAll('input[type="file"]').length,
              allInputs: document.querySelectorAll('input').length,
              otherEditable: document.querySelectorAll(
                '.guide-page input:not([type="file"]), .guide-page select, '
                + '.guide-page form, .guide-page [contenteditable="true"]'
              ).length,
              manualAgentButtons: document.querySelectorAll(
                '[aria-label="浏览可用 Agent"]'
              ).length,
              routeOpen: document.querySelector('.route-disclosure').open,
              routeRowsVisible: [...document.querySelectorAll('.agent-card')].some(
                item => item.getClientRects().length > 0
              ),
              summaryLiveRegions: document.querySelectorAll('.route-summary[aria-live]').length,
              stateLiveRegions: document.querySelectorAll('.route-summary-state[aria-live="polite"]').length,
              primaryActions: [...document.querySelectorAll('.plan-foot button')]
                .filter(item => item.getClientRects().length > 0)
                .map(item => item.innerText.trim()),
            })"""
        )
        check(
            "自动路由默认只显示摘要与一个人工开工动作",
            route_before["textInputs"] == 1
            and route_before["attachmentInputs"] == 1
            and route_before["otherEditable"] == 0
            and route_before["manualAgentButtons"] == 0
            and route_before["routeOpen"] is False
            and route_before["routeRowsVisible"] is False
            and route_before["summaryLiveRegions"] == 0
            and route_before["stateLiveRegions"] == 1
            and route_before["primaryActions"] == ["按方案开始"],
            str(route_before),
        )
        route_disclosure.locator("summary").click()
        expect(route_disclosure).to_have_attribute("open", "")
        route_after = route_disclosure.evaluate(
            """element => ({
              rows: element.querySelectorAll('.agent-card').length,
              reasonVisible: element.innerText.includes('任务首先需要结构化检查开算条件'),
              summaryText: element.querySelector('summary').innerText.trim(),
              rosterText: element.querySelector('.roster-label').innerText.trim(),
              materialChips: [...element.querySelectorAll('.plan-material-chip')]
                .map(item => item.innerText.trim()),
              ignoredNarrated: element.innerText.includes('系统已明确忽略，不会静默带入'),
              noFormControls: element.querySelectorAll(
                'input, textarea, select, form, [contenteditable="true"]'
              ).length === 0,
            })"""
        )
        check(
            "路由依据可按需展开且仍无参数表或手工选择",
            route_after == {
                "rows": 2,
                "reasonVisible": True,
                "summaryText": "查看路由依据与边界",
                "rosterText": "成员 · 2",
                "materialChips": ["稳态算例输入表.xlsx", "旧版背景说明.pdf"],
                "ignoredNarrated": True,
                "noFormControls": True,
            },
            str(route_after),
        )
        capture(frame, "routing-desktop.png")

        frame = select_case(page, "streaming-desktop", "桌面 · 流式中")
        streaming_metrics = frame.evaluate(
            """() => {
              const composer = document.querySelector('.composer-fixed');
              const page = document.querySelector('.guide-page');
              const mark = document.querySelector(
                '.bubble-row.assistant .flai-bloom.is-fast'
              );
              return {
                hasFastMark: Boolean(mark),
                pagePaddingBottom: parseFloat(getComputedStyle(page).paddingBottom),
                composerHeight: composer.getBoundingClientRect().height,
                assistantStreaming: Boolean(
                  document.querySelector('.bubble-row.assistant .ai-lead')
                ),
              };
            }"""
        )
        check(
            "流式快照用高速档（fast）标记且 composer 不遮正文",
            streaming_metrics["hasFastMark"] is True
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
            "保存待核为 amber，且文字/附件入口共同锁定",
            persistence["pendingToken"] == "#a8761a"
            and persistence["pending"] == persistence["border"]
            and persistence["pending"] == persistence["strong"]
            and persistence["background"] not in ("", "rgba(0, 0, 0, 0)")
            and persistence["sendDisabled"] is True
            and persistence["attachDisabled"] is True
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
                  '.send-btn, .icon-btn'
                )].map(item => item.getBoundingClientRect().height)
              ),
              touchCount: document.querySelectorAll(
                '.send-btn, .icon-btn'
              ).length,
              intentCount: document.querySelectorAll('.intent-card').length,
              manualAgentButtons: document.querySelectorAll(
                '[aria-label="浏览可用 Agent"]'
              ).length,
              textInputs: document.querySelectorAll('.guide-page textarea').length,
              attachmentInputs: document.querySelectorAll(
                '.guide-page input[type="file"]'
              ).length,
              otherEditable: document.querySelectorAll(
                '.guide-page input:not([type="file"]), .guide-page select, '
                + '.guide-page form, .guide-page [contenteditable="true"]'
              ).length,
            })"""
        )
        check(
            "移动起手页 375×812 无横向溢出",
            mobile["width"] == 375
            and mobile["height"] == 812
            and mobile["scrollWidth"] <= mobile["clientWidth"]
            and mobile["touchCount"] > 0
            and mobile["minTouch"] >= 44
            and mobile["intentCount"] == 0
            and mobile["manualAgentButtons"] == 0
            and mobile["textInputs"] == 1
            and mobile["attachmentInputs"] == 1
            and mobile["otherEditable"] == 0,
            str(mobile),
        )
        capture(frame, "landing-mobile.png")

        frame = select_case(
            page,
            "routing-mobile",
            "移动端 · 自动路由待确认",
        )
        mobile_route = frame.evaluate(
            """() => {
              const disclosure = document.querySelector('.route-disclosure');
              const summary = disclosure.querySelector('summary');
              const primary = document.querySelector('.plan-foot .open-plan-btn');
              return {
                viewport: { width: innerWidth, height: innerHeight },
                documentFits:
                  document.documentElement.scrollWidth <=
                  document.documentElement.clientWidth,
                routeOpen: disclosure.open,
                summaryTouch: summary.getBoundingClientRect().height,
                primaryTouch: primary.getBoundingClientRect().height,
                textInputs: document.querySelectorAll('.composer-input textarea').length,
                attachmentInputs: document.querySelectorAll(
                  '.composer-attach input[type="file"]'
                ).length,
                otherEditable: document.querySelectorAll(
                  '.guide-page input:not([type="file"]), .guide-page select, '
                  + '.guide-page form, .guide-page [contenteditable="true"]'
                ).length,
                manualAgentButtons: document.querySelectorAll(
                  '[aria-label="浏览可用 Agent"]'
                ).length,
              };
            }"""
        )
        check(
            "移动自动路由默认折叠、单一输入且无横向溢出",
            mobile_route["viewport"] == {"width": 375, "height": 812}
            and mobile_route["documentFits"] is True
            and mobile_route["routeOpen"] is False
            and mobile_route["summaryTouch"] >= 44
            and mobile_route["primaryTouch"] >= 44
            and mobile_route["textInputs"] == 1
            and mobile_route["attachmentInputs"] == 1
            and mobile_route["otherEditable"] == 0
            and mobile_route["manualAgentButtons"] == 0,
            str(mobile_route),
        )
        frame.locator(".route-disclosure summary").click()
        mobile_route_expanded = frame.evaluate(
            """() => ({
              documentFits:
                document.documentElement.scrollWidth <=
                document.documentElement.clientWidth,
              rows: document.querySelectorAll('.route-disclosure .agent-card').length,
            })"""
        )
        check(
            "移动路由依据展开后仍无横向溢出",
            mobile_route_expanded == {"documentFits": True, "rows": 2},
            str(mobile_route_expanded),
        )
        capture(frame, "routing-mobile.png")

        map_api_before = len(api_requests)
        map_body_requests_before = lazy_component_requests.count(
            "FeatureAssetMapBody.vue"
        )
        frame = select_case(
            page,
            "feature-asset-map-closed-desktop",
            "桌面 · 功能与资产地图默认收起",
        )
        map_details = frame.locator(".feature-asset-map details")
        map_closed = map_details.evaluate(
            """element => ({
              open: element.open,
              cards: element.querySelectorAll('.capability-card, .asset-card').length,
              refreshActions: [...element.querySelectorAll('button')]
                .filter(item => item.innerText.trim() === '重新读取').length,
              summary: element.querySelector('summary').innerText,
            })"""
        )
        check(
            "功能与资产地图默认收起且未提前读取",
            map_closed == {
                "open": False,
                "cards": 0,
                "refreshActions": 0,
                "summary": map_closed["summary"],
            }
            and "只读披露" in map_closed["summary"]
            and len(api_requests) == map_api_before
            and lazy_component_requests.count("FeatureAssetMapBody.vue")
            == map_body_requests_before
            and lazy_component_requests.count("AssetCandidateCallout.vue") == 0,
            str(map_closed),
        )
        capture(frame, "feature-asset-map-closed-desktop.png")

        frame = select_case(
            page,
            "feature-asset-map-ready-desktop",
            "桌面 · 功能与资产地图已展开",
        )
        map_details = frame.locator(".feature-asset-map details")
        map_body_requests_before_open = lazy_component_requests.count(
            "FeatureAssetMapBody.vue"
        )
        map_details.locator("summary").click()
        expect(map_details.locator(".map-metrics")).to_be_visible()
        map_ready = map_details.evaluate(
            """element => ({
              open: element.open,
              metrics: [...element.querySelectorAll('.map-metrics b')]
                .map(item => item.innerText.trim()),
              capabilities: element.querySelectorAll('.capability-card').length,
              assets: element.querySelectorAll('.asset-card').length,
              signedSteps: element.querySelectorAll('.asset-card .is-signed').length,
              unformedSteps: element.querySelectorAll('.asset-card .is-unformed').length,
              boundary: element.querySelector('.map-boundary')?.innerText || '',
              buttons: [...element.querySelectorAll('button')]
                .map(item => item.innerText.trim()),
              forbiddenControls: element.querySelectorAll(
                'input, textarea, select, form, [contenteditable="true"]'
              ).length,
            })"""
        )
        check(
            "展开地图只显示 owner 冷读快照、真实人审与未形成阶梯",
            map_ready == {
                "open": True,
                "metrics": ["2", "1", "1", "1"],
                "capabilities": 2,
                "assets": 1,
                "signedSteps": 3,
                "unformedSteps": 2,
                "boundary": map_ready["boundary"],
                "buttons": ["重新读取"],
                "forbiddenControls": 0,
            }
            and "当前读取快照" in map_ready["boundary"]
            and "仅当前账号" in map_ready["boundary"]
            and "不执行 · 不注册 · 不晋级" in map_ready["boundary"]
            and len(api_requests) == map_api_before
            and lazy_component_requests.count("FeatureAssetMapBody.vue")
            > map_body_requests_before_open
            and lazy_component_requests.count("AssetCandidateCallout.vue") == 0,
            str(map_ready),
        )
        map_details.get_by_role("button", name="重新读取", exact=True).click()
        expect(map_details.locator(".asset-card")).to_have_count(2)
        refreshed_metrics = map_details.locator(".map-metrics b").all_inner_texts()
        check(
            "ready 快照可在同页重新读取新增 Candidate 且不触发真实网络",
            refreshed_metrics == ["2", "2", "1", "1"]
            and map_details.locator(".asset-card .is-pending").count() >= 1
            and len(api_requests) == map_api_before,
            str(refreshed_metrics),
        )
        capture_element(map_details, "feature-asset-map-ready-desktop.png")

        frame = select_case(
            page,
            "feature-asset-map-error-desktop",
            "桌面 · 功能与资产地图停披露",
        )
        map_details = frame.locator(".feature-asset-map details")
        map_details.locator("summary").click()
        expect(map_details.locator(".map-state.is-error")).to_be_visible()
        map_error = map_details.evaluate(
            """element => ({
              alert: element.querySelector('[role="alert"]')?.innerText || '',
              metrics: element.querySelectorAll('.map-metrics').length,
              cards: element.querySelectorAll('.capability-card, .asset-card').length,
              buttons: [...element.querySelectorAll('button')]
                .map(item => item.innerText.trim()),
              forbiddenControls: element.querySelectorAll(
                'input, textarea, select, form, [contenteditable="true"]'
              ).length,
            })"""
        )
        check(
            "来源 503 时地图整体停披露且只保留重新读取",
            "地图暂不可用" in map_error["alert"]
            and "来源完整性核验失败（503）" in map_error["alert"]
            and "未展示任何残缺数据" in map_error["alert"]
            and map_error["metrics"] == 0
            and map_error["cards"] == 0
            and map_error["buttons"] == ["重新读取"]
            and map_error["forbiddenControls"] == 0
            and len(api_requests) == map_api_before,
            str(map_error),
        )
        capture_element(map_details, "feature-asset-map-error-desktop.png")

        frame = select_case(
            page,
            "feature-asset-map-ready-mobile",
            "移动端 · 功能与资产地图已展开",
        )
        map_details = frame.locator(".feature-asset-map details")
        map_details.locator("summary").click()
        expect(map_details.locator(".map-metrics")).to_be_visible()
        map_mobile = map_details.evaluate(
            """element => {
              const refresh = element.querySelector('.map-refresh');
              const capability = element.querySelector('.capability-card');
              return {
                viewport: { width: innerWidth, height: innerHeight },
                documentFits:
                  document.documentElement.scrollWidth <=
                  document.documentElement.clientWidth,
                detailsWidth: element.getBoundingClientRect().width,
                refreshTouch: refresh.getBoundingClientRect().height,
                capabilityWidth: capability.getBoundingClientRect().width,
                bodyWidth: element.querySelector('.map-body').getBoundingClientRect().width,
                metrics: element.querySelectorAll('.map-metrics > div').length,
                forbiddenControls: element.querySelectorAll(
                  'input, textarea, select, form, [contenteditable="true"]'
                ).length,
              };
            }"""
        )
        check(
            "375px 地图单列可扫读、触控目标合格且无横向溢出",
            map_mobile["viewport"] == {"width": 375, "height": 812}
            and map_mobile["documentFits"] is True
            and map_mobile["detailsWidth"] <= 375
            and map_mobile["refreshTouch"] >= 44
            and abs(map_mobile["capabilityWidth"] - (map_mobile["bodyWidth"] - 22)) <= 1
            and map_mobile["metrics"] == 4
            and map_mobile["forbiddenControls"] == 0
            and len(api_requests) == map_api_before,
            str(map_mobile),
        )
        capture_element(map_details, "feature-asset-map-ready-mobile.png")

        candidate_api_before = len(api_requests)
        candidate_module_requests_before = lazy_component_requests.count(
            "AssetCandidateCallout.vue"
        )
        frame = select_case(
            page,
            "asset-candidate-desktop",
            "桌面 · 已完成任务资产候选",
        )
        candidate_callout = frame.locator(".asset-candidate-callout")
        candidate_shell = frame.evaluate(
            """() => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.background = rootStyle.getPropertyValue('--trust-pending');
              document.body.append(probe);
              const pending = getComputedStyle(probe).backgroundColor;
              probe.remove();
              return {
                callouts: document.querySelectorAll('.asset-candidate-callout').length,
                textInputs: document.querySelectorAll('textarea').length,
                attachmentInputs: document.querySelectorAll('input[type="file"]').length,
                allInputs: document.querySelectorAll('input').length,
                forbiddenControls: document.querySelectorAll(
                  '.guide-page form, .guide-page select, .guide-page [role="combobox"], '
                  + '.guide-page [contenteditable="true"]'
                ).length,
                openActions: [...document.querySelectorAll('.candidate-open')]
                  .filter(item => item.innerText.trim() === '查看并决定').length,
                markColor: getComputedStyle(
                  document.querySelector('.asset-candidate-callout .candidate-mark')
                ).backgroundColor,
                pending,
              };
            }"""
        )
        check(
            "completed 单任务只在对话轴长出一张 amber 候选卡",
            candidate_shell["markColor"] == candidate_shell["pending"]
            and {
                key: value
                for key, value in candidate_shell.items()
                if key not in {"markColor", "pending"}
            } == {
                "callouts": 1,
                "textInputs": 1,
                "attachmentInputs": 1,
                "allInputs": 1,
                "forbiddenControls": 0,
                "openActions": 1,
            }
            and lazy_component_requests.count("AssetCandidateCallout.vue")
            > candidate_module_requests_before,
            str(candidate_shell),
        )
        capture(frame, "asset-candidate-desktop.png")

        review_trigger = candidate_callout.get_by_role(
            "button",
            name="查看并决定",
            exact=True,
        )
        review_trigger.click()
        candidate_drawer = frame.locator(".asset-candidate-review")
        expect(candidate_drawer).to_be_visible()
        candidate_review = candidate_drawer.evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = rootStyle.getPropertyValue('--trust-pending');
              document.body.append(probe);
              const pending = getComputedStyle(probe).color;
              probe.remove();
              const actionLabels = [...element.querySelectorAll(
                '.candidate-review-actions button'
              )].map(item => item.innerText.trim());
              const count = label => actionLabels.filter(item => item === label).length;
              return {
                forbiddenControls: element.querySelectorAll(
                  'input, textarea, select, form, [contenteditable="true"]'
                ).length,
                actionCount: actionLabels.length,
                accept: count('接受这个候选'),
                reject: count('本次不保留'),
                download: count('下载待审包'),
                back: count('回到对话'),
                workflowGated: element.innerText.includes('Workflow') &&
                  element.innerText.includes('尚未形成'),
                agentGated: element.innerText.includes('Agent') &&
                  element.innerText.includes('需要通过 Workflow、Agent Package、评测与人工晋级门'),
                stateColor: getComputedStyle(
                  element.querySelector('.candidate-state')
                ).color,
                pending,
              };
            }"""
        )
        check(
            "待审候选用 amber，抽屉只读且四个按钮动作各出现一次",
            candidate_review["stateColor"] == candidate_review["pending"]
            and {
                key: value
                for key, value in candidate_review.items()
                if key not in {"stateColor", "pending"}
            } == {
                "forbiddenControls": 0,
                "actionCount": 4,
                "accept": 1,
                "reject": 1,
                "download": 1,
                "back": 1,
                "workflowGated": True,
                "agentGated": True,
            },
            str(candidate_review),
        )
        capture(frame, "asset-candidate-review-desktop.png")

        candidate_drawer.get_by_role(
            "button",
            name="回到对话",
            exact=True,
        ).click()
        expect(candidate_drawer).not_to_be_visible()
        expect(review_trigger).to_be_focused()
        check(
            "验收候选关闭后焦点回触发按钮且没有网络或真实决定",
            len(api_requests) == candidate_api_before
            and candidate_callout.get_by_role(
                "button",
                name="查看并决定",
                exact=True,
            ).count() == 1,
            str(api_requests[candidate_api_before:]),
        )

        accepted_api_before = len(api_requests)
        frame = select_case(
            page,
            "asset-candidate-accepted-desktop",
            "桌面 · 隔离包待复核",
        )
        accepted_callout = frame.locator(".asset-candidate-callout")
        accepted_shell = accepted_callout.evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.background = rootStyle.getPropertyValue('--trust-pending');
              document.body.append(probe);
              const pending = getComputedStyle(probe).backgroundColor;
              probe.remove();
              return {
                calloutText: element.innerText,
                callouts: document.querySelectorAll('.asset-candidate-callout').length,
                reviewPackageActions: [...element.querySelectorAll('button')]
                  .filter(item => item.innerText.trim() === '复核隔离包').length,
                markColor: getComputedStyle(
                  element.querySelector('.candidate-mark')
                ).backgroundColor,
                pending,
              };
            }"""
        )
        check(
            "Candidate 接受后以 amber 聚焦隔离包复核，不冒充批准成功",
            accepted_shell["callouts"] == 1
            and accepted_shell["reviewPackageActions"] == 1
            and "隔离包待复核" in accepted_shell["calloutText"]
            and accepted_shell["markColor"] == accepted_shell["pending"],
            str(accepted_shell),
        )
        capture(frame, "asset-candidate-accepted-desktop.png")

        accepted_trigger = accepted_callout.get_by_role(
            "button",
            name="复核隔离包",
            exact=True,
        )
        accepted_trigger.click()
        accepted_drawer = frame.locator(".asset-candidate-review")
        expect(accepted_drawer).to_be_visible()
        accepted_review = accepted_drawer.evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = rootStyle.getPropertyValue('--trust-signed');
              document.body.append(probe);
              const signed = getComputedStyle(probe).color;
              probe.style.color = rootStyle.getPropertyValue('--trust-pending');
              const pending = getComputedStyle(probe).color;
              probe.remove();
              const actionLabels = [...element.querySelectorAll(
                '.candidate-review-actions button'
              )].map(item => item.innerText.trim());
              const count = label => actionLabels.filter(item => item === label).length;
              return {
                honesty: element.innerText.includes(
                  '已接受为资产候选，尚未登记、发布或形成 Agent。'
                ),
                packagePending: element.innerText.includes(
                  '隔离包待复核'
                ) && element.innerText.includes(
                  '达到数量门也不会自动形成 Workflow 或 Agent Candidate。'
                ),
                forbiddenControls: element.querySelectorAll(
                  'input, textarea, select, form, [contenteditable="true"]'
                ).length,
                actionCount: actionLabels.length,
                accept: count('接受这个候选'),
                reject: count('本次不保留'),
                approvePackage: count('批准复用'),
                approveDisabled: [...element.querySelectorAll(
                  '.candidate-review-actions button'
                )].find(item => item.innerText.trim() === '批准复用')?.disabled === true,
                rejectPackage: count('本次不批准'),
                reviewBytes: [...element.querySelectorAll('button')]
                  .filter(item => item.innerText.trim() === '读取并审阅真实包内容').length,
                download: count('下载候选记录'),
                back: count('回到对话'),
                stateColor: getComputedStyle(
                  element.querySelector('.candidate-state')
                ).color,
                packageStateColor: getComputedStyle(
                  element.querySelector('.candidate-state.is-package-pending_review')
                ).color,
                signed,
                pending,
              };
            }"""
        )
        check(
            "已接受抽屉保持只读，并只把隔离包复核作为下一层按钮动作",
            accepted_review["stateColor"] == accepted_review["signed"]
            and accepted_review["packageStateColor"] == accepted_review["pending"]
            and {
                key: value
                for key, value in accepted_review.items()
                if key not in {
                    "stateColor",
                    "packageStateColor",
                    "signed",
                    "pending",
                }
            } == {
                "honesty": True,
                "packagePending": True,
                "forbiddenControls": 0,
                "actionCount": 4,
                "accept": 0,
                "reject": 0,
                "approvePackage": 1,
                "approveDisabled": True,
                "rejectPackage": 1,
                "reviewBytes": 1,
                "download": 1,
                "back": 1,
            },
            str(accepted_review),
        )
        accepted_drawer.get_by_role(
            "button",
            name="读取并审阅真实包内容",
            exact=True,
        ).click()
        expect(accepted_drawer.locator(".candidate-package-file")).to_have_count(4)
        expect(
            accepted_drawer.get_by_role("button", name="批准复用", exact=True)
        ).to_be_enabled()
        loaded_package_review = accepted_drawer.evaluate(
            """element => ({
              filePaths: [...element.querySelectorAll('.candidate-package-file h4')]
                .map(item => item.innerText.trim()),
              skillText: element.querySelector('.candidate-package-file pre')?.innerText || '',
              forbiddenControls: element.querySelectorAll(
                'input, textarea, select, form, [contenteditable="true"]'
              ).length,
            })"""
        )
        check(
            "待审包按需展示经核验的四份真实文本，随后才解锁批准",
            loaded_package_review == {
                "filePaths": [
                    "SKILL.md",
                    "references/provenance.json",
                    "references/skill-revision.json",
                    "references/task-pattern-revision.json",
                ],
                "skillText": loaded_package_review["skillText"],
                "forbiddenControls": 0,
            }
            and "name: cfd-inlet-boundary-review"
            in loaded_package_review["skillText"],
            str(loaded_package_review),
        )
        capture(frame, "asset-candidate-accepted-review-desktop.png")
        accepted_drawer.get_by_role(
            "button",
            name="回到对话",
            exact=True,
        ).click()
        expect(accepted_drawer).not_to_be_visible()
        expect(accepted_trigger).to_be_focused()
        check(
            "接受成功态验收不发网络请求",
            len(api_requests) == accepted_api_before,
            str(api_requests[accepted_api_before:]),
        )

        approved_api_before = len(api_requests)
        frame = select_case(
            page,
            "asset-package-approved-desktop",
            "桌面 · 隔离包已批准",
        )
        approved_callout = frame.locator(".asset-candidate-callout")
        approved_shell = approved_callout.evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.background = rootStyle.getPropertyValue('--trust-signed');
              document.body.append(probe);
              const signed = getComputedStyle(probe).backgroundColor;
              probe.remove();
              return {
                text: element.innerText,
                mark: getComputedStyle(element.querySelector('.candidate-mark')).backgroundColor,
                signed,
              };
            }"""
        )
        approved_trigger = approved_callout.get_by_role(
            "button", name="查看记录", exact=True
        )
        approved_trigger.click()
        approved_drawer = frame.locator(".asset-candidate-review")
        expect(approved_drawer).to_be_visible()
        approved_review = approved_drawer.evaluate(
            """element => ({
              packageState: element.querySelector('.candidate-state.is-package-approved')?.innerText,
              decisionActions: [...element.querySelectorAll('.candidate-review-actions button')]
                .filter(item => ['批准复用', '本次不批准'].includes(item.innerText.trim())).length,
              workflowNotFormed: element.innerText.includes('Workflow') &&
                element.innerText.includes('尚未形成'),
              agentNotFormed: element.innerText.includes('Agent') &&
                element.innerText.includes('尚未形成'),
            })"""
        )
        check(
            "包级批准使用 teal 人签态且不生成 Workflow/Agent 或重复决定",
            approved_shell["mark"] == approved_shell["signed"]
            and "自动复用" in approved_shell["text"]
            and approved_review == {
                "packageState": "工程师已批准复用",
                "decisionActions": 0,
                "workflowNotFormed": True,
                "agentNotFormed": True,
            }
            and len(api_requests) == approved_api_before,
            f"shell={approved_shell} drawer={approved_review}",
        )
        approved_drawer.get_by_role("button", name="回到对话", exact=True).click()

        rejected_api_before = len(api_requests)
        frame = select_case(
            page,
            "asset-package-rejected-desktop",
            "桌面 · 隔离包未批准",
        )
        rejected_callout = frame.locator(".asset-candidate-callout")
        rejected_shell = rejected_callout.evaluate(
            """element => {
              const mark = getComputedStyle(element.querySelector('.candidate-mark'));
              return {
                text: element.innerText,
                background: mark.backgroundColor,
                boxShadow: mark.boxShadow,
              };
            }"""
        )
        rejected_trigger = rejected_callout.get_by_role(
            "button", name="查看记录", exact=True
        )
        rejected_trigger.click()
        rejected_drawer = frame.locator(".asset-candidate-review")
        expect(rejected_drawer).to_be_visible()
        rejected_review = rejected_drawer.evaluate(
            """element => ({
              packageState: element.querySelector('.candidate-state.is-package-rejected')?.innerText,
              decisionActions: [...element.querySelectorAll('.candidate-review-actions button')]
                .filter(item => ['批准复用', '本次不批准'].includes(item.innerText.trim())).length,
              recordPreserved: element.innerText.includes('Candidate 与复核记录仍完整保留'),
            })"""
        )
        check(
            "包级拒绝回到中性空心标记，不回落 Candidate teal 或误画失败红",
            rejected_shell["background"] == "rgba(0, 0, 0, 0)"
            and rejected_shell["boxShadow"] != "none"
            and "本次不进入自动复用" in rejected_shell["text"]
            and rejected_review == {
                "packageState": "本次未批准复用",
                "decisionActions": 0,
                "recordPreserved": True,
            }
            and len(api_requests) == rejected_api_before,
            f"shell={rejected_shell} drawer={rejected_review}",
        )
        rejected_drawer.get_by_role("button", name="回到对话", exact=True).click()

        reuse_api_before = len(api_requests)
        frame = select_case(
            page,
            "skill-reuse-desktop",
            "桌面 · 已自动复用方法",
        )
        reuse_dom = frame.locator(".plan-card").evaluate(
            """element => ({
              inlineCount: element.querySelectorAll('.skill-reuse-inline').length,
              inlineText: element.querySelector('.skill-reuse-inline')?.innerText || '',
              disclosureOpen: element.querySelector('.route-disclosure')?.open === true,
              mainActions: [...element.querySelectorAll('.plan-foot button')]
                .filter(item => item.innerText.trim() === '按方案开始').length,
              forbiddenFields: element.querySelectorAll(
                'input, textarea, select, form, [contenteditable="true"]'
              ).length,
              forbiddenPanels: element.querySelectorAll(
                '.skill-reuse-card, .skill-reuse-panel, .skill-reuse-action'
              ).length,
            })"""
        )
        frame.locator(".route-disclosure summary").click()
        reuse_detail = frame.locator(".skill-reuse-detail").inner_text()
        check(
            "已审核 Skill 只在既有方案对话内联与按需披露中复用",
            reuse_dom == {
                "inlineCount": 1,
                "inlineText": "计划复用 · cfd-inlet-boundary-review",
                "disclosureOpen": False,
                "mainActions": 1,
                "forbiddenFields": 0,
                "forbiddenPanels": 0,
            }
            and "已通过包级人工复核" in reuse_detail
            and len(api_requests) == reuse_api_before,
            f"dom={reuse_dom} detail={reuse_detail}",
        )

        invalid_reuse_api_before = len(api_requests)
        frame = select_case(
            page,
            "skill-reuse-invalid-desktop",
            "桌面 · 复用证据待核",
        )
        invalid_reuse_dom = frame.locator(".plan-card").evaluate(
            """element => ({
              amber: element.querySelector('.route-summary-state.is-pending')?.innerText || '',
              openActions: [...element.querySelectorAll('.plan-foot button')]
                .filter(item => item.innerText.trim() === '按方案开始').length,
              recoveryActions: [...element.querySelectorAll('.plan-foot button')]
                .filter(item => item.innerText.includes('继续对话让系统重新安排')).length,
              reuseInline: element.querySelectorAll('.skill-reuse-inline').length,
            })"""
        )
        frame.get_by_role(
            "button",
            name="复用证据待核 · 继续对话让系统重新安排",
            exact=True,
        ).click()
        check(
            "非法复用证据显式 amber 阻断且点击只回主输入，保持零任务 POST",
            "复用证据无法核验，本次禁止开始" in invalid_reuse_dom["amber"]
            and invalid_reuse_dom["openActions"] == 0
            and invalid_reuse_dom["recoveryActions"] == 1
            and invalid_reuse_dom["reuseInline"] == 0
            and len(api_requests) == invalid_reuse_api_before,
            str(invalid_reuse_dom),
        )

        # 决定按钮状态机：隔离挂载真实 AssetCandidateCallout。ready 才可决定；
        # deciding 保持按钮位置稳定但全禁用，并锁住所有关闭出口。组件全程零 API。
        candidate_component_page = context.new_page()
        candidate_component_api_requests: list[str] = []
        candidate_component_page.on(
            "request",
            lambda request: candidate_component_api_requests.append(request.url)
            if urlparse(request.url).path.startswith("/api/")
            else None,
        )
        candidate_component_page.route(
            "**/src/ui-lab/main.js",
            lambda route: route.fulfill(
                content_type="application/javascript",
                body="export {};",
            ),
        )
        candidate_component_page.route(
            f"{BASE}/api/**",
            lambda route: route.abort(),
        )
        candidate_component_page.goto(BASE + "/ui-lab.html", wait_until="networkidle")
        candidate_component_page.evaluate(
            """async () => {
              const [Vue, ElementPlus, zhCn, calloutModule, casesModule] =
                await Promise.all([
                  import('/node_modules/.vite/deps/vue.js'),
                  import('/node_modules/.vite/deps/element-plus.js'),
                  import('/node_modules/.vite/deps/element-plus_es_locale_lang_zh-cn.js'),
                  import('/src/components/AssetCandidateCallout.vue'),
                  import('/src/ui-lab/uiAcceptanceCases.js'),
                ]);
              const fixture = casesModule.getUiAcceptanceCase(
                'asset-candidate-desktop'
              ).guide;
              const state = Vue.reactive({
                candidate: fixture.assetCandidate,
                phase: 'loading',
              });
              window.__FLAI_CANDIDATE_COMPONENT_STATE__ = state;
              window.__FLAI_CANDIDATE_COMPONENT_NEXT_TICK__ = Vue.nextTick;
              const app = Vue.createApp({
                setup() {
                  return () => Vue.h(calloutModule.default, {
                    candidate: state.candidate,
                    phase: state.phase,
                    error: '',
                  });
                },
              });
              app.use(ElementPlus.default, { locale: zhCn.default });
              app.mount('#app');
              await Vue.nextTick();
            }"""
        )
        loading_trigger = candidate_component_page.get_by_role(
            "button",
            name="查看记录",
            exact=True,
        )
        loading_trigger.click()
        component_candidate_drawer = candidate_component_page.locator(
            ".asset-candidate-review"
        )
        expect(component_candidate_drawer).to_be_visible()

        def candidate_component_actions() -> dict[str, int]:
            return component_candidate_drawer.evaluate(
                """element => {
                  const buttons = [...element.querySelectorAll(
                    '.candidate-review-actions button'
                  )];
                  const labels = buttons.map(item => item.innerText.trim());
                  return {
                    accept: labels.filter(text => text === '接受这个候选').length,
                    reject: labels.filter(text => text === '本次不保留').length,
                    download: labels.filter(text => text === '下载待审包').length,
                    back: labels.filter(text => text === '回到对话').length,
                    disabled: buttons.filter(item => item.disabled).length,
                    busy: element.querySelector('.candidate-review-body')
                      ?.getAttribute('aria-busy'),
                    close: element.querySelectorAll('.el-drawer__close-btn').length,
                    forbidden: element.querySelectorAll(
                      'input, textarea, select, form, [contenteditable="true"]'
                    ).length,
                  };
                }"""
            )

        loading_actions = candidate_component_actions()
        candidate_component_page.evaluate(
            """async () => {
              window.__FLAI_CANDIDATE_COMPONENT_STATE__.phase = 'ready';
              await window.__FLAI_CANDIDATE_COMPONENT_NEXT_TICK__();
            }"""
        )
        ready_actions = candidate_component_actions()
        candidate_component_page.evaluate(
            """async () => {
              window.__FLAI_CANDIDATE_COMPONENT_STATE__.phase = 'deciding';
              await window.__FLAI_CANDIDATE_COMPONENT_NEXT_TICK__();
            }"""
        )
        deciding_actions = candidate_component_actions()
        check(
            "候选只在 ready 可决定，deciding 保持稳定位置并锁住关闭动作",
            loading_actions == {
                "accept": 0,
                "reject": 0,
                "download": 1,
                "back": 1,
                "disabled": 0,
                "busy": "false",
                "close": 1,
                "forbidden": 0,
            }
            and ready_actions == {
                "accept": 1,
                "reject": 1,
                "download": 1,
                "back": 1,
                "disabled": 0,
                "busy": "false",
                "close": 1,
                "forbidden": 0,
            }
            and deciding_actions == {
                "accept": 1,
                "reject": 1,
                "download": 1,
                "back": 1,
                "disabled": 4,
                "busy": "true",
                "close": 0,
                "forbidden": 0,
            }
            and candidate_component_api_requests == [],
            (
                f"loading={loading_actions} ready={ready_actions} "
                f"deciding={deciding_actions} api={candidate_component_api_requests}"
            ),
        )
        candidate_component_page.close()

        # 包级决定真实链：挂载生产 Callout + 生产 API helper，用可控 fetch 保持
        # POST 在途，先验 deciding 锁，再放行 approved/rejected 响应观察同一 DOM。
        package_decision_page = context.new_page()
        package_decision_page.route(
            "**/src/ui-lab/main.js",
            lambda route: route.fulfill(
                content_type="application/javascript",
                body="export {};",
            ),
        )
        package_decision_page.goto(BASE + "/ui-lab.html", wait_until="networkidle")
        package_decision_page.evaluate(
            """async () => {
              const [Vue, ElementPlus, zhCn, calloutModule, apiModule, utilsModule, casesModule] =
                await Promise.all([
                  import('/node_modules/.vite/deps/vue.js'),
                  import('/node_modules/.vite/deps/element-plus.js'),
                  import('/node_modules/.vite/deps/element-plus_es_locale_lang_zh-cn.js'),
                  import('/src/components/AssetCandidateCallout.vue'),
                  import('/src/api/assetCandidates.js'),
                  import('/src/utils/assetCandidates.js'),
                  import('/src/ui-lab/uiAcceptanceCases.js'),
                ]);
              const pendingGuide = casesModule.getUiAcceptanceCase(
                'asset-candidate-accepted-desktop'
              ).guide;
              const approvedGuide = casesModule.getUiAcceptanceCase(
                'asset-package-approved-desktop'
              ).guide;
              const rejectedGuide = casesModule.getUiAcceptanceCase(
                'asset-package-rejected-desktop'
              ).guide;
              const verifiedContent = await utilsModule.normalizeSkillPackageReviewContent(
                pendingGuide.skillPackageReviewContent,
                {
                  expectedPackageId: pendingGuide.assetCandidate.skill_package.id,
                  expectedPackageDigest:
                    pendingGuide.assetCandidate.skill_package.package_digest,
                  expectedFiles: pendingGuide.assetCandidate.skill_package.files,
                },
              );
              const state = Vue.reactive({
                candidate: structuredClone(pendingGuide.assetCandidate),
                phase: 'ready',
                error: '',
                reviewContent: verifiedContent,
                reviewPhase: 'ready',
              });
              const requests = [];
              let resolveDecision = null;
              const pendingPackage = structuredClone(
                pendingGuide.assetCandidate.skill_package
              );
              const responses = {
                approve: structuredClone(
                  approvedGuide.assetCandidate.skill_package
                ),
                reject: structuredClone(
                  rejectedGuide.assetCandidate.skill_package
                ),
              };
              globalThis.fetch = (path, init = {}) => {
                const body = JSON.parse(init.body || '{}');
                requests.push({ path, method: init.method || 'GET', body });
                return new Promise(resolve => {
                  resolveDecision = () => resolve(new Response(
                    JSON.stringify(responses[body.action]),
                    { status: 200, headers: { 'Content-Type': 'application/json' } },
                  ));
                });
              };
              async function decidePackage(action) {
                state.phase = 'deciding';
                state.error = '';
                try {
                  const decided = await apiModule.decideSkillPackage(
                    state.candidate.skill_package,
                    action,
                  );
                  state.candidate = { ...state.candidate, skill_package: decided };
                  state.phase = 'ready';
                } catch (error) {
                  state.error = error?.message || 'decision failed';
                  state.phase = 'reconcile_required';
                }
              }
              window.__FLAI_PACKAGE_DECISION__ = {
                state,
                requests,
                pendingPackage,
                decidePackage,
                resetPending: async () => {
                  state.candidate = {
                    ...state.candidate,
                    skill_package: structuredClone(pendingPackage),
                  };
                  state.phase = 'ready';
                  state.error = '';
                  await Vue.nextTick();
                },
                resolve: () => resolveDecision?.(),
                nextTick: Vue.nextTick,
              };
              const app = Vue.createApp({
                setup() {
                  return () => Vue.h(calloutModule.default, {
                    candidate: state.candidate,
                    phase: state.phase,
                    error: state.error,
                    packageReviewContent: state.reviewContent,
                    packageReviewPhase: state.reviewPhase,
                    packageReviewError: '',
                    onDecidePackage: decidePackage,
                  });
                },
              });
              app.use(ElementPlus.default, { locale: zhCn.default });
              app.mount('#app');
              await Vue.nextTick();
            }"""
        )
        package_decision_page.get_by_role(
            "button", name="复核隔离包", exact=True
        ).click()
        package_drawer = package_decision_page.locator(".asset-candidate-review")
        expect(package_drawer).to_be_visible()
        expect(
            package_drawer.get_by_role("button", name="批准复用", exact=True)
        ).to_be_enabled()
        package_drawer.get_by_role(
            "button", name="批准复用", exact=True
        ).click()
        expect(package_drawer.locator(".candidate-review-body")).to_have_attribute(
            "aria-busy", "true"
        )
        approve_pending = package_drawer.evaluate(
            """element => {
              const footer = [...element.querySelectorAll(
                '.candidate-review-actions button'
              )];
              const evidence = element.querySelector('.candidate-evidence-toggle');
              evidence?.click();
              return {
                footerLabels: footer.map(item => item.innerText.trim()),
                disabledFooter: footer.filter(item => item.disabled).length,
                evidenceDisabled: evidence?.disabled === true,
                evidenceExpanded: evidence?.getAttribute('aria-expanded'),
                contentDisabled:
                  element.querySelector('.candidate-package-content-toggle')?.disabled === true,
                close: element.querySelectorAll('.el-drawer__close-btn').length,
              };
            }"""
        )
        approve_request = package_decision_page.evaluate(
            "() => window.__FLAI_PACKAGE_DECISION__.requests[0]"
        )
        check(
            "包级批准发出精确 CAS POST，deciding 锁住底栏、证据、内容与关闭出口",
            approve_request == {
                "path": "/api/skill-packages/skill_package_919191919191919191919191/decision",
                "method": "POST",
                "body": {
                    "schema_version": "skill_package_decision_request.v1",
                    "action": "approve",
                    "expected_package_digest": f"sha256:{'9' * 64}",
                },
            }
            and approve_pending == {
                "footerLabels": [
                    "正在记录决定…",
                    "本次不批准",
                    "下载候选记录",
                    "回到对话",
                ],
                "disabledFooter": 4,
                "evidenceDisabled": True,
                "evidenceExpanded": "false",
                "contentDisabled": True,
                "close": 0,
            },
            f"request={approve_request} deciding={approve_pending}",
        )
        package_decision_page.evaluate(
            "() => window.__FLAI_PACKAGE_DECISION__.resolve()"
        )
        expect(
            package_drawer.locator(".candidate-state.is-package-approved")
        ).to_have_text("工程师已批准复用")
        approved_transition = package_decision_page.locator(
            ".asset-candidate-callout"
        ).evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.background = rootStyle.getPropertyValue('--trust-signed');
              document.body.append(probe);
              const signed = getComputedStyle(probe).backgroundColor;
              probe.remove();
              return {
                mark: getComputedStyle(element.querySelector('.candidate-mark')).backgroundColor,
                signed,
                text: element.innerText,
              };
            }"""
        )
        check(
            "mock approved 响应经不可变投影核对后，同一 DOM 转为 teal 人签态",
            approved_transition["mark"] == approved_transition["signed"]
            and "自动复用" in approved_transition["text"]
            and package_drawer.get_by_role(
                "button", name="批准复用", exact=True
            ).count() == 0,
            str(approved_transition),
        )

        package_decision_page.evaluate(
            "() => window.__FLAI_PACKAGE_DECISION__.resetPending()"
        )
        expect(
            package_drawer.get_by_role("button", name="本次不批准", exact=True)
        ).to_be_enabled()
        package_drawer.get_by_role(
            "button", name="本次不批准", exact=True
        ).click()
        reject_request = package_decision_page.evaluate(
            "() => window.__FLAI_PACKAGE_DECISION__.requests[1]"
        )
        check(
            "包级拒绝同样只发精确 CAS POST",
            reject_request == {
                "path": "/api/skill-packages/skill_package_919191919191919191919191/decision",
                "method": "POST",
                "body": {
                    "schema_version": "skill_package_decision_request.v1",
                    "action": "reject",
                    "expected_package_digest": f"sha256:{'9' * 64}",
                },
            },
            str(reject_request),
        )
        package_decision_page.evaluate(
            "() => window.__FLAI_PACKAGE_DECISION__.resolve()"
        )
        expect(
            package_drawer.locator(".candidate-state.is-package-rejected")
        ).to_have_text("本次未批准复用")
        package_decision_page.close()

        frame = select_case(
            page,
            "asset-intake-desktop",
            "桌面 · 资产沉淀单焦点",
        )
        asset_intake = frame.locator(".asset-builder-drawer").evaluate(
            """element => {
              const rect = element.getBoundingClientRect();
              const header = element.querySelector('.el-drawer__header');
              const body = element.querySelector('.el-drawer__body');
              const footer = element.querySelector('.el-drawer__footer');
              return {
                width: rect.width,
                height: rect.height,
                headerTop: header.getBoundingClientRect().top,
                footerBottom: innerHeight - footer.getBoundingClientRect().bottom,
                bodyOverflow: getComputedStyle(body).overflowY,
                sourceBound: element.innerText.includes('当前会话') &&
                  element.innerText.includes('生成时由平台解析并校验'),
                conversationVisible: element.innerText.includes('ui-asset-work-case'),
                step: element.querySelector('[aria-current="step"]')?.innerText,
                fields: element.querySelectorAll('.asset-builder-form textarea, .asset-builder-form input').length,
                question: element.querySelector('#asset-focus-question-title')?.innerText,
                progress: element.querySelector('.asset-focus-count')?.innerText,
                activeId: document.activeElement?.id || '',
                answered: element.querySelector('.asset-summary-toggle')?.innerText,
              };
            }"""
        )
        check(
            "桌面 Asset Builder 为 560px 单焦点抽屉并绑定 Work Case",
            abs(asset_intake["width"] - 560) <= 1
            and asset_intake["height"] == 900
            and abs(asset_intake["headerTop"]) <= 0.5
            and abs(asset_intake["footerBottom"]) <= 0.5
            and asset_intake["bodyOverflow"] == "auto"
            and asset_intake["sourceBound"] is True
            and asset_intake["conversationVisible"] is True
            and "本次工作" in (asset_intake["step"] or "")
            and asset_intake["fields"] == 1
            and asset_intake["question"] == "如果以后再遇到，这类工作应该叫什么？"
            and asset_intake["progress"] == "问题 1 / 9"
            and asset_intake["activeId"] == "asset-field-title"
            and "已整理 2 / 9 项" in (asset_intake["answered"] or ""),
            str(asset_intake),
        )
        capture(frame, "asset-intake-desktop.png")

        for expected_id in [
            "asset-field-trigger",
            "asset-field-desired-outcome",
            "asset-field-inputs",
        ]:
            frame.get_by_role("button", name="下一问").click()
            expect(frame.locator(f"#{expected_id}")).to_be_focused()

        asset_method_focus = frame.locator(".asset-builder-drawer").evaluate(
            """element => ({
              fields: element.querySelectorAll('.asset-builder-form textarea, .asset-builder-form input').length,
              step: element.querySelector('[aria-current="step"]')?.innerText,
              progress: element.querySelector('.asset-focus-count')?.innerText,
              activeId: document.activeElement?.id || '',
              answered: element.querySelector('.asset-summary-toggle')?.innerText,
              documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
            })"""
        )
        check(
            "九问流程跨阶段仍只有一个输入并保留焦点与回答",
            asset_method_focus["fields"] == 1
            and "复用方法" in (asset_method_focus["step"] or "")
            and asset_method_focus["progress"] == "问题 4 / 9"
            and asset_method_focus["activeId"] == "asset-field-inputs"
            and "已整理 2 / 9 项" in (asset_method_focus["answered"] or "")
            and asset_method_focus["documentFits"] is True,
            str(asset_method_focus),
        )
        frame.locator(".asset-summary-toggle").click()
        check(
            "折叠摘要保留先前回答且不新增编辑框",
            "稳态算例入口边界复核" in frame.locator(".asset-answered-list").inner_text()
            and frame.locator(".asset-builder-form input, .asset-builder-form textarea").count() == 1,
        )
        frame.locator(".el-drawer__body").evaluate("element => { element.scrollTop = element.scrollHeight; }")
        frame.locator(".asset-answered-list button").first.click()
        expect(frame.locator("#asset-field-title")).to_be_focused()
        check(
            "摘要回跳同阶段也归顶并聚焦唯一问题",
            frame.locator(".el-drawer__body").evaluate("element => element.scrollTop") == 0,
        )
        for expected_id in [
            "asset-field-trigger",
            "asset-field-desired-outcome",
            "asset-field-inputs",
        ]:
            frame.get_by_role("button", name="下一问").click()
            expect(frame.locator(f"#{expected_id}")).to_be_focused()
        capture(frame, "asset-method-focus-desktop.png")

        for expected_id in [
            "asset-field-outputs",
            "asset-field-steps",
            "asset-field-evidence",
            "asset-field-human-boundaries",
            "asset-field-limitations",
        ]:
            frame.get_by_role("button", name="下一问").click()
            expect(frame.locator(f"#{expected_id}")).to_be_focused()
        frame.get_by_role("button", name="生成待审草稿").click()
        expect(frame.locator(".asset-builder-error")).to_contain_text("已阻止 fetch")
        check(
            "预览失败停留第九问、保留回答并恢复可编辑",
            frame.locator(".asset-focus-count").inner_text() == "问题 9 / 9"
            and frame.locator("#asset-field-limitations").is_enabled()
            and frame.locator(".asset-summary-toggle").inner_text().startswith("已整理 2 / 9 项")
            and frame.get_by_role("button", name="生成待审草稿").is_enabled(),
        )

        # 成功态 DOM 回归：隔离挂载真实 AssetBuilderDrawer，从公开按钮走完整的
        # Q4→Q9→预览成功链。仅在浏览器网络边界返回 ready fixture；不注入内部
        # showReview、不增加测试专用 prop，也不削弱 UI Lab 的只读边界。
        component_page = context.new_page()
        component_page.route(
            "**/src/ui-lab/main.js",
            lambda route: route.fulfill(
                content_type="application/javascript",
                body="export {};",
            ),
        )
        component_page.goto(BASE + "/ui-lab.html", wait_until="networkidle")
        ready_preview = component_page.evaluate(
            """async () => (
              await import('/src/ui-lab/uiAcceptanceCases.js')
            ).getUiAcceptanceCase('asset-review-desktop').guide.assetDraftPreview"""
        )

        def asset_preview_route(route):
            request_path = urlparse(route.request.url).path
            if (
                route.request.method == "POST"
                and request_path.endswith(
                    "/api/conversations/ui-asset-work-case/asset-draft-preview"
                )
            ):
                route.fulfill(status=200, json=ready_preview)
                return
            route.abort()

        component_page.route(
            f"{BASE}/api/**",
            asset_preview_route,
        )
        component_page.evaluate(
            """async () => {
              const [Vue, ElementPlus, zhCn, drawerModule, casesModule] =
                await Promise.all([
                  import('/node_modules/.vite/deps/vue.js'),
                  import('/node_modules/.vite/deps/element-plus.js'),
                  import('/node_modules/.vite/deps/element-plus_es_locale_lang_zh-cn.js'),
                  import('/src/components/AssetBuilderDrawer.vue'),
                  import('/src/ui-lab/uiAcceptanceCases.js'),
                ]);
              const fixture = casesModule.getUiAcceptanceCase('asset-review-desktop').guide;
              const app = Vue.createApp(drawerModule.default, {
                modelValue: true,
                conversationId: fixture.conversationId,
                messages: fixture.messages,
                initialStep: 2,
                initialGeneralization: fixture.assetDraftGeneralization,
              });
              app.use(ElementPlus.default, { locale: zhCn.default });
              app.mount('#app');
            }"""
        )
        expect(component_page.locator(".asset-builder-drawer")).to_be_visible()
        expect(component_page.locator("#asset-field-inputs")).to_be_focused()
        for expected_id in [
            "asset-field-outputs",
            "asset-field-steps",
            "asset-field-evidence",
            "asset-field-human-boundaries",
            "asset-field-limitations",
        ]:
            component_page.get_by_role("button", name="下一问").click()
            expect(component_page.locator(f"#{expected_id}")).to_be_focused()
        component_page.get_by_role("button", name="生成待审草稿").click()
        expect(component_page.locator("#asset-review-title")).to_be_visible()
        expect(component_page.locator("#asset-review-title")).to_be_focused()
        success_dom = component_page.locator(".asset-builder-drawer").evaluate(
            """element => ({
              currentStep: element.querySelector('[aria-current="step"]')?.innerText || '',
              reviewStatus: element.querySelector('.asset-review-status')?.innerText || '',
              editBoxes: element.querySelectorAll(
                '.asset-builder-form input, .asset-builder-form textarea'
              ).length,
              downloadDisabled: [...element.querySelectorAll('button')].find(
                item => item.innerText.includes('下载待审 JSON')
              )?.disabled,
              hasError: Boolean(element.querySelector('.asset-builder-error')),
            })"""
        )
        check(
            "生成待审草稿成功后真实进入只读待审 DOM",
            "待审草稿" in success_dom["currentStep"]
            and "结构校验完成 · 等待人工审核" in success_dom["reviewStatus"]
            and success_dom["editBoxes"] == 0
            and success_dom["downloadDisabled"] is False
            and success_dom["hasError"] is False,
            str(success_dom),
        )
        component_page.close()

        frame = select_case(
            page,
            "asset-review-desktop",
            "桌面 · 待审资产草稿",
        )
        asset_review = frame.locator(".asset-builder-drawer").evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = rootStyle.getPropertyValue('--trust-pending');
              document.body.append(probe);
              const pending = getComputedStyle(probe).color;
              probe.remove();
              const state = element.querySelector('.asset-review-status');
              const stateIcon = state.querySelector('.asset-review-state .el-icon');
              const buttons = [...element.querySelectorAll('button')].map(item => item.innerText.trim());
              return {
                stateIconColor: getComputedStyle(stateIcon).color,
                pending,
                taskPattern: element.innerText.includes('TASK PATTERN · DRAFT'),
                skill: element.innerText.includes('SKILL · DRAFT'),
                reviewGate: element.innerText.includes('HUMAN REVIEW GATE'),
                honesty: element.innerText.includes('下载不等于注册'),
                zeroEffects: element.innerText.includes('未写数据库') && element.innerText.includes('未注册或晋级'),
                hasDownload: buttons.some(text => text.includes('下载待审 JSON')),
                hasApprove: buttons.some(text => /批准|注册|晋级/.test(text)),
              };
            }"""
        )
        check(
            "待审资产链使用 amber 且没有批准/注册/晋级动作",
            asset_review["stateIconColor"] == asset_review["pending"]
            and asset_review["taskPattern"] is True
            and asset_review["skill"] is True
            and asset_review["reviewGate"] is True
            and asset_review["honesty"] is True
            and asset_review["zeroEffects"] is True
            and asset_review["hasDownload"] is True
            and asset_review["hasApprove"] is False,
            str(asset_review),
        )
        capture(frame, "asset-review-desktop.png")

        frame = select_case(
            page,
            "asset-review-mobile",
            "移动端 · 待审资产草稿",
        )
        asset_mobile = frame.locator(".asset-builder-drawer").evaluate(
            """element => {
              const rect = element.getBoundingClientRect();
              const body = element.querySelector('.el-drawer__body');
              const footer = element.querySelector('.el-drawer__footer');
              const download = [...element.querySelectorAll('button')].find(item =>
                item.innerText.includes('下载待审 JSON')
              );
              return {
                viewport: { width: innerWidth, height: innerHeight },
                width: rect.width,
                height: rect.height,
                left: rect.left,
                bodyOverflow: getComputedStyle(body).overflowY,
                footerBottom: innerHeight - footer.getBoundingClientRect().bottom,
                downloadTouch: download?.getBoundingClientRect().height || 0,
                documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
              };
            }"""
        )
        check(
            "移动 Asset Builder 全屏、正文内部滚动且底栏触控目标可用",
            asset_mobile["viewport"] == {"width": 375, "height": 812}
            and abs(asset_mobile["width"] - 375) <= 1
            and abs(asset_mobile["height"] - 812) <= 1
            and abs(asset_mobile["left"]) <= 0.5
            and asset_mobile["bodyOverflow"] == "auto"
            and abs(asset_mobile["footerBottom"]) <= 0.5
            and asset_mobile["downloadTouch"] >= 44
            and asset_mobile["documentFits"] is True,
            str(asset_mobile),
        )
        capture(frame, "asset-review-mobile.png")

        frame.get_by_role("button", name="返回整理").click()
        expect(frame.locator("#asset-field-limitations")).to_be_focused()
        asset_focus_mobile = frame.locator(".asset-builder-drawer").evaluate(
            """element => {
              const rect = element.getBoundingClientRect();
              const footerButtons = [...element.querySelectorAll('.asset-builder-actions button')];
              return {
                viewport: { width: innerWidth, height: innerHeight },
                width: rect.width,
                height: rect.height,
                fields: element.querySelectorAll('.asset-builder-form textarea, .asset-builder-form input').length,
                progress: element.querySelector('.asset-focus-count')?.innerText,
                activeId: document.activeElement?.id || '',
                minFooterTouch: Math.min(...footerButtons.map(item => item.getBoundingClientRect().height)),
                documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
              };
            }"""
        )
        check(
            "移动单焦点问题保持全屏、单输入与 44px 底栏",
            asset_focus_mobile["viewport"] == {"width": 375, "height": 812}
            and abs(asset_focus_mobile["width"] - 375) <= 1
            and abs(asset_focus_mobile["height"] - 812) <= 1
            and asset_focus_mobile["fields"] == 1
            and asset_focus_mobile["progress"] == "问题 9 / 9"
            and asset_focus_mobile["activeId"] == "asset-field-limitations"
            and asset_focus_mobile["minFooterTouch"] >= 44
            and asset_focus_mobile["documentFits"] is True,
            str(asset_focus_mobile),
        )
        capture(frame, "asset-focus-mobile.png")

        frame = select_case(
            page,
            "asset-blocked-mobile",
            "移动端 · 草稿阻断待补",
        )
        asset_blocked = frame.locator(".asset-builder-drawer").evaluate(
            """element => {
              const rootStyle = getComputedStyle(document.documentElement);
              const probe = document.createElement('span');
              probe.style.color = rootStyle.getPropertyValue('--trust-fail');
              document.body.append(probe);
              const fail = getComputedStyle(probe).color;
              probe.remove();
              const state = element.querySelector('.asset-review-status.needs-revision');
              const download = [...element.querySelectorAll('button')].find(item =>
                item.innerText.includes('下载待审 JSON')
              );
              const rect = element.getBoundingClientRect();
              return {
                viewport: { width: innerWidth, height: innerHeight },
                width: rect.width,
                stateColor: state ? getComputedStyle(state).color : '',
                fail,
                blockingSummary: state?.innerText || '',
                issueCount: element.querySelectorAll('.asset-issue-list .is-blocking').length,
                downloadDisabled: download?.disabled,
                documentFits: document.documentElement.scrollWidth <= document.documentElement.clientWidth,
              };
            }"""
        )
        check(
            "needs_revision 用红色阻断摘要且禁止下载",
            asset_blocked["viewport"] == {"width": 375, "height": 812}
            and abs(asset_blocked["width"] - 375) <= 1
            and asset_blocked["stateColor"] == asset_blocked["fail"]
            and "需补全 · 2 项阻断" in asset_blocked["blockingSummary"]
            and asset_blocked["issueCount"] == 2
            and asset_blocked["downloadDisabled"] is True
            and asset_blocked["documentFits"] is True,
            str(asset_blocked),
        )
        capture(frame, "asset-blocked-mobile.png")

        verification_issue = frame.locator(
            ".asset-issue-list li",
            has_text="/skill/verification",
        )
        verification_issue.get_by_role("button", name="返回补全").click()
        expect(frame.locator("#asset-field-evidence")).to_be_focused()
        check(
            "阻断项返回补全落到唯一对应问题",
            frame.locator(".asset-focus-count").inner_text() == "问题 7 / 9"
            and frame.locator(".asset-builder-form input, .asset-builder-form textarea").count() == 1,
        )

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
