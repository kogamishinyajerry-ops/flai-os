"""Stage C 工作台原型 UI 行为验收 v3（SYNTHETIC ONLY）。

自包含：启动 frontend vite dev server（需先 npm ci）+ 真 chromium，
仅访问 /stage-c.html 原型页，不连后端、不打真 LLM、不碰 data/。

断言矩阵（对应 work_item flai-stage-c-kimi-uiux-001@3 验证要求）：
  ① docx / meeting / cfd × 九个要求状态（running / waiting_review /
     completed / failed / cancelled / evidence-missing / permission-denied /
     unknown / stale）全遍历：逐组合断言终态 glyph、data-motion、
     信任槽、右栏对象种类；
  ② 合成负例：任何状态下不存在 data-slot=real，页面不出现“有执行见证”，
     徽标必须标注“合成样例 … 非真实见证”；首页未提交时无执行类徽标；
  ③ completed 不给可信绿：hero data-trust=terminal（非 real/sign）；
  ④ cancelled 中性：trust=terminal（不进红 fail）；failed/permission-denied=fail；
  ⑤ 假签发负例：点击“查看签发要求”后无 teal 徽标、无“真人已签发/签发成功”，
     hero 信任槽不变，amber“未签发”徽标保持；
  ⑥ 三栏 Workspace：左上下文轨 / 中央叙事 / 右对象舞台，1440px 下三列；
  ⑦ 1440px 与 1280px：无横向溢出；
  ⑧ prefers-reduced-motion：glyph computed animation-name 为 none；
  ⑨ 键盘：Ctrl+Enter 提交；IME composition 期间快捷键不提交，结束后可提交；
  ⑩ focus-visible：Tab 聚焦后焦点环可见（outline 2px solid）。
  ⑪ 四形态 DOM 矩阵（@3 新增）：REAL/MOCK/TEST 经 reality picker 与
     `?reality=` URL 参数可达，3 场景 × 3 形态逐组合断言徽标文案、
     data-reality-form、data-source-kind、data-slot；UNKNOWN 形态只由
     fail-closed 给出（picker 选 UNKNOWN 强制 unknown 缺口 + 状态选择器禁用）；
  ⑫ P2-1：stale / evidence-missing / unknown 即使带 @REAL 覆盖，徽标一律
     UNKNOWN 未核（fail-closed 优先于形态字段）；
  ⑬ P2-2：permission-denied 默认 REAL 形态徽标（无隐式 MOCK 特例）；
  ⑭ P2-3：failed / cancelled 显示“执行例外”卡且无“原因码”病句，
     观察缺口卡（含原因码）只属 unknown 族。

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

SCENES = ["docx", "meeting", "cfd"]
RUNNING_GLYPH = {"docx": "rewrite", "meeting": "map", "cfd": "inspect"}
# 九个要求状态的逐态期望：glyph / motion / trust / 右栏对象种类
STATE_EXPECT = {
    "running": {"glyph": None, "motion": "true", "trust": "work", "rail": "object"},
    "waiting_review": {"glyph": "wait", "motion": "false", "trust": "work", "rail": "checklist"},
    "completed": {"glyph": "render", "motion": "false", "trust": "terminal", "rail": "frozen"},
    "failed": {"glyph": "failed", "motion": "false", "trust": "fail", "rail": "failed"},
    "cancelled": {"glyph": "cancelled", "motion": "false", "trust": "terminal", "rail": "stopped"},
    "evidence-missing": {"glyph": "unknown", "motion": "false", "trust": "unverified", "rail": "gap"},
    "permission-denied": {"glyph": "failed", "motion": "false", "trust": "fail", "rail": "failed"},
    "unknown": {"glyph": "unknown", "motion": "false", "trust": "unverified", "rail": "gap"},
    "stale": {"glyph": "unknown", "motion": "false", "trust": "unverified", "rail": "gap"},
}


def wait_port(port: int, timeout: float = 60.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        with socket.socket() as sock:
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.3)
    sys.exit(f"诚实失败：vite dev server 端口 {port} 等待超时")


def goto(page, scene: str, state: str, reality: str | None = None):
    url = f"{BASE}/stage-c.html?scene={scene}&state={state}"
    if reality is not None:
        url += f"&reality={reality}"
    page.goto(url)
    page.wait_for_selector("[data-testid='workbench']")


failures: list[str] = []
passed = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global passed
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  ({detail})" if detail else ""))
    if ok:
        passed += 1
    else:
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

        # ②a 首页负例：未提交任务不得出现任何执行类徽标
        page.goto(f"{BASE}/stage-c.html")
        page.wait_for_selector("[data-testid='home']")
        body = page.text_content("body") or ""
        check(
            "首页无执行徽标且无“有执行见证”",
            page.locator("[data-testid='reality-badge']").count() == 0
            and "有执行见证" not in body,
        )
        page.screenshot(path=str(SHOTS / "home.png"), full_page=True)

        # ①+②b 三场景 × 九态全矩阵：glyph / motion / trust / 右栏对象 / 合成负例
        for scene in SCENES:
            for state, expect in STATE_EXPECT.items():
                goto(page, scene, state)
                glyph = page.get_attribute("[data-testid='hero'] .hero-glyph", "data-glyph")
                motion = page.get_attribute("[data-testid='hero'] .hero-glyph", "data-motion")
                trust = page.get_attribute("[data-testid='hero']", "data-trust")
                rail = page.get_attribute("[data-testid='object-card']", "data-rail-kind")
                want_glyph = expect["glyph"] or RUNNING_GLYPH[scene]
                check(
                    f"{scene}:{state} glyph/motion/trust/rail",
                    glyph == want_glyph
                    and motion == expect["motion"]
                    and trust == expect["trust"]
                    and rail == expect["rail"],
                    f"glyph={glyph} motion={motion} trust={trust} rail={rail}",
                )
                badge = page.locator("[data-testid='reality-badge']")
                badge_text = badge.text_content() or ""
                check(
                    f"{scene}:{state} 合成负例（无 real 槽/无见证措辞/标注合成）",
                    page.locator("[data-slot='real']").count() == 0
                    and "有执行见证" not in (page.text_content("body") or "")
                    and "合成样例" in badge_text
                    and "非真实见证" in badge_text,
                    badge_text.strip(),
                )
                step = page.text_content("[data-testid='step-label']") or ""
                if "%" in step:
                    check(f"{scene}:{state} 步骤文案无百分比", False, step)
        page.screenshot(path=str(SHOTS / "matrix-tail.png"), full_page=True)

        # ①b 额外交互状态 validating：guard glyph 且动画开
        goto(page, "cfd", "validating")
        check(
            "cfd:validating glyph=guard 且动画开",
            page.get_attribute("[data-testid='hero'] .hero-glyph", "data-glyph") == "guard"
            and page.get_attribute("[data-testid='hero'] .hero-glyph", "data-motion") == "true",
        )

        # ⑪ 四形态 DOM 矩阵：REAL/MOCK/TEST 经 URL 与 picker 可达，徽标逐形态断言
        for scene in SCENES:
            for form in ("REAL", "MOCK", "TEST"):
                goto(page, scene, "running", reality=form)
                badge = page.locator("[data-testid='reality-badge']")
                badge_text = badge.text_content() or ""
                check(
                    f"{scene}:running@{form} 形态徽标 DOM",
                    f"合成样例 · {form} 形态测试 · 非真实见证" in badge_text
                    and badge.get_attribute("data-reality-form") == form
                    and badge.get_attribute("data-source-kind") == "synthetic-fixture"
                    and badge.get_attribute("data-slot") == "test"
                    and page.locator("[data-slot='real']").count() == 0
                    and "有执行见证" not in (page.text_content("body") or ""),
                    badge_text.strip(),
                )
        # ⑪b 四形态在终态同样成立（形态不随状态漂移）
        for form in ("REAL", "MOCK", "TEST"):
            goto(page, "docx", "completed", reality=form)
            badge = page.locator("[data-testid='reality-badge']")
            check(
                f"docx:completed@{form} 形态徽标保持",
                badge.get_attribute("data-reality-form") == form
                and f"合成样例 · {form} 形态测试" in (badge.text_content() or ""),
            )
        # ⑪c UNKNOWN 形态：picker 选 UNKNOWN 强制 fail-closed 缺口，状态选择器禁用
        for scene in SCENES:
            goto(page, scene, "running", reality="UNKNOWN")
            badge = page.locator("[data-testid='reality-badge']")
            check(
                f"{scene}: UNKNOWN 形态强制 fail-closed 缺口徽标",
                badge.get_attribute("data-reality-form") == "UNKNOWN"
                and badge.get_attribute("data-slot") == "unverified"
                and "UNKNOWN 形态 · 未核，非真实见证" in (badge.text_content() or "")
                and page.get_attribute("[data-testid='object-card']", "data-rail-kind") == "gap",
            )
        goto(page, "docx", "running", reality="UNKNOWN")
        check(
            "UNKNOWN 形态下状态选择器禁用且有诚实提示",
            page.locator("[data-testid='state-picker']").is_disabled()
            and page.locator("[data-testid='unknown-form-hint']").is_visible(),
        )
        # ⑪d picker 交互：切 MOCK 徽标即时更新；非法 URL 形态参数 fail-closed 回 REAL
        goto(page, "docx", "running")
        page.select_option("[data-testid='reality-picker']", "MOCK")
        check(
            "reality picker 切换 MOCK 后徽标即时更新",
            page.locator("[data-testid='reality-badge']").get_attribute("data-reality-form") == "MOCK",
        )
        goto(page, "docx", "running", reality="FAKE")
        check(
            "非法 reality URL 参数 fail-closed 回 REAL 形态",
            page.locator("[data-testid='reality-badge']").get_attribute("data-reality-form") == "REAL",
        )

        # ⑫ P2-1：fail-closed 状态一律 UNKNOWN 未核徽标（stale 不得保留 REAL 形态）
        for scene in SCENES:
            for state in ("stale", "evidence-missing", "unknown"):
                goto(page, scene, state, reality="REAL")
                badge = page.locator("[data-testid='reality-badge']")
                check(
                    f"{scene}:{state}@REAL fail-closed 压到 UNKNOWN 徽标",
                    badge.get_attribute("data-reality-form") == "UNKNOWN"
                    and badge.get_attribute("data-slot") == "unverified"
                    and "未核，非真实见证" in (badge.text_content() or ""),
                )

        # ⑬ P2-2：permission-denied 默认 REAL 形态（无隐式 MOCK 特例）
        for scene in SCENES:
            goto(page, scene, "permission-denied")
            badge = page.locator("[data-testid='reality-badge']")
            check(
                f"{scene}:permission-denied 默认 REAL 形态徽标",
                badge.get_attribute("data-reality-form") == "REAL"
                and "合成样例 · REAL 形态测试 · 非真实见证" in (badge.text_content() or ""),
            )

        # ⑭ P2-3：failed/cancelled 例外卡无“原因码”病句；缺口卡只属 unknown 族
        for state in ("failed", "cancelled"):
            goto(page, "docx", state)
            card = page.locator("[data-testid='exception-card']")
            check(
                f"docx:{state} 执行例外卡可见且无原因码行",
                card.is_visible()
                and card.get_attribute("data-card-kind") == "exception"
                and "原因码" not in (card.text_content() or "")
                and page.locator("[data-testid='gap-card']").count() == 0,
            )
        goto(page, "docx", "unknown")
        check(
            "docx:unknown 缺口卡含原因码且无例外卡",
            page.locator("[data-testid='gap-card']").is_visible()
            and "原因码" in (page.locator("[data-testid='gap-card']").text_content() or "")
            and page.locator("[data-testid='exception-card']").count() == 0,
        )

        # ③ completed 终态 glyph 静止且不给绿（矩阵已逐场景断言，这里截图留证）
        goto(page, "docx", "completed")
        page.screenshot(path=str(SHOTS / "docx-completed.png"), full_page=True)

        # ④ cancelled 中性截图留证（矩阵已断言 trust=terminal）
        goto(page, "docx", "cancelled")
        page.screenshot(path=str(SHOTS / "docx-cancelled.png"), full_page=True)

        # fail-closed 缺口卡原因码
        for state, reason in [
            ("evidence-missing", "observation_invalid"),
            ("unknown", "observation_missing"),
            ("stale", "observation_stale"),
        ]:
            goto(page, "meeting", state)
            gap = page.locator("[data-testid='gap-card']")
            check(
                f"meeting:{state} 缺口卡可见且原因码 {reason}",
                gap.is_visible() and reason in (gap.text_content() or ""),
            )
        page.screenshot(path=str(SHOTS / "meeting-gap.png"), full_page=True)

        # ⑤ 假签发负例：teal 路径不可达
        goto(page, "docx", "waiting_review")
        check(
            "waiting_review 交付区与 amber 未签发徽标可见",
            page.locator("[data-testid='delivery']").is_visible()
            and page.locator("[data-testid='unsigned-badge']").is_visible()
            and page.get_attribute("[data-testid='unsigned-badge']", "data-slot") == "unverified",
        )
        page.click("[data-testid='sign-requirements-button']")
        req = page.locator("[data-testid='sign-requirements']")
        req_text = req.text_content() or ""
        body = page.text_content("body") or ""
        check(
            "签发要求可见（认证主体/时间/版本/receipt）",
            req.is_visible()
            and "认证主体" in req_text
            and "receipt" in req_text,
        )
        check(
            "点击后无 teal 签发（无 sign 槽/无已签发措辞/信任槽不变）",
            page.locator("[data-slot='sign']").count() == 0
            and "真人已签发" not in body
            and "签发成功" not in body
            and page.get_attribute("[data-testid='hero']", "data-trust") == "work",
        )
        page.screenshot(path=str(SHOTS / "docx-sign-requirements.png"), full_page=True)

        # ⑥ 三栏 Workspace 结构
        goto(page, "docx", "running")
        left = page.locator("[data-testid='left-rail']")
        left_text = left.text_content() or ""
        columns = page.evaluate(
            "getComputedStyle(document.querySelector('[data-testid=\"workbench\"]')).gridTemplateColumns"
        )
        check(
            "三栏：左上下文轨可见且含 项目/最近工作/知识上下文",
            left.is_visible()
            and "当前项目" in left_text
            and "最近工作" in left_text
            and "获准知识上下文" in left_text,
        )
        check("三栏：1440px 下 workbench 为三列", len(columns.split()) == 3, columns)
        page.screenshot(path=str(SHOTS / "docx-running-three-pane.png"), full_page=True)

        # ⑦ 1440 / 1280 无横向溢出
        for width in (1440, 1280):
            page.set_viewport_size({"width": width, "height": 900})
            goto(page, "cfd", "running")
            overflow = page.evaluate(
                "document.documentElement.scrollWidth > document.documentElement.clientWidth"
            )
            check(f"{width}px 无横向溢出", not overflow)

        # ⑧ reduced motion 停动画
        page.emulate_media(reduced_motion="reduce")
        goto(page, "docx", "running")
        anim = page.eval_on_selector(
            "[data-testid='hero'] .hero-glyph .g-dash",
            "el => getComputedStyle(el).animationName",
        )
        check("reduced-motion 下 glyph 动画为 none", anim == "none", anim)
        page.emulate_media(reduced_motion="no-preference")

        # ⑨a 键盘提交：首页 Ctrl+Enter → 工作台
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

        # ⑨b IME composition 期间快捷键不提交，结束后可提交（首页 Composer）
        page.goto(f"{BASE}/stage-c.html")
        page.wait_for_selector("[data-testid='home']")
        page.fill("[data-testid='composer'] textarea", "输入中途")
        page.eval_on_selector(
            "[data-testid='composer'] textarea",
            """el => {
              el.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
              el.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter', ctrlKey: true, bubbles: true, cancelable: true, isComposing: true,
              }));
            }""",
        )
        check(
            "IME composition 中 Ctrl+Enter 不提交（仍在首页）",
            page.locator("[data-testid='workbench']").count() == 0
            and page.locator("[data-testid='home']").is_visible(),
        )
        page.eval_on_selector(
            "[data-testid='composer'] textarea",
            "el => el.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true }))",
        )
        page.press("[data-testid='composer'] textarea", "Control+Enter")
        page.wait_for_selector("[data-testid='workbench']")
        check("IME composition 结束后 Ctrl+Enter 可提交", True)

        # ⑨c 工作台 Composer 同样防 IME 误提交
        goto(page, "docx", "running")
        page.fill("[data-testid='composer'] textarea", "追加一条修正")
        page.eval_on_selector(
            "[data-testid='composer'] textarea",
            """el => {
              el.dispatchEvent(new CompositionEvent('compositionstart', { bubbles: true }));
              el.dispatchEvent(new KeyboardEvent('keydown', {
                key: 'Enter', metaKey: true, bubbles: true, cancelable: true, isComposing: true,
              }));
            }""",
        )
        check(
            "工作台 IME composition 中 ⌘+Enter 不清空不提交",
            page.input_value("[data-testid='composer'] textarea") == "追加一条修正",
        )
        page.eval_on_selector(
            "[data-testid='composer'] textarea",
            "el => el.dispatchEvent(new CompositionEvent('compositionend', { bubbles: true }))",
        )
        page.press("[data-testid='composer'] textarea", "Control+Enter")
        check(
            "工作台 composition 结束后可提交",
            page.input_value("[data-testid='composer'] textarea") == "",
        )

        # ⑩ focus-visible 焦点环
        page.goto(f"{BASE}/stage-c.html")
        page.wait_for_selector("[data-testid='home']")
        page.keyboard.press("Tab")
        outline = page.evaluate(
            """() => {
              const el = document.activeElement;
              const cs = getComputedStyle(el);
              return { tag: el.tagName, style: cs.outlineStyle, width: cs.outlineWidth };
            }"""
        )
        check(
            "focus-visible 焦点环可见（2px solid）",
            outline["style"] == "solid" and outline["width"] == "2px",
            f"{outline['tag']} outline={outline['width']} {outline['style']}",
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

print(f"\n截图证据目录: {SHOTS}")
print(f"断言总数: {passed + len(failures)}（PASS {passed} / FAIL {len(failures)}）")
if failures:
    print(f"\n{len(failures)} 条断言失败：")
    for item in failures:
        print(f"  - {item}")
    sys.exit(1)
print("\n全部断言通过（仅证明外网合成原型 UI 行为，不证明内网已部署或 REAL）。")
