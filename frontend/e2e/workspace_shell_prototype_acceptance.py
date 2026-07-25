"""Workspace Shell V1 原型 UI 行为验收（SYNTHETIC ONLY）。

自包含：启动 frontend vite dev server（需先 npm ci）+ 真 chromium，
仅访问 /workspace-shell.html 原型页，不连后端、不打真 LLM、不碰 data/。

断言矩阵（对应 work_item flai-workspace-shell-kimi-001@1）：
  ① 三工作流 × running/waiting_review/completed = 9 核心页：
     glyph / data-motion / data-trust / Focus Surface 种类逐组合断言并截图；
  ② docx 五异常页：failed / cancelled / evidence-missing /
     permission-denied / observation-invalid：通知卡、公开原因码、
     Focus 种类、静止与信任槽；
  ③ docx:running × REAL/MOCK/TEST/UNKNOWN 四显示形态 DOM：
     即使 REAL 形态也保持 source-kind=synthetic-fixture、永不进 real 槽；
     UNKNOWN 形态强制 fail-closed 缺口并禁用状态选择器；
  ④ stale 叠加态（96 矩阵外）：docx:running 观察过期 → 停动画、
     UNKNOWN/未核、Focus 不残留敏感预览（无 SHA-256/来源见证行）；
  ⑤ fail-closed 优先：evidence-missing / observation-invalid 即使带
     REAL 形态，徽标一律 UNKNOWN 未核；
  ⑥ completed 中性永不绿、全页无 real/sign 槽、无“已签发”措辞、
     合成/未签发永不 teal；
  ⑦ 指令队列：Ctrl+Enter 连续提交三条 → 独立稳定 ID（cmd-1..3）、
     保序、文本互不拼接、receipt=ACCEPTED 且明示“不代表完成”；
  ⑧ IME composition 期间 ⌘/Ctrl+Enter 不提交，结束后可提交；
  ⑨ 键盘可达与 focus-visible：Tab 可遍历到搜索框/工作项/Composer，
     焦点环 2px solid，键盘可完成提交；
  ⑩ 1440px 与 1280px 无横向溢出；
  ⑪ prefers-reduced-motion：glyph computed animation-name 为 none；
  ⑫ 颜色不是唯一状态信号：glyph 带 aria-label 与相邻文字标签、
     徽标与状态均带文字；
  ⑬ 可见 11px/12px 直接文本对比度 >= 4.5:1（三态扫描）；
  ⑭ 治理入口默认折叠；左轨搜索可过滤；无 iframe；
  ⑮ 网络边界：零非 loopback 请求、零应用 fetch/XHR/WebSocket/
     EventSource/beacon/service-worker（vite HMR client 被拦截，
     页面在完全无 WebSocket 下工作）；
  ⑯ 截图清单由测试自证，文件数与名称不依赖手工陈述。

运行（仓根）：
  cd frontend && npm ci && cd ..
  WORKSPACE_SHELL_SHOTS=<dir> UV_OFFLINE=1 uv run --offline --no-project \
    --with playwright python frontend/e2e/workspace_shell_prototype_acceptance.py
"""
from __future__ import annotations

import json
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
SHOTS = Path(
    os.environ.get("WORKSPACE_SHELL_SHOTS")
    or tempfile.mkdtemp(prefix="workspace-shell-shots-")
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

if not (FRONTEND / "node_modules").is_dir():
    sys.exit("诚实失败：frontend/node_modules 缺失。先执行 cd frontend && npm ci")

WORKFLOWS = ["docx", "meeting", "cfd"]
RUNNING_GLYPH = {"docx": "compute", "meeting": "search", "cfd": "parse"}
CORE_EXPECT = {
    "running": {"motion": "true", "trust": "active", "focus": "runtime"},
    "waiting_review": {
        "motion": "false", "trust": "attention", "focus": "diff", "glyph": "waiting-review",
    },
    "completed": {
        "motion": "false", "trust": "terminal", "focus": "artifact", "glyph": "render",
    },
}


def wait_port(port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    sys.exit(f"诚实失败：vite dev server 端口 {port} 等待超时")


def goto(page, workflow: str, state: str, form: str | None = None):
    url = f"{BASE}/workspace-shell.html?workflow={workflow}&state={state}"
    if form is not None:
        url += f"&form={form}"
    page.goto(url)
    page.wait_for_selector("[data-testid='ws-center']")


failures: list[str] = []
passed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if ok:
        passed += 1
    else:
        failures.append(f"{name}: {detail}")


def small_text_contrast_violations(page) -> list[str]:
    """扫描可见直接文本，返回 12px 及以下且低于 WCAG AA 4.5:1 的元素。"""
    return page.evaluate(
        """() => {
          const rgba = value => {
            const match = value.match(/[\\d.]+/g);
            if (!match) return [0, 0, 0, 0];
            const values = match.map(Number);
            return [values[0], values[1], values[2], values.length > 3 ? values[3] : 1];
          };
          const luminance = rgb => {
            const linear = rgb.slice(0, 3).map(channel => {
              const value = channel / 255;
              return value <= 0.04045
                ? value / 12.92
                : Math.pow((value + 0.055) / 1.055, 2.4);
            });
            return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
          };
          return [...document.querySelectorAll('body *')].flatMap((el, index) => {
            const style = getComputedStyle(el);
            const rect = el.getBoundingClientRect();
            const directText = [...el.childNodes].some(
              node => node.nodeType === Node.TEXT_NODE && node.textContent.trim(),
            );
            if (
              !directText
              || rect.width === 0
              || rect.height === 0
              || style.display === 'none'
              || style.visibility === 'hidden'
              || Number.parseFloat(style.fontSize) > 12
            ) {
              return [];
            }
            const foreground = rgba(style.color);
            let node = el;
            let background = [255, 255, 255, 1];
            while (node) {
              const candidate = rgba(getComputedStyle(node).backgroundColor);
              if (candidate[3] > 0) {
                background = candidate;
                break;
              }
              node = node.parentElement;
            }
            const a = luminance(foreground);
            const b = luminance(background);
            const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
            if (ratio >= 4.5) return [];
            const label = el.getAttribute('data-testid')
              || (typeof el.className === 'string' && el.className)
              || `${el.tagName.toLowerCase()}[${index}]`;
            return [`${label}=${ratio.toFixed(2)}:1`];
          });
        }""",
    )


# 网络账本：实现本身不得发任何请求；测试只允许固定 loopback origin 的
# document/module/static bootstrap。/@vite/client 被无 HMR 桩替换以根除
# WebSocket（原型不需要 HMR；替换后页面必须在无 WebSocket 下正常工作）。
network = {"non_loopback": [], "xhr": 0, "fetch": 0, "websocket": 0, "eventsource": 0}


# 网络账本：实现本身不得发任何请求；测试只允许固定 loopback origin 的
# document/module/static bootstrap（含 vite dev 的 /@vite/client 样式注入）。
def route_handler(route):
    url = route.request.url
    if not (url.startswith(BASE) or url.startswith("data:") or url == "about:blank"):
        network["non_loopback"].append(url)
        route.abort()
        return
    route.continue_()


def on_request(request):
    kind = request.resource_type
    if kind in ("xhr", "fetch", "websocket", "eventsource"):
        network[kind] += 1


INIT_SCRIPT = """
window.__wsNet = {
  fetch: 0, xhr: 0, websocket: 0, eventsource: 0, beacon: 0, serviceworker: 0,
  devtoolsHmr: 0,
};
const wsDeny = (kind) => { window.__wsNet[kind] += 1; throw new Error(`network denied: ${kind}`); };
window.fetch = () => wsDeny('fetch');
window.XMLHttpRequest = class { constructor() { wsDeny('xhr'); } };
// 应用 WebSocket 一律拒绝并计数；vite dev 的 HMR socket（固定 loopback +
// 'vite-hmr' 子协议）是 dev-server bootstrap，不是应用请求：黑洞化（从不
// 连接）并单独计数披露，页面在无 HMR 下正常工作。
window.WebSocket = class {
  constructor(url, protocols) {
    const text = String(url);
    const loopback = /^wss?:\\/\\/(127\\.0\\.0\\.1|localhost)(:\\d+)?\\//.test(text);
    const hmr = Array.isArray(protocols)
      ? protocols.includes('vite-hmr')
      : protocols === 'vite-hmr';
    if (loopback && hmr) {
      window.__wsNet.devtoolsHmr += 1;
      this.addEventListener = () => {};
      this.removeEventListener = () => {};
      this.close = () => {};
      this.send = () => {};
      return;
    }
    wsDeny('websocket');
  }
};
window.EventSource = class { constructor() { wsDeny('eventsource'); } };
if (navigator.sendBeacon) {
  navigator.sendBeacon = () => { window.__wsNet.beacon += 1; return false; };
}
if (navigator.serviceWorker) {
  navigator.serviceWorker.register = () => wsDeny('serviceworker');
}
"""

server = subprocess.Popen(
    ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", str(PORT), "--strictPort"],
    cwd=FRONTEND,
    stdout=subprocess.DEVNULL,
    stderr=subprocess.DEVNULL,
    start_new_session=True,  # 独立进程组，保证 npm 的子进程 vite 也能被回收
)
try:
    wait_port(PORT)
    urllib.request.urlopen(f"{BASE}/workspace-shell.html", timeout=10)

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:  # noqa: BLE001 - 需要诚实失败信息
            sys.exit(f"诚实失败：chromium 不可用：{exc}\n请先 uv run --no-project --with playwright python -m playwright install chromium")

        context = browser.new_context(viewport={"width": 1440, "height": 900})
        context.add_init_script(INIT_SCRIPT)
        context.route("**/*", route_handler)
        page = context.new_page()
        page.on("request", on_request)

        # ① 三工作流 × running/waiting_review/completed 核心页
        for workflow in WORKFLOWS:
            for state, expect in CORE_EXPECT.items():
                goto(page, workflow, state)
                glyph = page.get_attribute("[data-testid='action-glyph']", "data-glyph")
                motion = page.get_attribute("[data-testid='action-glyph']", "data-motion")
                trust = page.get_attribute("[data-testid='action-card']", "data-trust")
                focus = page.get_attribute("[data-testid='focus-card']", "data-focus-kind")
                want_glyph = expect.get("glyph") or RUNNING_GLYPH[workflow]
                check(
                    f"{workflow}:{state} glyph/motion/trust/focus",
                    glyph == want_glyph
                    and motion == expect["motion"]
                    and trust == expect["trust"]
                    and focus == expect["focus"],
                    f"glyph={glyph} motion={motion} trust={trust} focus={focus}",
                )
                badge = page.locator("[data-testid='reality-badge']")
                badge_text = badge.text_content() or ""
                check(
                    f"{workflow}:{state} 合成负例（无 real/sign 槽、标注非真实见证）",
                    badge.get_attribute("data-source-kind") == "synthetic-fixture"
                    and "非真实见证" in badge_text
                    and page.locator("[data-slot='real']").count() == 0
                    and page.locator("[data-slot='sign']").count() == 0
                    and "已签发" not in (page.text_content("body") or ""),
                    badge_text.strip(),
                )
                page.screenshot(path=str(SHOTS / f"core-{workflow}-{state}.png"), full_page=True)

        # ② docx 五异常页
        exception_expect = {
            "failed": {
                "card": "exception-card", "code": "EXECUTION_FAILED_SYNTHETIC",
                "trust": "fail", "focus": "exception",
            },
            "cancelled": {
                "card": "stopped-card", "code": "EXECUTION_CANCELLED_SYNTHETIC",
                "trust": "terminal", "focus": "stopped",
            },
            "evidence-missing": {
                "card": "gap-card", "code": "observation_missing",
                "trust": "unverified", "focus": "gap",
            },
            "permission-denied": {
                "card": "boundary-card", "code": "PERMISSION_DENIED_SYNTHETIC",
                "trust": "fail", "focus": "denied",
            },
            "observation-invalid": {
                "card": "gap-card", "code": "observation_invalid",
                "trust": "unverified", "focus": "gap",
            },
        }
        for state, expect in exception_expect.items():
            goto(page, "docx", state)
            card = page.locator(f"[data-testid='{expect['card']}']")
            card_text = card.text_content() or ""
            check(
                f"docx:{state} 通知卡 + 公开原因码 + 静止 + Focus",
                card.is_visible()
                and expect["code"] in card_text
                and page.get_attribute("[data-testid='action-glyph']", "data-motion") == "false"
                and page.get_attribute("[data-testid='action-card']", "data-trust") == expect["trust"]
                and page.get_attribute("[data-testid='focus-card']", "data-focus-kind") == expect["focus"],
                card_text.strip()[:80],
            )
            page.screenshot(path=str(SHOTS / f"docx-{state}.png"), full_page=True)

        # ②b permission-denied / evidence-missing 不得假装执行仍在继续
        for state in ("permission-denied", "evidence-missing"):
            goto(page, "docx", state)
            check(
                f"docx:{state} 不假装执行继续（静止 + 原因码可见）",
                page.get_attribute("[data-testid='action-glyph']", "data-motion") == "false"
                and page.locator(".notice-code").first.is_visible(),
            )

        # ③ docx:running × 四显示形态
        for form in ("REAL", "MOCK", "TEST"):
            goto(page, "docx", "running", form=form)
            badge = page.locator("[data-testid='reality-badge']")
            check(
                f"docx:running@{form} 形态徽标 DOM",
                badge.get_attribute("data-reality-form") == form
                and badge.get_attribute("data-source-kind") == "synthetic-fixture"
                and badge.get_attribute("data-slot") == "synthetic"
                and f"合成夹具 · {form} 显示形态 · 非真实见证" in (badge.text_content() or "")
                and page.locator("[data-slot='real']").count() == 0,
                (badge.text_content() or "").strip(),
            )
        goto(page, "docx", "running", form="UNKNOWN")
        badge = page.locator("[data-testid='reality-badge']")
        check(
            "docx:running@UNKNOWN 强制 fail-closed 缺口",
            badge.get_attribute("data-reality-form") == "UNKNOWN"
            and badge.get_attribute("data-slot") == "unverified"
            and page.get_attribute("[data-testid='focus-card']", "data-focus-kind") == "gap"
            and page.locator("[data-testid='ws-state-picker']").is_disabled()
            and page.locator("[data-testid='unknown-form-hint']").is_visible()
            and page.get_attribute("[data-testid='action-glyph']", "data-motion") == "false",
        )
        page.screenshot(path=str(SHOTS / "docx-form-unknown.png"), full_page=True)

        # ③b 非法形态参数 fail-closed 到 UNKNOWN，绝不回退 REAL
        goto(page, "docx", "running", form="FAKE")
        check(
            "非法 form 参数 fail-closed 到 UNKNOWN 缺口",
            page.locator("[data-testid='reality-badge']").get_attribute("data-reality-form") == "UNKNOWN"
            and page.input_value("[data-testid='ws-form-picker']") == "UNKNOWN"
            and page.get_attribute("[data-testid='focus-card']", "data-focus-kind") == "gap",
        )

        # ④ stale 叠加态：停动画 + UNKNOWN 未核 + 清空敏感 Focus 预览
        goto(page, "docx", "stale", form="REAL")
        gap = page.locator("[data-testid='gap-card']")
        focus_text = page.text_content("[data-testid='focus-card']") or ""
        badge = page.locator("[data-testid='reality-badge']")
        check(
            "docx:stale 过期观察 fail-closed",
            page.get_attribute("[data-testid='action-glyph']", "data-motion") == "false"
            and page.get_attribute("[data-testid='action-card']", "data-trust") == "unverified"
            and badge.get_attribute("data-reality-form") == "UNKNOWN"
            and badge.get_attribute("data-slot") == "unverified"
            and gap.is_visible()
            and "observation_stale" in (gap.text_content() or "")
            and page.get_attribute("[data-testid='focus-card']", "data-focus-kind") == "gap"
            and "SHA-256" not in focus_text
            and "来源见证" not in focus_text,
            focus_text.strip()[:80],
        )
        page.screenshot(path=str(SHOTS / "docx-stale.png"), full_page=True)

        # ⑤ fail-closed 优先于形态字段
        for state in ("evidence-missing", "observation-invalid"):
            goto(page, "docx", state, form="REAL")
            badge = page.locator("[data-testid='reality-badge']")
            check(
                f"docx:{state}@REAL 徽标压到 UNKNOWN 未核",
                badge.get_attribute("data-reality-form") == "UNKNOWN"
                and badge.get_attribute("data-slot") == "unverified",
            )

        # ⑥ completed 中性永不绿；交付区无 teal 路径
        goto(page, "docx", "completed")
        check(
            "completed 交付区：琥珀未签发 + 无 teal/绿槽",
            page.locator("[data-testid='delivery']").is_visible()
            and page.get_attribute("[data-testid='unsigned-badge']", "data-slot") == "unverified"
            and page.get_attribute("[data-testid='action-card']", "data-trust") == "terminal"
            and page.locator("[data-slot='sign']").count() == 0
            and page.locator("[data-slot='real']").count() == 0,
        )
        page.click("[data-testid='sign-conditions-button']")
        check(
            "签发条件可见且仍无签发事实",
            page.locator("[data-testid='sign-conditions']").is_visible()
            and "receipt" in (page.locator("[data-testid='sign-conditions']").text_content() or "")
            and "已签发" not in (page.text_content("body") or "")
            and page.locator("[data-slot='sign']").count() == 0
            and page.get_attribute("[data-testid='unsigned-badge']", "data-slot") == "unverified",
        )

        # ⑦ 指令队列：三条独立提交，稳定 ID、保序、互不拼接
        goto(page, "docx", "running")
        composer = "[data-testid='composer'] textarea"
        texts = ["把第三节改写得更正式", "补充一张对照表", "检查引用格式"]
        for text in texts:
            page.fill(composer, text)
            page.press(composer, "Control+Enter")
        items = page.locator("[data-testid='queue-item']")
        check(
            "队列：三条独立指令稳定 ID 且保序",
            items.count() == 3
            and [items.nth(i).get_attribute("data-command-id") for i in range(3)]
            == ["cmd-1", "cmd-2", "cmd-3"]
            and [items.nth(i).locator(".queue-text").text_content() for i in range(3)] == texts,
        )
        check(
            "队列：receipt 只表示已受理，不代表完成",
            all(
                items.nth(i).get_attribute("data-receipt-status") == "ACCEPTED"
                and "不代表完成" in (items.nth(i).locator(".queue-receipt").text_content() or "")
                for i in range(3)
            )
            and page.input_value(composer) == "",
        )
        page.screenshot(path=str(SHOTS / "queue-order.png"), full_page=True)

        # ⑧ IME composition 期间快捷键不提交，结束后可提交
        page.fill(composer, "输入中途")
        page.eval_on_selector(
            composer,
            """el => {
              el.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
              el.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter', ctrlKey: true, bubbles: true, cancelable: true, isComposing: true,
              }));
            }""",
        )
        check(
            "IME composition 中 Ctrl+Enter 不提交",
            page.locator("[data-testid='queue-item']").count() == 3
            and page.input_value(composer) == "输入中途",
        )
        page.eval_on_selector(
            composer,
            "el => el.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true }))",
        )
        page.press(composer, "Control+Enter")
        check(
            "IME composition 结束后 Ctrl+Enter 可提交",
            page.locator("[data-testid='queue-item']").count() == 4
            and page.input_value(composer) == "",
        )

        # ⑧b Enter 单独按下只是换行，不提交
        page.fill(composer, "第一行")
        page.press(composer, "Enter")
        check(
            "Enter 单独按下不提交（IME 安全）",
            page.locator("[data-testid='queue-item']").count() == 4
            and page.input_value(composer).startswith("第一行"),
        )

        # ⑨ 键盘可达 + focus-visible：Tab 遍历到搜索框/工作项/Composer
        page.evaluate("document.activeElement && document.activeElement.blur()")
        visited = []
        focused_composer = False
        for _ in range(30):
            page.keyboard.press("Tab")
            info = page.evaluate(
                """() => {
                  const el = document.activeElement;
                  if (!el || el.tagName === 'BODY') return null;
                  const cs = getComputedStyle(el);
                  return {
                    testid: el.getAttribute('data-testid') || el.tagName,
                    outline: `${cs.outlineWidth} ${cs.outlineStyle}`,
                  };
                }""",
            )
            if info:
                visited.append(info)
            if info and info["testid"] == "composer-input":
                focused_composer = True
                break
        visited_ids = [item["testid"] for item in visited]
        check(
            "键盘 Tab 可达：搜索框、工作项与 Composer 均可聚焦",
            focused_composer
            and any("rail-search" in str(t) for t in visited_ids)
            and any("rail-item" in str(t) or t == "BUTTON" for t in visited_ids),
            " -> ".join(str(t) for t in visited_ids[:12]),
        )
        check(
            "focus-visible 焦点环 2px solid",
            bool(visited) and all(item["outline"] == "2px solid" for item in visited),
            "; ".join(f"{item['testid']}={item['outline']}" for item in visited[:6]),
        )
        # 键盘完成一次完整提交（不碰鼠标）
        page.keyboard.type("纯键盘提交的指令")
        page.keyboard.press("Control+Enter")
        check(
            "键盘完成提交并清空 Composer",
            page.locator("[data-testid='queue-item']").count() == 5
            and page.input_value(composer) == "",
        )

        # ⑩ 1440 / 1280 无横向溢出
        for width in (1440, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            goto(page, "cfd", "running")
            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            check(f"{width}px 无横向溢出", not overflow)
        page.set_viewport_size({"width": 1440, "height": 900})

        # ⑪ reduced-motion 停动画
        page.emulate_media(reduced_motion="reduce")
        goto(page, "docx", "running")
        anim = page.eval_on_selector(
            "[data-testid='action-glyph'] .g-anim-fill",
            "el => getComputedStyle(el).animationName",
        )
        check("reduced-motion 下 glyph 动画为 none", anim == "none", anim)
        page.emulate_media(reduced_motion="no-preference")

        # ⑫ 颜色不是唯一状态信号：glyph aria-label + 相邻文字 + 徽标文字
        goto(page, "docx", "running")
        overline = page.text_content("[data-testid='action-card'] .action-overline") or ""
        check(
            "状态非颜色唯一编码（glyph 标签 + 文字 + 徽标文字）",
            (page.get_attribute("[data-testid='action-glyph']", "aria-label") or "") in overline
            and len((page.text_content("[data-testid='reality-badge']") or "").strip()) > 0
            and len((page.text_content("[data-testid='step-label']") or "").strip()) > 0,
            overline.strip(),
        )

        # ⑬ 小字号文本对比度（三态扫描）
        for state in ("running", "waiting_review", "observation-invalid"):
            goto(page, "docx", state)
            violations = small_text_contrast_violations(page)
            check(
                f"docx:{state} 可见 11/12px 文本对比度 >= 4.5:1",
                not violations,
                ", ".join(violations),
            )

        # ⑭ 治理默认折叠；左轨搜索过滤；无 iframe
        goto(page, "docx", "running")
        check(
            "治理入口默认折叠",
            page.get_attribute("[data-testid='rail-governance']", "open") is None
            and page.get_attribute("[data-testid='demo-console']", "open") is None,
        )
        page.fill("[data-testid='rail-search']", "纪要")
        recent_text = page.text_content("[data-testid='rail-recent']") or ""
        check(
            "左轨搜索过滤最近工作",
            "纪要整理" in recent_text and "报告润色" not in recent_text,
            recent_text.strip()[:60],
        )
        check("无 iframe（不嵌入第三方 Surface）", page.locator("iframe").count() == 0)

        # ⑮ 状态一致性：picker 切换后选择器值、glyph、Focus 与徽标一致
        goto(page, "docx", "running")
        page.locator("[data-testid='demo-console'] summary").click()
        page.select_option("[data-testid='ws-state-picker']", "failed")
        check(
            "切到 failed 后选择器/glyph/Focus/徽标一致",
            page.input_value("[data-testid='ws-state-picker']") == "failed"
            and page.get_attribute("[data-testid='action-glyph']", "data-glyph") == "failed"
            and page.get_attribute("[data-testid='action-glyph']", "data-motion") == "false"
            and page.get_attribute("[data-testid='focus-card']", "data-focus-kind") == "exception"
            and page.locator("[data-testid='exception-card']").is_visible(),
        )
        page.select_option("[data-testid='ws-state-picker']", "running")
        page.select_option("[data-testid='ws-form-picker']", "MOCK")
        check(
            "切到 MOCK 形态后徽标即时更新且状态保持",
            page.locator("[data-testid='reality-badge']").get_attribute("data-reality-form") == "MOCK"
            and page.input_value("[data-testid='ws-state-picker']") == "running"
            and page.get_attribute("[data-testid='action-glyph']", "data-motion") == "true",
        )

        # ⑮b 网络账本：页面交互后仍然零违规
        net_counts = page.evaluate("window.__wsNet")
        app_net = {key: value for key, value in net_counts.items() if key != "devtoolsHmr"}
        check(
            "零应用 fetch/XHR/WebSocket/EventSource/beacon/service-worker",
            app_net == {
                "fetch": 0, "xhr": 0, "websocket": 0,
                "eventsource": 0, "beacon": 0, "serviceworker": 0,
            }
            and network["xhr"] == 0
            and network["fetch"] == 0
            and network["websocket"] == 0
            and network["eventsource"] == 0,
            json.dumps({"dom": net_counts, "requests": network}),
        )
        check(
            "vite HMR socket 已黑洞化且无任何真实 ws 连接",
            network["websocket"] == 0,
            f"devtoolsHmr（仅计数披露）={net_counts.get('devtoolsHmr')}",
        )
        check(
            "零非 loopback 请求",
            not network["non_loopback"],
            "; ".join(network["non_loopback"][:5]),
        )

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

EXPECTED_SCREENSHOTS = {
    *(f"core-{workflow}-{state}.png" for workflow in WORKFLOWS for state in CORE_EXPECT),
    "docx-failed.png",
    "docx-cancelled.png",
    "docx-evidence-missing.png",
    "docx-permission-denied.png",
    "docx-observation-invalid.png",
    "docx-form-unknown.png",
    "docx-stale.png",
    "queue-order.png",
}
actual_screenshots = {path.name for path in SHOTS.glob("*.png")}
check(
    "截图证据清单精确为 17 张",
    actual_screenshots == EXPECTED_SCREENSHOTS,
    f"expected={sorted(EXPECTED_SCREENSHOTS)} actual={sorted(actual_screenshots)}",
)

print(f"\n截图证据目录: {SHOTS}")
print(f"断言总数: {passed + len(failures)}（PASS {passed} / FAIL {len(failures)}）")
if failures:
    print(f"\n{len(failures)} 条断言失败：")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print("\n全部断言通过（仅证明外网合成原型 UI 行为，不证明内网已部署或 REAL）。")
