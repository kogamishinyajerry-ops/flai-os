"""桌面工艺批（UI-DESKTOP-CRAFT）验收：W0-W7 融合语言的回归网（真浏览器）。

契约来源：docs/design/UI-DESKTOP-CRAFT.md。八组探针：
  ① W0 focus-visible 焊死：Tab 落点 outline=2px solid + 颜色==--focus-ring-clay
     （亮/暗双主题各断一次——令牌拆掉必红，自证 tamper 面）；
  ② W0 全局工具类（真实渲染元素上断言，绝不造假节点）：.num-token 在今日页
     计数实例验 mono+tabular-nums；.cta-clay 在导引页真实 .send-btn 验「类名
     真接入+渐变+投影」——类没接或 utility 被拆任一必红（CTA 真归位口径）；
  ③ W2 空态纪律（今日页，空库冷开）：插画空态恰 1 张（待签发=行动召唤保插画），
     纯数据空态 4 处全为 .empty-line 轻量态，5 段文案逐字不变；
  ④ W6 登录门仪式感（未登录 context）：≥900px 品牌氛围面（aria-hidden 装饰）
     +标语可见；<900px 氛围面隐去回落单卡；诚实地板「签发永远由你亲手完成」
     逐字在场——两种宽度都在；
  ⑤ W3 任务详情 rail：宽容器双栏（260px rail 含来源+元信息卡；300px 档在
     ≥1120 超宽容器）、窄容器单栏（container query 断言 .td-grid 计算列数）；
     产物在主列、下载链接 DOM 序先于 rail；产物卡可折叠（aria-expanded 翻转
     + body 显隐），下载链接键盘 Enter 不触发折叠（@keydown.stop 对称隔离）；
     夹具 file id 加载失败如实显示「产物加载失败」（诚实非静默）；
  ⑥ W1 工作日志语义着色：chip 动宾分踢（对象名 mono+加重、innerText 逐字
     「调用工具 mock_echo」）；时间轴 tool_failed 行染 --trust-fail、
     task_completed 行不染（红=仅真失败，completed 不给绿也不给红）；
     ⑥' 红线边界：task_cancelled+level=error（毒丸隔离同款）绝不染红；
  ⑦ W3 驳回术语：waiting_review 详情页动作=「批准放行」+「驳回」（无「拒绝」）；
  ⑧ W5 对话轴 markdown：助手气泡 "- " 列表渲染成真 ul>li；用户气泡保持纯文本。

夹具口径（与 m9 同纪律）：temp DB 直写只为渲染路径提供 fixture，不冒充业务
状态机行为（真实完成/放行链路由 m2 验收）。completed 任务配 tool_failed 事件
是合法业务态（工具失败后重试成功），非造假。

自包含：自起后端（tmp DB）+ stub gateway + 真 chromium，不起 worker。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/craft_desktop_acceptance.py

截图落 docs/reviews/craft-shots/。
"""
from __future__ import annotations

import json
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = REPO / "docs" / "reviews" / "craft-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_craft_"))


class _StubGateway:
    """导引 stub：返回带 markdown 列表的纯文本回复（无 PLAN 块）——只为
    ⑧ 的 MarkdownLite 渲染路径提供 fixture。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        # 行内保真管辖输入（Codex R1+R2 P1 回归网）：成对 `code`/**strong** 须
        # 渲染成真元素；配不上对的 **/反引号逐字保留。含 R2 原例
        # def f(**kwargs)：**重要**——'：**' 绝不许当闭标记吃掉函数语法。
        reply = (
            "两步走：\n- 先出控制逻辑\n- 再做故障树\n\n"
            "注意 `top_event` 参数，**关键**是先确认口径；"
            "def f(**kwargs)：**重要**；另 2 ** 3 这类字面量逐字保留。"
        )
        return {"content": reply, "token_usage": None, "model_name": "stub", "finish_reason": "stop"}


_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

app = create_app(
    agents_dir=REPO / "agents",
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=WORK / "flai_os.db",
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

app.state.conversation_service.model_gateway = _StubGateway()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def _db(sql: str, params: tuple = ()) -> None:
    import sqlite3

    conn = sqlite3.connect(WORK / "flai_os.db")
    conn.execute(sql, params)
    conn.commit()
    conn.close()


def flip_completed_with_artifact_and_events(task_id: str) -> None:
    """夹具：completed+产物+事件流（tool_failed 后重试成功=合法业务态）。"""
    _db(
        "UPDATE tasks SET status='completed', output_file_ids=?, started_at=?, finished_at=? WHERE id=?",
        (json.dumps(["file_probe_0001"]), "2026-07-15T02:00:00+00:00", "2026-07-15T02:01:35+00:00", task_id),
    )
    rows = [
        ("evt_craft_1", "task_created", "info", "任务已创建", "{}"),
        ("evt_craft_2", "tool_started", "info", "工具开始", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_3", "tool_failed", "error", "工具首跑失败", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_4", "tool_started", "info", "工具重试", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_5", "tool_finished", "info", "工具完成", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_6", "task_completed", "info", "任务完成", "{}"),
    ]
    for i, (eid, etype, level, msg, payload) in enumerate(rows):
        _db(
            "INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (eid, task_id, "hello_agent", etype, level, msg, payload, f"2026-07-15T02:00:{10 + i:02d}+00:00"),
        )


def resolved_color(page, css_value: str) -> str:
    """在页面里解析任意 CSS 颜色表达式（含 var()）为 rgb() 串——嵌套 var 也能解。"""
    return page.evaluate(
        """(v) => { const el = document.createElement('div'); el.style.color = v;
             document.body.appendChild(el); const c = getComputedStyle(el).color;
             el.remove(); return c; }""",
        css_value,
    )


from _auth import login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "验收工程师")

with sync_playwright() as p:
    browser = p.chromium.launch()

    # ── ④ W6 登录门（未登录 context，先于一切登录态探针）─────────────────
    gate_ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    gpage = gate_ctx.new_page()
    gpage.goto(BASE + "/", wait_until="networkidle")
    gpage.wait_for_selector(".welcome-gate", timeout=8000)
    brand = gpage.locator(".welcome-gate__brand")
    check("④宽屏品牌氛围面可见且纯装饰（aria-hidden）",
          brand.count() == 1 and brand.get_attribute("aria-hidden") == "true" and brand.is_visible())
    check("④标语在场", gpage.locator(".welcome-gate__tagline").inner_text().strip() == "机器提议，人签发。")
    body = gpage.locator("body").inner_text()
    check("④诚实地板逐字（宽）", "登录后开始工作——签发永远由你亲手完成。" in body)
    check("④登录卡原样（用户名/密码/进入）",
          gpage.locator(".welcome-gate__content input").count() == 2
          and gpage.locator(".welcome-gate__button").count() == 1)
    gpage.screenshot(path=str(SHOTS / "gate_split_wide.png"))
    gpage.set_viewport_size({"width": 760, "height": 900})
    gpage.wait_for_timeout(200)
    check("④<900px 氛围面隐去（单卡回落）",
          gpage.locator(".welcome-gate__brand").is_hidden()
          and gpage.locator(".welcome-gate__content").is_visible())
    check("④诚实地板逐字（窄）", "签发永远由你亲手完成" in gpage.locator("body").inner_text())
    gpage.screenshot(path=str(SHOTS / "gate_single_narrow.png"))
    gate_ctx.close()

    # ── 登录态主 context（亮色 pin）──────────────────────────────────────
    ctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(ctx, BASE)
    API = login_httpx(BASE)
    page = ctx.new_page()

    # ── ③ W2 今日页空态纪律（空库冷开，先于建任务）──────────────────────
    page.goto(BASE + "/today", wait_until="networkidle")
    page.wait_for_selector(".today-section", timeout=8000)
    imgs = page.locator(".today .el-empty__image img")
    lines = page.locator(".today .empty-line")
    check("③插画空态恰 1 张（待签发=行动召唤）", imgs.count() == 1)
    check("③纯数据空态 4 处全为轻量行", lines.count() == 4)
    body = page.locator("body").inner_text()
    texts = ["没有等你签发的任务", "当前没有进行中的任务", "今天还没有交付的任务", "本周暂无晋升", "今天暂无任务"]
    check("③空态文案 5 段逐字不变", all(t in body for t in texts),
          "缺:" + ",".join(t for t in texts if t not in body))
    line_color = lines.first.evaluate("el => getComputedStyle(el).color")
    check("③line 空态走 ink-soft（4.5:1 可读阈，非 faint）",
          line_color == resolved_color(page, "var(--ink-soft)"), line_color)
    page.screenshot(path=str(SHOTS / "today_empty_light.png"), full_page=True)

    # ── ② W0 全局工具类（今日页真实实例上断言；CTA 探针在 ⑧ 导引页真实
    #      .send-btn 上做——绝不造假元素）─────────────────────────────────
    num = page.locator(".today-section-head .num-token").first
    num_style = num.evaluate("el => { const s = getComputedStyle(el); return s.fontFamily + '|' + s.fontVariantNumeric; }")
    check("②.num-token 走 mono+tabular-nums", ("Mono" in num_style or "monospace" in num_style) and "tabular-nums" in num_style,
          num_style)

    # ── ① W0 focus-visible（亮）────────────────────────────────────────
    # 焦点环契约=瞬时出现（focus-visible 块 transition:none 冻结基态 transition:all
    # 对 outline 的卷入）；等一拍取稳态只为隔离其他动效，非放宽断言。
    page.keyboard.press("Tab")
    page.wait_for_timeout(250)
    focus = page.evaluate(
        """() => { const el = document.activeElement; const s = getComputedStyle(el);
             return { tag: el.tagName, w: s.outlineWidth, st: s.outlineStyle, c: s.outlineColor }; }"""
    )
    want = resolved_color(page, "var(--focus-ring-clay)")
    check("①Tab 焦点环=2px solid focus-ring-clay（亮）",
          focus["st"] == "solid" and focus["w"] == "2px" and focus["c"] == want,
          f"{focus} want={want}")

    # ── 建任务 A（completed+产物+事件）、B（waiting_review）、C（cancelled+
    #    毒丸隔离事件——runner._quarantine_poison_candidate 同款 task_cancelled+
    #    level=error，红线探针「取消绝不染红」的最刁钻输入）──────────────────
    resp_a = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针A"}})
    resp_b = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针B"}})
    resp_c = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针C"}})
    assert resp_a.status_code < 300 and resp_b.status_code < 300 and resp_c.status_code < 300, \
        f"建任务失败：{resp_a.text} {resp_b.text} {resp_c.text}"
    task_a = resp_a.json()["id"]
    task_b = resp_b.json()["id"]
    task_c = resp_c.json()["id"]
    flip_completed_with_artifact_and_events(task_a)
    _db("UPDATE tasks SET status='waiting_review', started_at=? WHERE id=?",
        ("2026-07-15T02:00:00+00:00", task_b))
    _db("UPDATE tasks SET status='cancelled' WHERE id=?", (task_c,))
    _db(
        "INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("evt_craft_c1", task_c, None, "task_cancelled", "error",
         "候选依赖解析遇畸形持久数据抛异常，单候选隔离取消", "{}", "2026-07-15T02:02:00+00:00"),
    )

    # ── ⑤ W3 任务详情 rail（宽=双栏）─────────────────────────────────────
    page.goto(BASE + f"/tasks/{task_a}", wait_until="networkidle")
    page.wait_for_selector(".td-grid", timeout=8000)
    # 1440 视口下任务台中栏≈820px 容器 → 780 档双栏（rail 260px）；300px 档要
    # ≥1120 容器（超宽屏），非本探针视口所及。
    cols = page.locator(".td-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns")
    check("⑤宽容器双栏（rail=260px）", cols.strip().endswith("260px") and " " in cols.strip(), cols)
    check("⑤rail 含元信息卡+来源面板",
          page.locator(".td-rail .task-meta-card").count() == 1
          and page.locator(".td-rail .source-panel").count() == 1)
    # 固定态状态坞让位（Codex R0 P2 回归网）：scroll-0 时 rail 首卡不得与
    # StatusDock（fixed top16+高32）叠压——rail 顶必须在坞底之下。
    dock_box = page.locator(".status-dock").bounding_box()
    rail_box = page.locator(".td-rail").bounding_box()
    dock_clear = (dock_box is None) or (rail_box is not None and rail_box["y"] >= dock_box["y"] + dock_box["height"])
    check("⑤rail 让位状态坞（无叠压）", dock_clear is True,
          f"dock={dock_box} rail={rail_box}")
    dl = page.locator("a[href*='/download']").first
    in_main = dl.evaluate("el => !!el.closest('.td-main')")
    check("⑤产物下载链接在主列（DOM 序先于 rail）", in_main is True)
    # 披露触发器=真 <button>（Codex R0 P2：嵌套可交互控件非法）——下载 <a>
    # 是其兄弟，二者互不包含。
    toggle = page.locator(".artifact-toggle").first
    check("⑤产物卡默认展开（aria-expanded=true）", toggle.get_attribute("aria-expanded") == "true")
    check("⑤下载链接是触发器兄弟（不嵌套，合法 ARIA）",
          page.locator(".artifact-toggle .artifact-download").count() == 0
          and page.locator(".artifact-head > .artifact-download").count() >= 1)
    check("⑤夹具产物加载失败如实显示", "产物加载失败" in page.locator(".artifact-card").first.inner_text())
    toggle.click()
    page.wait_for_timeout(150)
    body_hidden = page.locator(".artifact-card").first.locator(".artifact-body").first.is_hidden()
    check("⑤点触发器折叠（aria-expanded 翻转+body 隐）",
          toggle.get_attribute("aria-expanded") == "false" and body_hidden is True)
    toggle.click()
    page.wait_for_timeout(150)
    check("⑤再点展开还原", toggle.get_attribute("aria-expanded") == "true")
    # 键盘路径隔离（3-lens P2 回归保护，兄弟结构后由原生语义保证）：Tab 到
    # 「下载」链接按 Enter 绝不触发折叠。
    page.locator(".artifact-download").first.focus()
    page.keyboard.press("Enter")
    page.wait_for_timeout(150)
    check("⑤下载链接键盘 Enter 不触发折叠（兄弟结构）",
          toggle.get_attribute("aria-expanded") == "true")
    page.screenshot(path=str(SHOTS / "taskdetail_rail_wide_light.png"), full_page=True)

    # ── ⑥ W1 工作日志语义着色（同页）────────────────────────────────────
    obj = page.locator(".worklog-tool-object").first
    chip_text = page.locator(".worklog-tool").filter(has_text="调用工具").first.inner_text().replace("\n", " ")
    obj_style = obj.evaluate("el => { const s = getComputedStyle(el); return s.fontWeight + '|' + s.fontFamily; }")
    check("⑥chip 动宾分踢（innerText 逐字+对象 mono 加重）",
          "调用工具" in chip_text and "mock_echo" in chip_text
          and obj_style.startswith("600") and ("Mono" in obj_style or "monospace" in obj_style),
          f"{chip_text} / {obj_style}")
    if page.locator(".worklog-timeline .event-type").count() == 0:
        page.locator(".worklog-head").first.click()
        page.wait_for_selector(".worklog-timeline .event-type", timeout=4000)
    fail_color = resolved_color(page, "var(--trust-fail)")
    rows = page.locator(".worklog-timeline .event-type")
    colors: dict[str, str] = {}
    for i in range(rows.count()):
        t = rows.nth(i).inner_text()
        c = rows.nth(i).evaluate("el => getComputedStyle(el).color")
        if "tool_failed" in t:
            colors["fail"] = c
        elif "task_completed" in t:
            colors["done"] = c
    check("⑥tool_failed 行染 trust-fail", colors.get("fail") == fail_color, str(colors) + " want=" + fail_color)
    check("⑥task_completed 行不染红（completed 不给红也不给绿）",
          "done" in colors and colors["done"] != fail_color, str(colors))
    page.screenshot(path=str(SHOTS / "worklog_semantic_light.png"), full_page=True)

    # ── ⑤' W3 窄容器单栏（container query 生效面）────────────────────────
    # 760 视口：≤900 媒体档（侧栏收抽屉、padding 16×2）→ 容器≈728 < 780 → 单列。
    page.set_viewport_size({"width": 760, "height": 900})
    page.wait_for_timeout(250)
    cols_narrow = page.locator(".td-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns")
    check("⑤'窄容器单栏（无 rail 列）",
          not cols_narrow.strip().endswith("260px") and not cols_narrow.strip().endswith("300px"),
          cols_narrow)
    page.screenshot(path=str(SHOTS / "taskdetail_rail_narrow_light.png"), full_page=True)
    page.set_viewport_size({"width": 1440, "height": 900})

    # ── ⑥' 红线边界：task_cancelled+level=error（毒丸隔离同款）绝不染红────
    page.goto(BASE + f"/tasks/{task_c}", wait_until="networkidle")
    page.wait_for_selector(".td-grid", timeout=8000)
    if page.locator(".worklog-timeline .event-type").count() == 0:
        page.locator(".worklog-head").first.click()
        page.wait_for_selector(".worklog-timeline .event-type", timeout=4000)
    crows = page.locator(".worklog-timeline .event-type")
    cancel_color = None
    for i in range(crows.count()):
        if "task_cancelled" in crows.nth(i).inner_text():
            cancel_color = crows.nth(i).evaluate("el => getComputedStyle(el).color")
    check("⑥'取消（含 level=error 毒丸隔离）不染红（红=仅真失败）",
          cancel_color is not None and cancel_color != resolved_color(page, "var(--trust-fail)"),
          f"cancel={cancel_color}")
    # 时间轴节点同一谓词（Codex R1 P1）：豁免路径的 dot 也不许残留 error 红
    # （LEVEL_COLOR.error=#F56C6C → rgb(245,108,108)）。
    dot_colors = page.locator(".worklog-timeline .el-timeline-item__node").evaluate_all(
        "els => els.map(el => getComputedStyle(el).backgroundColor)"
    )
    check("⑥'毒丸隔离 dot 降中性（无 error 红点）",
          len(dot_colors) >= 1 and "rgb(245, 108, 108)" not in dot_colors,
          str(dot_colors))

    # ── ⑦ W3 驳回术语（waiting_review 详情页）────────────────────────────
    page.goto(BASE + f"/tasks/{task_b}", wait_until="networkidle")
    page.wait_for_selector(".td-grid", timeout=8000)
    has_approve = page.get_by_role("button", name="批准放行").count() == 1
    has_reject = page.get_by_role("button", name="驳回").count() == 1
    no_old = page.get_by_role("button", name="拒绝").count() == 0
    check("⑦动作=批准放行+驳回（无「拒绝」）", has_approve and has_reject and no_old)

    # ── ⑧ W5 对话轴 markdown（助手 ul>li / 用户纯文本）＋ ② CTA 真归位────
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("- 这行是用户输入不该变列表\n先做什么？")
    # ② CTA 探针（真实渲染元素，非合成节点）：send-btn 必须真接 .cta-clay 类，
    # 渐变/投影由全局 utility 供给（填字后按钮 enabled，disabled 态的 shadow:none
    # 覆盖不在此路径）。类名或 utility 规则任一被拆 → 此探针红。
    send_btn = page.locator(".send-btn")
    send_cls = send_btn.get_attribute("class") or ""
    send_sty = send_btn.evaluate(
        "el => { const s = getComputedStyle(el); return { bg: s.backgroundImage, shadow: s.boxShadow }; }"
    )
    check("②主 CTA 真接 .cta-clay（send-btn 类名+渐变+投影）",
          "cta-clay" in send_cls.split() and "linear-gradient" in send_sty["bg"] and send_sty["shadow"] != "none",
          f"{send_cls} / {send_sty}")
    page.get_by_role("button", name="发送").click()
    page.wait_for_selector(".ai-lead .md-ul li", timeout=8000)
    check("⑧助手气泡列表渲染为 ul>li", page.locator(".ai-lead .md-ul li").count() == 2)
    check("⑧用户气泡保持纯文本（无 ul）",
          page.locator(".user-bubble ul").count() == 0
          and "- 这行是用户输入不该变列表" in page.locator("body").inner_text())
    # 行内保真（Codex R1 P1）：成对标记渲染成真元素、不成对标记逐字保留——
    # 绝不无差别删字符。
    ai_text = page.locator(".ai-lead").last.inner_text()
    check("⑧成对 `code`/**strong** 渲染成真元素",
          page.locator(".ai-lead .md-code", has_text="top_event").count() == 1
          and page.locator(".ai-lead strong", has_text="关键").count() == 1
          and page.locator(".ai-lead strong", has_text="重要").count() == 1)
    check("⑧代码字面量零误伤（Codex R2 原例：函数语法逐字 + 相邻 strong 仍成立）",
          "def f(**kwargs)：" in ai_text and "2 ** 3" in ai_text, ai_text[-140:])
    page.screenshot(path=str(SHOTS / "guide_markdown_light.png"), full_page=True)

    ctx.close()

    # ── ①' 暗主题 pin（focus 令牌+rail 复核）────────────────────────────
    dctx = browser.new_context(viewport={"width": 1440, "height": 900}, color_scheme="dark")
    login_context(dctx, BASE)
    dpage = dctx.new_page()
    dpage.goto(BASE + f"/tasks/{task_a}", wait_until="networkidle")
    dpage.wait_for_selector(".td-grid", timeout=8000)
    dpage.keyboard.press("Tab")
    dpage.wait_for_timeout(250)
    dfocus = dpage.evaluate(
        """() => { const s = getComputedStyle(document.activeElement);
             return { st: s.outlineStyle, w: s.outlineWidth, c: s.outlineColor }; }"""
    )
    dwant = resolved_color(dpage, "var(--focus-ring-clay)")
    lwant = want  # 亮主题解析值
    check("①'Tab 焦点环走暗主题令牌（≠亮值）",
          dfocus["st"] == "solid" and dfocus["c"] == dwant and dwant != lwant,
          f"{dfocus} want={dwant}")
    dcols = dpage.locator(".td-grid").evaluate("el => getComputedStyle(el).gridTemplateColumns")
    check("①'暗主题 rail 结构同构", dcols.strip().endswith("260px"), dcols)
    dpage.screenshot(path=str(SHOTS / "taskdetail_rail_wide_dark.png"), full_page=True)
    dctx.close()

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'CRAFT DESKTOP ALL GREEN' if not failed else 'CRAFT DESKTOP FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
