"""map #32 Destination 终点验收 · 波 2a：A6（暗 1440）/ A7（亮 375）/ A8（暗 375）
段节奏复判 + E7 窄屏 dock + C2 零待签今日页窗口。

栈前提同波 1（不起 worker）：后端 127.0.0.1:8620，前端 127.0.0.1:5202，
造段会话 conv_c52ca8c5e4dc4a7bb9aaaf936a07e993（12 轮 3 段，波 1 已造）。

复判口径 = 波 1 A1–A4 同标准（段头×2/fold×1/divider×1、6 条 seg-folded 保 DOM
hidden、段界锚 opacity 恒 1 vs 非段界恒 0、首泡/最新 AI 可见/当前段零折叠）；
375 加无横向溢出（documentElement.scrollWidth <= 375）。

C2：当前零 waiting_review 窗口（worker 未起），今日页首行摘要 .today-summary
不渲染、待签发组头无「· 0」后缀。

E7：375 下 @media≤860px .dock-pill display:none（探针注入断言，因零态本不渲染
pill），只余 .dock-core 核心钮；dock 居右不遮左侧汉堡/标题区。

截图落 docs/reviews/map32-accept-shots/。

运行（仓根）：
  UV_OFFLINE=1 uv run --no-project --with playwright --with httpx \
    python frontend/e2e/map32_destination_acceptance_wave2a.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHOTS = REPO / "docs" / "reviews" / "map32-accept-shots"
BASE = "http://127.0.0.1:5202"
API = "http://127.0.0.1:8620"
USERNAME = "tester"
PASSWORD = "Tester#2026"
CONV_ID = "conv_c52ca8c5e4dc4a7bb9aaaf936a07e993"

CHROMIUM_SNAPSHOT = (
    Path.home()
    / ".chromium-browser-snapshots/chromium/mac_arm-1610067/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if not ok else ""))


def seg_assertions(page, tag: str) -> None:
    """A1–A4 同标准复判（在已进入会话、thread 稳定后调用）。"""
    heads = page.locator(".seg-head")
    fold = page.locator("button.seg-fold")
    divider = page.locator(".seg-divider")
    fold_text = fold.inner_text() if fold.count() else "(无 fold 行)"
    div_text = divider.inner_text() if divider.count() else "(无 divider)"
    check(
        f"{tag} A1 三段结构：段头×2、fold×1、divider×1",
        heads.count() == 2 and fold.count() == 1 and divider.count() == 1,
        f"heads={heads.count()} fold={fold.count()} divider={divider.count()}",
    )
    check(
        f"{tag} A1 中段默认折：「▸ 3 轮往来 · 第 2 段」",
        fold.count() == 1
        and "3 轮往来" in fold_text
        and "第 2 段" in fold_text
        and fold_text.strip().startswith("▸"),
        fold_text,
    )
    check(
        f"{tag} A1 当前段分隔线（第 3 段）",
        divider.count() == 1 and "第 3 段" in div_text,
        div_text,
    )
    folded = page.locator(".bubble-row.seg-folded")
    folded_count = folded.count()
    folded_hidden = folded.evaluate_all(
        "els => els.every(el => !el.checkVisibility())"
    ) if folded_count else False
    check(
        f"{tag} A2 折叠保 DOM：6 条 seg-folded 在 DOM 且全 hidden",
        folded_count == 6 and folded_hidden is True,
        f"folded={folded_count} hidden={folded_hidden}",
    )
    mid_user = page.locator(".bubble-row.user", has_text="转换开关在热浸时也抖动过")
    check(
        f"{tag} A2 轮 5–7 泡不可见（在 DOM）",
        mid_user.count() == 1 and mid_user.is_visible() is False,
    )
    # 375 抽屉点击后鼠标残留在 thread 上方会触发 .bubble-row:hover 显示时间戳
    # （样式溯源：仅 hover/focus-within 可让非段界 .bubble-time opacity=1）——
    # 量测前把鼠标移到顶带中性位，排除测试伪影。
    page.mouse.move(2, 2)
    page.wait_for_timeout(250)
    boundary_ops = page.locator(".bubble-time.is-boundary").evaluate_all(
        "els => els.map(el => getComputedStyle(el).opacity)"
    )
    normal_ops = page.locator(".bubble-time:not(.is-boundary)").evaluate_all(
        "els => els.map(el => getComputedStyle(el).opacity)"
    )
    check(
        f"{tag} A3 段界锚 opacity 恒 1（3 条）",
        len(boundary_ops) == 3 and all(o == "1" for o in boundary_ops),
        f"boundary={boundary_ops}",
    )
    check(
        f"{tag} A3 非段界时间戳 opacity 恒 0",
        len(normal_ops) >= 1 and all(o == "0" for o in normal_ops),
        f"total={len(normal_ops)}",
    )
    cur_seg_folded = page.evaluate(
        """() => {
          const kids = [...document.querySelectorAll('.thread > div')];
          let lastHead = -1;
          kids.forEach((el, i) => { if (el.classList.contains('seg-head')) lastHead = i; });
          return kids.slice(lastHead + 1)
            .filter(el => el.classList.contains('seg-folded')).length;
        }"""
    )
    check(f"{tag} A4 首条 .user-bubble 可见", page.locator(".user-bubble").first.is_visible() is True)
    check(f"{tag} A4 最新 .ai-body 可见", page.locator(".ai-body").last.is_visible() is True)
    check(f"{tag} A4 当前段零 seg-folded", cur_seg_folded == 0, f"cur={cur_seg_folded}")


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)

    api = httpx.Client(base_url=API, timeout=10)
    resp = api.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    if resp.status_code != 200:
        sys.exit(f"诚实失败：API 登录 {resp.status_code} {resp.text[:200]}")

    # C2 前置：确认当前确为零 waiting_review 窗口（worker 未起）。
    raw = api.get("/api/tasks").json()
    tasks = raw if isinstance(raw, list) else raw.get("items", [])
    waiting = [t for t in tasks if t.get("status") == "waiting_review"]
    check("C2 前置：零 waiting_review 窗口成立", len(waiting) == 0,
          f"waiting={len(waiting)} statuses={sorted({t.get('status') for t in tasks})}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            browser = p.chromium.launch(executable_path=str(CHROMIUM_SNAPSHOT))

        def new_ctx(width: int, height: int, scheme: str):
            context = browser.new_context(
                viewport={"width": width, "height": height}, color_scheme=scheme
            )
            auth = context.request.post(
                f"{BASE}/api/auth/login",
                data=json.dumps({"username": USERNAME, "password": PASSWORD}),
                headers={"Content-Type": "application/json"},
            )
            assert auth.ok, f"诚实失败：浏览器上下文登录 {auth.status}"
            page = context.new_page()
            page.goto(BASE + "/", wait_until="networkidle")
            page.evaluate("() => localStorage.removeItem('flai_theme_mode')")
            page.reload(wait_until="networkidle")
            return context, page

        def reenter_via_sidebar(page) -> None:
            """切走→从侧栏最近对话重进造段会话（375 走汉堡抽屉，语义同）。"""
            page.goto(BASE + "/", wait_until="networkidle")
            item = page.locator(f'a.convo-item[href*="{CONV_ID}"]')
            # ≤860px 侧栏收起为抽屉（元素在 DOM 但屏外，is_visible 不可靠），
            # 必须经汉堡唤出；路由 watch 会在跳转后自动收起抽屉。
            if page.locator(".sb-hamburger").is_visible():
                page.locator(".sb-hamburger").click()
            item.wait_for(state="visible", timeout=8000)
            item.click()
            page.locator(".thread").wait_for(state="visible", timeout=8000)
            page.wait_for_timeout(1200)

        # ══ A6 暗 1440 复判 A1–A4 ═════════════════════════════════════════
        ctx, page = new_ctx(1440, 900, "dark")
        reenter_via_sidebar(page)
        seg_assertions(page, "A6[dark/1440]")
        page.screenshot(path=str(SHOTS / "seg_overview_dark_1440.png"), full_page=True)
        # 展开中段取 unfolded 图（A6 口径含展开后暗色可辨）
        page.locator("button.seg-fold").click()
        page.wait_for_timeout(500)
        check(
            "A6[dark/1440] 展开后中段 6 泡可见、fold 行消失",
            page.locator(".bubble-row.seg-folded").count() == 0
            and page.locator("button.seg-fold").count() == 0
            and page.locator(".bubble-row.user", has_text="转换开关在热浸时也抖动过").is_visible() is True,
        )
        page.screenshot(path=str(SHOTS / "seg_unfolded_dark_1440.png"), full_page=True)
        ctx.close()

        # ══ A7 亮 375 复判 + 无横向溢出 + E7 ═════════════════════════════
        ctx, page = new_ctx(375, 812, "light")
        reenter_via_sidebar(page)
        seg_assertions(page, "A7[light/375]")
        sw = page.evaluate("() => document.documentElement.scrollWidth")
        bw = page.evaluate("() => document.body.scrollWidth")
        check("A7[light/375] 无横向溢出 scrollWidth<=375", sw <= 375 and bw <= 375,
              f"doc={sw} body={bw}")
        page.screenshot(path=str(SHOTS / "seg_overview_light_375.png"), full_page=True)

        # E7 窄屏 dock：零态 pill 本不渲染，注入探针断言媒体查询 display:none。
        # scoped 样式要求探针带上 StatusDock 的 data-v 属性（否则选择器不匹配，
        # 量到的是 UA 默认 display）。
        pill_display = page.evaluate(
            """() => {
              const dock = document.querySelector('.status-dock');
              if (!dock) return null;
              const attrs = [...dock.attributes].filter(a => a.name.startsWith('data-v-'));
              const probe = document.createElement('span');
              probe.className = 'dock-pill dock-pill-waiting';
              attrs.forEach(a => probe.setAttribute(a.name, a.value));
              probe.textContent = '✍ 待你签发 1';
              dock.prepend(probe);
              const d = getComputedStyle(probe).display;
              probe.remove();
              return d;
            }"""
        )
        check("E7 375 下 .dock-pill 媒体查询 display:none（探针注入）",
              pill_display == "none", f"display={pill_display}")
        core_visible = page.locator(".dock-core").is_visible()
        check("E7 375 下只余核心钮 .dock-core 可见", core_visible is True)
        overlap = page.evaluate(
            """() => {
              const dock = document.querySelector('.status-dock').getBoundingClientRect();
              const ham = document.querySelector('.sb-hamburger').getBoundingClientRect();
              const title = document.querySelector('.app-main');
              return { dock: {top: dock.top, right: dock.right, bottom: dock.bottom, left: dock.left},
                       ham: {left: ham.left, right: ham.right, top: ham.top},
                       vw: window.innerWidth,
                       noOverlapHam: dock.left >= ham.right,
                       inViewport: dock.right <= window.innerWidth && dock.top >= 0 && dock.bottom <= 60 };
            }"""
        )
        check("E7 dock 居右贴边不遮汉堡/标题区（顶带内）",
              bool(overlap) and overlap["noOverlapHam"] and overlap["inViewport"],
              json.dumps(overlap, ensure_ascii=False) if overlap else "no dock")
        page.screenshot(path=str(SHOTS / "e7_dock_light_375.png"), full_page=False)
        ctx.close()

        # ══ A8 暗 375 复判 + 无横向溢出 ═══════════════════════════════════
        ctx, page = new_ctx(375, 812, "dark")
        reenter_via_sidebar(page)
        seg_assertions(page, "A8[dark/375]")
        sw = page.evaluate("() => document.documentElement.scrollWidth")
        bw = page.evaluate("() => document.body.scrollWidth")
        check("A8[dark/375] 无横向溢出 scrollWidth<=375", sw <= 375 and bw <= 375,
              f"doc={sw} body={bw}")
        page.screenshot(path=str(SHOTS / "seg_overview_dark_375.png"), full_page=True)
        ctx.close()

        # ══ C2 零待签今日页（亮 1440）══════════════════════════════════════
        ctx, page = new_ctx(1440, 900, "light")
        page.goto(BASE + "/today", wait_until="networkidle")
        page.wait_for_timeout(800)
        summary_count = page.locator(".today-summary").count()
        sign_head = page.locator(".today-section-head.waiting").inner_text()
        check("C2 零待签：首行摘要 .today-summary 不渲染", summary_count == 0,
              f"count={summary_count}")
        check("C2 零待签：待签发组头无「· 0」", "·" not in sign_head and "0" not in sign_head,
              sign_head)
        page.screenshot(path=str(SHOTS / "ia_today-zero_light_1440.png"), full_page=True)
        ctx.close()

        browser.close()

    failed = [x for x in results if x[1] is not True]
    print(f"\n{'MAP32 WAVE2A ALL GREEN' if not failed else 'MAP32 WAVE2A FAILED'} "
          f"({len(results) - len(failed)}/{len(results)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
