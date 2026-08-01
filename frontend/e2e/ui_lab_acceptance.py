"""轻量 UI 验收台浏览器回归。

自包含：启动真实 Vite 开发服务器，不启动后端、不读写真实业务数据。验收台入口
是 development-only，生产构建故意不包含 ui-lab.html，因此本脚本不能复用 dist。

覆盖：
  ① 未知 case fail-closed；
  ② 十个固定镜头、精确 viewport 与桌面布局数值基线；
  ③ opaque-origin iframe + 只读边界阻止网络和主题偏好写入；
  ④ 自动路由摘要默认收敛，Agent/模型/工具依据按需披露；
  ⑤ 流式快照使用真实 generating 标记，正文给固定 composer 留足空间；
  ⑥ 保存待核使用 amber，且发送、附件、Agent 共同锁定；
  ⑦ Asset Builder 单焦点九问、待审桌面/移动与 needs_revision 阻断；
  ⑧ 375px 无横向溢出。

运行（仓根）：
  uv run --no-project --with playwright python frontend/e2e/ui_lab_acceptance.py

截图落 docs/reviews/ui-lab-shots/，每次重跑覆盖十个固定镜头与焦点过渡证据。
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
    if case_id.startswith("asset-"):
        expect(frame.locator(".asset-builder-drawer")).to_be_visible()
        page.wait_for_timeout(250)
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
            "固定十镜头与逐项检查点",
            page.locator(".case-button").count() == 10
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
                  document.body.innerText.match(/开工与签发仍由你确认/g) || []
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
            and "系统会在后台自动编排所需能力" in landing_signature["promise"],
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

        frame = select_case(
            page,
            "routing-desktop",
            "桌面 · 自动路由待确认",
        )
        route_disclosure = frame.locator(".route-disclosure")
        route_before = frame.evaluate(
            """() => ({
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
            and route_before["primaryActions"] == ["按方案开工"],
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
                "rosterText": "执行单元 · 2",
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

        frame.locator("#asset-field-inputs").fill("单焦点回归输入")
        frame.get_by_role("button", name="关闭此对话框").click()
        frame.get_by_role("button", name="沉淀本次工作").click()
        expect(frame.locator("#asset-field-inputs")).to_be_focused()
        check(
            "同一会话关闭重开保留当前问题、回答与宏观阶段",
            frame.locator(".asset-focus-count").inner_text() == "问题 4 / 9"
            and frame.locator("#asset-field-inputs").input_value() == "单焦点回归输入"
            and "复用方法" in frame.locator('[aria-current="step"]').inner_text()
            and frame.locator(".asset-builder-form input, .asset-builder-form textarea").count() == 1,
        )

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
            and frame.locator(".asset-summary-toggle").inner_text().startswith("已整理 3 / 9 项")
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

        component_page.route("**/api/**", asset_preview_route)
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
