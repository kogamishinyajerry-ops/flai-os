"""map #32 Destination 终点验收 · 波 1：12 轮造 3 段 + A1–A5 段节奏断言。

栈前提（不起 worker）：
  - 后端审计栈：/tmp/accept_launcher.py（REPO=/tmp/flai-os-accept），127.0.0.1:8620，
    DB /tmp/flai-audit-stack/flai.db，stub 关键词网关（报错/慢/思考/拒绝/超出已审定/计划）。
  - 前端 dev server：127.0.0.1:5202（vite 代理 /api→8620）。
  - 账户 tester/Tester#2026（登录走 JSON 编码 POST /api/auth/login；form 编码 422）。

段语义（workSegments，conversationPlans.js:136）：
  边界 1 = 轮 4「计划」方案卡点「按方案开始」的任务创建戳 → 第 2 段 起；
  边界 2 = 轮 7「超出已审定」guide 级 refuse 终点 → 第 3 段（当前段）起。
  中段（第 2 段，轮 5–7 共 3 轮往来）默认折；首段无段头；当前段分隔线。

A1 三段结构+中段默认折      A4 豁免红线（首泡/最新 AI/当前段不折）
A2 折叠保 DOM 红线          A5 单向展开（展开→切走切回复位）
A3 段界锚时间戳常显

截图落 docs/reviews/map32-accept-shots/。

运行（仓根）：
  uv run --no-project --with playwright --with httpx \
    python frontend/e2e/map32_destination_acceptance.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHOTS = REPO / "docs" / "reviews" / "map32-accept-shots"
BASE = "http://127.0.0.1:5202"
API = "http://127.0.0.1:8620"
USERNAME = "tester"
PASSWORD = "Tester#2026"

CHROMIUM_SNAPSHOT = (
    Path.home()
    / ".chromium-browser-snapshots/chromium/mac_arm-1610067/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx

# ── 12 轮话术（方案表逐字；轮 8–12 避开全部 stub 关键词）────────────────────
ROUNDS = [
    "帮我梳理双通道供电系统的故障模式。",            # 轮1 kind0
    "目前手上没有现成材料，先把目标聊清楚。",        # 轮2 kind1
    "目标是定位供电完全丧失的根因。",                # 轮3 kind2
    "计划：对双通道供电系统做故障树分析。",          # 轮4 → 方案卡（边界 1 由开工造）
    "补充：转换开关在热浸时也抖动过。",              # 轮5 kind0 ┐
    "先按既有输入推进，附件后补。",                  # 轮6 kind1 │ 第 2 段（中段）
    "这件事超出已审定范围，请如实处理。",            # 轮7 refuse=边界 2 ┘
    "根因定位后，处置建议由谁确认口径？",            # 轮8 ┐
    "转换开关抖动的记录我稍后整理成文档。",          # 轮9 │
    "汇流条的历史检修数据需要补充进来。",            # 轮10 │ 第 3 段（当前段）
    "发电机 A 与 B 的切换逻辑想再核对一遍。",        # 轮11 │
    "今天先到这里，后续材料齐了我再发起分析。",      # 轮12 ┘
]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if not ok else ""))


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)

    api = httpx.Client(base_url=API, timeout=10)
    resp = api.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    if resp.status_code != 200:
        sys.exit(f"诚实失败：API 登录 {resp.status_code} {resp.text[:200]}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            browser = p.chromium.launch(executable_path=str(CHROMIUM_SNAPSHOT))
        context = browser.new_context(
            viewport={"width": 1440, "height": 900}, color_scheme="light"
        )
        # 真登录（cookie 与页面共享 jar）；JSON 编码——此后端 form 编码 422。
        auth = context.request.post(
            f"{BASE}/api/auth/login",
            data=json.dumps({"username": USERNAME, "password": PASSWORD}),
            headers={"Content-Type": "application/json"},
        )
        assert auth.ok, f"诚实失败：浏览器上下文登录 {auth.status}"
        page = context.new_page()
        page.goto(BASE + "/", wait_until="networkidle")
        # 主题跟 prefers-color-scheme：确保无 flai_theme_mode 残留后重载定基线。
        page.evaluate("() => localStorage.removeItem('flai_theme_mode')")
        page.reload(wait_until="networkidle")

        composer = page.locator(".composer-input textarea")
        send_btn = page.locator('button.send-btn[aria-label="发送"]')

        def send_round(text: str) -> None:
            before = page.locator(".ai-body").count()
            composer.fill(text)
            send_btn.click()
            page.wait_for_function(
                f"document.querySelectorAll('.ai-body').length > {before}", timeout=30000
            )
            # 等流式播完：stop 按钮换回发送按钮，下一轮才可点。
            send_btn.wait_for(state="visible", timeout=30000)
            page.wait_for_timeout(300)

        # ── 12 轮造段 ──────────────────────────────────────────────────────
        conv_id = ""
        for i, text in enumerate(ROUNDS, start=1):
            send_round(text)
            if i == 1:
                convs = api.get("/api/conversations?limit=1").json()
                lst = convs if isinstance(convs, list) else convs.get("items", [])
                conv_id = lst[0]["id"] if lst else ""
            if i == 4:
                page.locator(".plan-card").last.wait_for(state="visible", timeout=10000)
                # 方案卡唯一主动作：按角色+名字点（绝不用 .open-plan-btn.first）。
                page.get_by_role("button", name="按方案开始").click()
                # 边界 1=任务创建戳：无 worker，任务滞留 queued/created，轮询到账即可。
                deadline = time.time() + 10
                tasks: list[dict] = []
                while time.time() < deadline:
                    raw = api.get(f"/api/conversations/{conv_id}/tasks").json()
                    tasks = raw if isinstance(raw, list) else raw.get("items", [])
                    if tasks:
                        break
                    time.sleep(0.3)
                check("造段前置：轮 4 开工任务创建（边界 1 戳到账）", len(tasks) >= 1,
                      f"tasks={len(tasks)}")
                page.wait_for_timeout(400)

        check("造段：会话 id 取得", bool(conv_id), conv_id)
        print(f"INFO 会话 id = {conv_id}")

        # ── 从侧栏「最近对话」重进该会话 ────────────────────────────────────
        page.goto(BASE + "/", wait_until="networkidle")  # 切走（新对话首页）
        page.locator(".convo-item").first.wait_for(state="visible", timeout=8000)
        page.locator(".convo-item").first.click()
        page.locator(".thread").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(1200)  # 权威会话重渲染 + 段布局稳定

        # ══ A1 三段结构+中段默认折 ═════════════════════════════════════════
        heads = page.locator(".seg-head")
        fold = page.locator("button.seg-fold")
        divider = page.locator(".seg-divider")
        fold_text = fold.inner_text() if fold.count() else "(无 fold 行)"
        div_text = divider.inner_text() if divider.count() else "(无 divider)"
        check(
            "A1 三段结构：段头×2（首段无段头）、fold×1、divider×1",
            heads.count() == 2 and fold.count() == 1 and divider.count() == 1,
            f"heads={heads.count()} fold={fold.count()} divider={divider.count()}",
        )
        check(
            "A1 中段默认折：文案「▸ 3 轮往来 · 第 2 段（HH:MM）」",
            fold.count() == 1
            and "3 轮往来" in fold_text
            and "第 2 段" in fold_text
            and fold_text.strip().startswith("▸"),
            fold_text,
        )
        check("A1 当前段分隔线在场（第 3 段）", divider.count() == 1 and "第 3 段" in div_text, div_text)
        page.screenshot(path=str(SHOTS / "seg_overview_light_1440.png"), full_page=True)

        # ══ A2 折叠保 DOM 红线 ═════════════════════════════════════════════
        folded = page.locator(".bubble-row.seg-folded")
        folded_count = folded.count()
        folded_hidden = folded.evaluate_all(
            "els => els.every(el => !el.checkVisibility())"
        ) if folded_count else False
        mid_user = page.locator(".bubble-row.user", has_text="转换开关在热浸时也抖动过")
        refuse_user = page.locator(".bubble-row.user", has_text="这件事超出已审定范围")
        check(
            "A2 折叠保 DOM：6 条 seg-folded 在 DOM 且全 hidden（非 detached）",
            folded_count == 6 and folded_hidden is True,
            f"folded={folded_count} hidden={folded_hidden}",
        )
        check(
            "A2 轮 5–7 泡不可见（在 DOM）",
            mid_user.count() == 1 and mid_user.is_visible() is False
            and refuse_user.count() == 1 and refuse_user.is_visible() is False,
        )

        # ══ A3 段界锚时间戳 ════════════════════════════════════════════════
        boundary_ops = page.locator(".bubble-time.is-boundary").evaluate_all(
            "els => els.map(el => getComputedStyle(el).opacity)"
        )
        normal_ops = page.locator(".bubble-time:not(.is-boundary)").evaluate_all(
            "els => els.map(el => getComputedStyle(el).opacity)"
        )
        check(
            "A3 段界锚 opacity 恒 1（3 条段界）",
            len(boundary_ops) == 3 and all(o == "1" for o in boundary_ops),
            f"boundary={boundary_ops}",
        )
        check(
            "A3 非段界时间戳 opacity 恒 0（hover-only）",
            len(normal_ops) >= 1 and all(o == "0" for o in normal_ops),
            f"normal[:6]={normal_ops[:6]} total={len(normal_ops)}",
        )
        page.screenshot(path=str(SHOTS / "seg_boundary-anchor_light_1440.png"), full_page=True)

        # ══ A4 豁免红线 ════════════════════════════════════════════════════
        cur_seg_folded = page.evaluate(
            """() => {
              const kids = [...document.querySelectorAll('.thread > div')];
              let lastHead = -1;
              kids.forEach((el, i) => { if (el.classList.contains('seg-head')) lastHead = i; });
              return kids.slice(lastHead + 1)
                .filter(el => el.classList.contains('seg-folded')).length;
            }"""
        )
        first_user_visible = page.locator(".user-bubble").first.is_visible()
        last_ai_visible = page.locator(".ai-body").last.is_visible()
        check("A4 首条 .user-bubble 可见", first_user_visible is True)
        check("A4 最新 .ai-body 可见", last_ai_visible is True)
        check("A4 当前段零 seg-folded", cur_seg_folded == 0, f"cur_seg_folded={cur_seg_folded}")

        # ══ A5 单向展开→切走切回复位 ═══════════════════════════════════════
        fold.click()
        page.wait_for_timeout(500)
        check(
            "A5 展开后中段 6 泡可见、fold 行消失",
            page.locator(".bubble-row.seg-folded").count() == 0
            and page.locator("button.seg-fold").count() == 0
            and mid_user.is_visible() is True,
        )
        check("A5 展开后段分隔线×2（中段抬头为 divider）", page.locator(".seg-divider").count() == 2)
        page.screenshot(path=str(SHOTS / "seg_unfolded_light_1440.png"), full_page=True)
        # 切走切回：unfoldedSegments 换会话清零（GuidePage.vue:2919）。
        page.goto(BASE + "/", wait_until="networkidle")
        page.locator(".convo-item").first.click()
        page.locator(".thread").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(1200)
        check(
            "A5 切走切回复位：fold 行回归、6 泡重折",
            page.locator("button.seg-fold").count() == 1
            and page.locator(".bubble-row.seg-folded").count() == 6,
        )

        browser.close()

    failed = [x for x in results if x[1] is not True]
    print(f"\n{'MAP32 WAVE1 ALL GREEN' if not failed else 'MAP32 WAVE1 FAILED'} "
          f"({len(results) - len(failed)}/{len(results)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
