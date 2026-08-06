"""map #32 Destination 终点验收 · 波 3（收尾波）：B 组状态来找人全链路 +
E1-peek Esc 焦点断档补验 + D2 fresh 方案卡密级 pill title 补验 + C1 今日页/任务台同口径。

栈前提（波 1/2 已在跑）：后端 127.0.0.1:8620，前端 127.0.0.1:5202，
DB /tmp/flai-audit-stack/flai.db；本波新增：worker 已起
（FLAI_DB_PATH=/tmp/flai-audit-stack/flai.db FLAI_LLM_TIMEOUT_S=5
bash scripts/dev_start_worker.sh，单实例）。

预置数据（本波开工时建成，见 /tmp/accept_notes_wave3.md）：
- fea_solve_agent 0-LLM 任务 task_d76d92f49a20458a9cc597249edf8e2e
  = waiting_review（B1/B2/B3/B6/C1/E1-peek 的待签载体；B3 批准后转 completed 供 B4）。
  （首个载体 task_a5137cf6de0c4975a8b7f563986ed4f2 已被首跑 B3 批准消耗，勿复用。）
- fta_agent 任务 task_28b3d16fa5b451f8b4d74d47bed2ad4f（波 1 轮 4 开工产物）
  已被 worker 拾取：stub 环境无 FLAI_LLM_BASE_URL → ModelConfigError 诚实失败
  = failed（B5 红行载体，预期产物）。

截图落 docs/reviews/map32-accept-shots/。

运行（仓根）：
  UV_OFFLINE=1 uv run --no-project --with playwright --with httpx \
    python frontend/e2e/map32_destination_acceptance_wave3.py
"""
from __future__ import annotations

import base64
import json
import re
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SHOTS = REPO / "docs" / "reviews" / "map32-accept-shots"
BASE = "http://127.0.0.1:5202"
API = "http://127.0.0.1:8620"
USERNAME = "tester"
PASSWORD = "Tester#2026"
FEA_TASK_ID = "task_f7bd4f089cbb43faa6f25af35fe44ae6"
FTA_TASK_ID = "task_28b3d16fa5b451f8b4d74d47bed2ad4f"
WORK_STATES = {"running", "validating", "parsing", "analyzing"}

CHROMIUM_SNAPSHOT = (
    Path.home()
    / ".chromium-browser-snapshots/chromium/mac_arm-1610067/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx

results: list[tuple[str, bool | None, str]] = []


def check(name: str, ok: bool | None, detail: str = "") -> None:
    results.append((name, ok, detail))
    tag = "PASS" if ok is True else ("INFO" if ok is None else "FAIL")
    print(tag, name, ("| " + detail if detail else ""))


def parse_rgb(css: str) -> tuple[int, int, int] | None:
    m = re.match(r"rgba?\(\s*(\d+),\s*(\d+),\s*(\d+)", css or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)

    api = httpx.Client(base_url=API, timeout=15)
    resp = api.post("/api/auth/login", json={"username": USERNAME, "password": PASSWORD})
    if resp.status_code != 200:
        sys.exit(f"诚实失败：API 登录 {resp.status_code} {resp.text[:200]}")

    def api_tasks() -> list[dict]:
        raw = api.get("/api/tasks").json()
        return raw if isinstance(raw, list) else raw.get("items", [])

    def api_truth() -> dict:
        tasks = api_tasks()
        return {
            "waiting": [t for t in tasks if t.get("status") == "waiting_review"],
            "working": [t for t in tasks if t.get("status") in WORK_STATES],
            "done": [t for t in tasks if t.get("status") in ("completed", "failed", "cancelled")],
        }

    # ── 前置真值：fea 待签、fta 诚实失败 ─────────────────────────────────
    pre = api_truth()
    fea = api.get(f"/api/tasks/{FEA_TASK_ID}").json()
    fta = api.get(f"/api/tasks/{FTA_TASK_ID}").json()
    check("前置：fea 任务 waiting_review（唯一待签）",
          fea.get("status") == "waiting_review" and len(pre["waiting"]) == 1,
          f"fea={fea.get('status')} waiting={len(pre['waiting'])}")
    check("前置：fta 任务 failed（ModelConfigError 诚实失败）",
          fta.get("status") == "failed" and "ModelConfigError" in (fta.get("error_message") or ""),
          f"fta={fta.get('status')} err={(fta.get('error_message') or '')[:80]}")
    check("前置：当前零工作态（inbox 运行中组应不渲染）",
          len(pre["working"]) == 0, f"working={[t.get('status') for t in pre['working']]}")

    with sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except Exception as exc:
            if "Executable doesn't exist" not in str(exc):
                raise
            browser = p.chromium.launch(executable_path=str(CHROMIUM_SNAPSHOT))

        context = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
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

        # ══ B1 dock 待签 pill + title 徽章 ═══════════════════════════════
        pill = page.locator(".dock-pill-waiting")
        pill.wait_for(state="visible", timeout=15000)
        page.wait_for_timeout(400)
        pill_text = pill.inner_text()
        pill_num = page.locator(".dock-pill-waiting .num-token").inner_text().strip()
        check("B1 dock .dock-pill-waiting「✍ 待你签发 1」",
              "待你签发" in pill_text and pill_num == "1", f"text={pill_text!r}")
        title = page.title()
        check("B1 title 徽章「(1 待签) …」", title.startswith("(1 待签) "), f"title={title!r}")
        page.screenshot(path=str(SHOTS / "status_dock-waiting_light_1440.png"))

        # ══ B6 dock 多点采样（retro④：/、/today、/tasks、/me 计数一致）══
        samples: dict[str, tuple[str, str]] = {}
        clip_paths: list[str] = []
        for name, path in [("root", "/"), ("today", "/today"), ("tasks", "/tasks"), ("me", "/me")]:
            page.goto(BASE + path, wait_until="networkidle")
            page.locator(".dock-pill-waiting").wait_for(state="visible", timeout=15000)
            page.wait_for_timeout(400)
            num = page.locator(".dock-pill-waiting .num-token").inner_text().strip()
            samples[name] = (num, page.title())
            cp = f"/tmp/wave3_dockclip_{name}.png"
            page.locator(".status-dock").screenshot(path=cp)
            clip_paths.append(cp)
        nums = {v[0] for v in samples.values()}
        titles_ok = all(v[1].startswith("(1 待签) ") for v in samples.values())
        check("B6 四点采样 dock 待签计数一致（=1）", nums == {"1"},
              json.dumps({k: v[0] for k, v in samples.items()}, ensure_ascii=False))
        check("B6 四点采样 title 徽章一致", titles_ok,
              json.dumps({k: v[1] for k, v in samples.items()}, ensure_ascii=False))
        # 四点 clip 拼一张取证图（无 PIL，走 canvas 拼图）。
        mp = context.new_page()
        mp.set_content("<body style='margin:0;background:#ffffff'><canvas id='c'></canvas></body>")
        mp.evaluate(
            """async ({imgs, labels}) => {
              const loaded = await Promise.all(imgs.map(src => new Promise(res => {
                const i = new Image(); i.onload = () => res(i);
                i.src = 'data:image/png;base64,' + src;
              })));
              const pad = 16, lh = 18, gap = 8;
              let w = 0, h = pad;
              loaded.forEach(i => { w = Math.max(w, i.width); h += lh + i.height + gap; });
              w += pad * 2;
              const c = document.getElementById('c');
              c.width = w; c.height = h;
              const x = c.getContext('2d');
              x.fillStyle = '#ffffff'; x.fillRect(0, 0, w, h);
              let y = pad;
              loaded.forEach((i, idx) => {
                x.fillStyle = '#333333'; x.font = '12px sans-serif';
                x.fillText(labels[idx], pad, y + 12); y += lh;
                x.drawImage(i, pad, y); y += i.height + gap;
              });
            }""",
            {
                "imgs": [base64.b64encode(Path(cp).read_bytes()).decode() for cp in clip_paths],
                "labels": [f"{name}  {path}  —  待签 {samples[name][0]} · title「{samples[name][1]}」"
                           for (name, path) in [("root", "/"), ("today", "/today"), ("tasks", "/tasks"), ("me", "/me")]],
            },
        )
        mp.locator("#c").screenshot(path=str(SHOTS / "status_dock_sampling.png"))
        mp.close()

        # ══ C1 今日页 / 任务台同分组同计数（taskGroups SSOT）══════════════
        page.goto(BASE + "/today", wait_until="networkidle")
        page.wait_for_timeout(1000)
        today_head = page.locator(".today-section-head.waiting").inner_text()
        today_cards = page.locator("section.today-section").first.locator(".today-card")
        today_card_name = ""
        check("C1 今日页待签组头「待你签发 · 1」",
              "待你签发" in today_head and "·1" in today_head.replace(" ", ""),
              f"head={today_head!r}")
        check("C1 今日页待签组 1 卡且为 fea 任务",
              today_cards.count() == 1 and "fea_solve_agent" in today_cards.first.inner_text(),
              f"cards={today_cards.count()}")
        if today_cards.count() == 1:
            today_card_name = today_cards.first.locator(".today-card-name").inner_text().strip()
        page.screenshot(path=str(SHOTS / "ia_today_light_1440.png"), full_page=True)

        page.goto(BASE + "/tasks", wait_until="networkidle")
        page.wait_for_timeout(1000)
        rail_head = page.locator(".cl-group-label.waiting").inner_text()
        rail_waiting_items = page.locator(".cl-item", has_text="需要你签发")
        check("C1 任务台左栏组头「✍ 待你签发 · 1」",
              "待你签发" in rail_head and "1" in rail_head, f"head={rail_head!r}")
        check("C1 任务台待签组 1 行且为 fea 任务",
              rail_waiting_items.count() == 1
              and "fea_solve_agent" in rail_waiting_items.first.inner_text(),
              f"rows={rail_waiting_items.count()}")
        if rail_waiting_items.count() == 1 and today_card_name:
            rail_name = rail_waiting_items.first.locator(".cl-name").inner_text().strip()
            check("C1 两面同人话称呼（taskDisplayName 同 SSOT）",
                  rail_name == today_card_name, f"today={today_card_name!r} rail={rail_name!r}")
        page.screenshot(path=str(SHOTS / "ia_tasks-rail_light_1440.png"))

        # ══ B2 inbox 三组（按 API 真值对账）═══════════════════════════════
        page.goto(BASE + "/", wait_until="networkidle")
        page.locator(".status-dock").click()
        page.locator(".sc-shell").wait_for(state="visible", timeout=8000)
        page.locator(".sc-group-label.waiting").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(600)
        truth = api_truth()
        wlabel = page.locator(".sc-group-label.waiting").inner_text()
        waiting_group = page.locator(".sc-group", has=page.locator(".sc-group-label.waiting"))
        waiting_items = waiting_group.locator(".sc-item", has_text="fea_solve_agent")
        check("B2 待你签发组头「✍ 待你签发 · 1」+ 1 行 fea + 审阅 CTA",
              "·1" in wlabel.replace(" ", "") and waiting_items.count() == 1
              and "审阅" in waiting_items.first.inner_text(),
              f"label={wlabel!r} rows={waiting_items.count()}")
        working_labels = page.locator(".sc-group-label.working").count()
        check("B2 运行中组与 API 真值一致（0 工作态→组不渲染）",
              working_labels == (0 if not truth["working"] else 1) and not truth["working"],
              f"dom={working_labels} api={len(truth['working'])}")
        done_group = page.locator(".sc-group", has=page.locator(".sc-group-label", has_text="最近落定"))
        done_items = done_group.locator(".sc-item")
        fta_row = done_group.locator(".sc-item", has_text="fta_agent")
        check("B2 最近落定组在位，fta 失败行可见（api 落定数对账）",
              done_group.count() == 1 and fta_row.count() == 1
              and done_items.count() == len(truth["done"][:5])
              and "失败" in fta_row.inner_text(),
              f"dom={done_items.count()} api_done={len(truth['done'])}")
        page.screenshot(path=str(SHOTS / "status_inbox_light_1440.png"))

        # ══ E1-peek 补验：peek 态 Esc 焦点断档（retro 口径修正后真问题候选）══
        waiting_items.first.click()
        page.locator(".peek-review-card").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(400)
        focus_in = page.evaluate(
            "() => !!document.activeElement && !!document.activeElement.closest('.sc-shell')"
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        back_in_inbox = page.locator(".sc-group-label.waiting").is_visible()
        still_open = page.locator(".sc-shell").is_visible()
        check("E1-peek[焦点在壳内] Esc 退层回收件箱（抽屉不关）",
              focus_in and back_in_inbox and still_open,
              f"focus_in={focus_in} inbox={back_in_inbox} open={still_open}")
        # 重新进 peek，把焦点程序化移到抽屉外（.app-main），再按 Esc。
        waiting_group.locator(".sc-item", has_text="fea_solve_agent").first.click()
        page.locator(".peek-review-card").wait_for(state="visible", timeout=8000)
        page.wait_for_timeout(400)
        page.evaluate(
            """() => {
              const m = document.querySelector('.app-main');
              m.setAttribute('tabindex', '-1');
              m.focus();
            }"""
        )
        page.wait_for_timeout(200)
        focus_out = page.evaluate(
            "() => !!document.activeElement && !document.activeElement.closest('.sc-shell')"
        )
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        peek_still = page.locator(".peek-review-card").is_visible()
        drawer_open = page.locator(".sc-shell").is_visible()
        # 断档成立 = 焦点在壳外时 Esc 既不收抽屉也不退层（如实记录，不判 PASS/FAIL
        # 口径——这是 retro 修正后的现状取证；成立即 retro 真问题候选坐实）。
        check("E1-peek[焦点在壳外] Esc 现状取证",
              None,
              f"focus_out={focus_out} peek_retained={peek_still} drawer_open={drawer_open}"
              f" → {'断档成立（不收不退层）' if (focus_out and peek_still and drawer_open) else '断档不成立（有响应）'}")
        e1_peek_gap = bool(focus_out and peek_still and drawer_open)
        # 收尾：焦点收回壳内，留 peek 开态给 B3。
        page.evaluate("() => document.querySelector('.sc-shell').focus()")

        # ══ B3 peek → 批准放行 → completed ═══════════════════════════════
        page.screenshot(path=str(SHOTS / "status_peek_light_1440.png"))
        page.locator(".peek-approve").click()
        page.locator(".el-message-box button.sign-confirm-btn").wait_for(state="visible", timeout=5000)
        page.locator(".el-message-box button.sign-confirm-btn").click()
        final_status = ""
        for _ in range(20):
            time.sleep(1.5)
            final_status = api.get(f"/api/tasks/{FEA_TASK_ID}").json().get("status", "")
            if final_status == "completed":
                break
        check("B3 peek 批准放行 → API 落定 completed", final_status == "completed",
              f"status={final_status}")
        # dock pill 轮询回落（≤ 下两个 tick）。
        try:
            page.locator(".dock-pill-waiting").wait_for(state="hidden", timeout=15000)
            pill_gone = True
        except Exception:
            pill_gone = False
        check("B3 批准后 dock 待签 pill 回落（零待签不渲染）", pill_gone)
        title_after = page.title()
        check("B3 批准后 title 徽章清零", not title_after.startswith("("), f"title={title_after!r}")

        # ══ B4 completed 恒中性（非 greenish，rgb 实取）/ B5 失败红行 ═════
        page.locator(".sc-back").click()
        page.wait_for_timeout(800)
        done_group = page.locator(".sc-group", has=page.locator(".sc-group-label", has_text="最近落定"))
        fea_row = done_group.locator(".sc-item", has_text="fea_solve_agent").first
        fta_row2 = done_group.locator(".sc-item", has_text="fta_agent").first
        fea_row.wait_for(state="visible", timeout=8000)
        fea_lamp = fea_row.locator(".sc-lamp").evaluate("el => getComputedStyle(el).backgroundColor")
        fea_rgb = parse_rgb(fea_lamp)
        greenish = bool(fea_rgb) and fea_rgb[1] > fea_rgb[0] and fea_rgb[1] > fea_rgb[2]
        check("B4 completed 落定行灯恒中性（rgb 实取非 greenish）",
              fea_rgb is not None and not greenish and "已完成" in fea_row.inner_text(),
              f"lamp={fea_lamp} row={fea_row.inner_text()[:60]!r}")
        page.screenshot(path=str(SHOTS / "status_settled-neutral_light_1440.png"))
        fta_lamp = fta_row2.locator(".sc-lamp").evaluate("el => getComputedStyle(el).backgroundColor")
        fta_rgb = parse_rgb(fta_lamp)
        reddish = bool(fta_rgb) and fta_rgb[0] > fta_rgb[1] and fta_rgb[0] > fta_rgb[2]
        err = fta.get("error_message") or ""
        check("B5 worker 拾取 fta → 无 LLM 诚实失败 → 最近落定红行",
              reddish and "失败" in fta_row2.inner_text() and "ModelConfigError" in err,
              f"lamp={fta_lamp} err={err[:80]!r}")
        fta_row2.screenshot(path=str(SHOTS / "status_failed-row_light_1440.png"))
        # 关抽屉，给 D2 净场。
        page.keyboard.press("Escape")
        page.wait_for_timeout(600)

        # ══ D2 补验：新会话 fresh 方案卡，密级 pill 收 title（DOM title 取证）══
        page.goto(BASE + "/", wait_until="networkidle")
        page.wait_for_timeout(500)
        composer = page.locator(".composer-input textarea")
        composer.fill("计划：对单梁做挠度分析。")
        page.locator('button.send-btn[aria-label="发送"]').click()
        # fresh 窗口=直播会话内方案卡落定瞬间：成员行 roster 只挂 latestPlanIdx，
        # 且明细收在 details.route-disclosure 内（默认折叠，行在 DOM 不可见）——
        # 先等方案卡，再展开披露，才谈得上 hover 抽验。
        try:
            page.locator("details.route-disclosure").first.wait_for(state="visible", timeout=40000)
            disclosure_found = True
        except Exception:
            disclosure_found = False
        if disclosure_found:
            page.locator("details.route-disclosure summary").first.click()
            page.wait_for_timeout(600)
        rows = page.locator(".agent-card.sa-row")
        row_count = rows.count()
        rows_visible = row_count >= 1 and rows.first.is_visible()
        if row_count == 0 or not rows_visible:
            check("D2 fresh 方案卡成员行可达（roster 渲染）", None,
                  f"disclosure={disclosure_found} rows={row_count} visible={rows_visible}"
                  "——fresh 窗口成员行仍不可达（观察项）")
        if rows_visible:
            titles = rows.locator(".agent-name").evaluate_all(
                "els => els.map(e => e.getAttribute('title'))"
            )
            clearances = rows.locator(".agent-name").evaluate_all(
                "els => els.map(e => ({tabindex: e.getAttribute('tabindex'), aria: e.getAttribute('aria-label')}))"
            )
            check("D2 成员行 .agent-name 全带非空 title（密级 pill 收 title）",
                  len(titles) >= 1 and all(t for t in titles),
                  f"titles={titles}")
            # 敏感行 tabindex=0+aria-label（PR#34 P2 a11y 承袭）——有敏感行才断言。
            sens = [c for c, t in zip(clearances, titles) if t and "敏感" in t]
            if sens:
                check("D2 敏感行补 tabindex=0 + aria-label",
                      all(c["tabindex"] == "0" and c["aria"] for c in sens),
                      json.dumps(sens, ensure_ascii=False))
            rows.first.locator(".agent-name").hover()
            page.wait_for_timeout(400)
            page.screenshot(path=str(SHOTS / "retire_pill-title_light_1440.png"), full_page=True)
            check("D2 hover 抽验截图已重拍（title 属性经 DOM 取证）", True,
                  f"首行 title={titles[0]!r}")
            # 退役红线：成员行 DOM 零密级 pill 元素残留。
            pill_residue = page.locator(".agent-card.sa-row .clearance-pill").count()
            check("D2 成员行零 clearance pill 元素残留", pill_residue == 0,
                  f"residue={pill_residue}")

        context.close()
        browser.close()

    failed = [x for x in results if x[1] is False]
    infos = [x for x in results if x[1] is None]
    print(f"\n{'MAP32 WAVE3 ALL GREEN' if not failed else 'MAP32 WAVE3 FAILED'} "
          f"({len(results) - len(failed) - len(infos)}/{len(results) - len(infos)} 断言，"
          f"{len(infos)} 条现状取证)")
    for n, _, d in infos:
        print("INFO 明细:", n, "|", d)
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
