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
  ⑧ W5 对话轴 markdown：助手气泡 "- " 列表渲染成真 ul>li；用户气泡保持纯文本；
  ⑨ 批次二 F1-F6 细粒度（契约=UI-DESKTOP-CRAFT.md 批次二）：
     F1 数字对表——盖章「2 分 05 秒」秒补零 + rail「tokens 合计 12.3k」千位
     压缩（原始 12345 绝迹）；F2 活跳计时——running 任务断轮询后 3.3s 窗口内
     「已处理」文本仍逐秒变化（纯 ticker 驱动，非轮询）；F3 核验段——mock
     任务 amber「未经真实核验」+teal 签发行（与 WorkLog 逐字同措辞 SSOT）/
     waiting 任务「待人工签发」/ cancelled 不渲染 / 全真工具任务「均为真实
     执行」中性 / 页头批量成功 tag 不给绿+核验批量行失败计数染红 / sensitive
     分级真实遮蔽下签发行降级「签发记录不可用」（绝不谎报「未经签发」）；
     F4 盖章落定时刻（HH:MM 或 MM-DD HH:MM）+ cancelled 报中断时刻不报时长；
     F5 产物 >3 件折叠「显示另外 N 个」单向展开（前 3 恒渲）；F6 类型标签
     「文档 · MD」（TaskDetail 与 StatusCenter 速览同 SSOT）；
  ⑩ 批次三 G1-G4 深度打磨（契约=UI-DESKTOP-CRAFT.md 批次三，desktop-restudy）：
     G1 工作日志头贴地（背景透明+左右无边+上下发丝线+灰字 500——盒装样式
     回种必红）；G2 工作态头行三段式「正在处理 · 已 X · N 条事件」+ 完成态
     零事件任务无「0 条事件」（零值豁口）；G3 状态中心运行中行活跳时长——
     断列表轮询后行内「已 X」仍逐秒递增（纯 ticker 驱动）；G4 收件箱行级
     紧凑时钟（同日 HH:MM/跨日 MM-DD HH:MM，locale 全量串绝迹）+ /me 任务行
     孪生面同 SSOT（useTodayKey 响应式日界）。
  ⑪ 批次四 Q1-Q5 新人极简（契约=UI-DESKTOP-CRAFT.md 批次四）：
     Q1 行级主文本人话称呼——缺名任务显 Agent 注册表显示名（裸 task_ 前缀
     绝迹），名册拉取失败诚实回退 id 切片（route-abort /api/agents 实证，
     绝不编名字）；Q2 零值不显示全站化——今日页组头零计数豁口/团队总量
     零值格语义对表/我的页四格与反馈同律；Q3 方法论脚注一处一行（状态中心
     口径短句/today-subhead-note 退役）；Q4 门户图例句撤下（释义走徽章
     title，L0「勿依赖」诚实提示保留）+类型/成熟度/id·版本合并次级 meta
     一行+cat-bar 退役；Q5 原始事件 token 只活在展开态时间轴（折叠态=人话
     扫读面，「task_created」在折叠态绝迹）。

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
    """夹具：completed+产物+事件流（tool_failed 后重试成功=合法业务态）+签发链
    +tool_runs（mock 位如实）+model_calls（token 用量）——批次二 F1/F3 探针面。
    耗时 125s（02:00:00→02:02:05）刻意让秒位 <10：格式对表「2 分 05 秒」补零可探。"""
    # data_classification='internal' 必须与 tool_runs/model_calls 同批种入：
    # 分级门 fail-closed 兜底是「NULL 分级 + 任何派生内容行 → 封（遮蔽 events
    # payload/message）」——真实 runner 对 internal 任务必落此戳（runtime.py
    # set_task_data_classification），夹具不落就是讲了个不自洽的故事，门会
    # 正确地咬（本批实测咬过一次：签发行/工具 chip payload 全被遮蔽）。
    _db(
        "UPDATE tasks SET status='completed', output_file_ids=?, started_at=?, finished_at=?,"
        " data_classification='internal' WHERE id=?",
        (json.dumps(["file_probe_0001"]), "2026-07-15T02:00:00+00:00", "2026-07-15T02:02:05+00:00", task_id),
    )
    rows = [
        ("evt_craft_1", "task_created", "info", "任务已创建", "{}"),
        ("evt_craft_2", "tool_started", "info", "工具开始", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_3", "tool_failed", "error", "工具首跑失败", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_4", "tool_started", "info", "工具重试", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_5", "tool_finished", "info", "工具完成", json.dumps({"tool_id": "mock_echo"})),
        ("evt_craft_5b", "review_requested", "info", "请求人工审核", "{}"),
        ("evt_craft_5c", "review_approved", "info", "人工已批准", json.dumps({"reviewer": "验收工程师"})),
        ("evt_craft_6", "task_completed", "info", "任务完成", "{}"),
    ]
    for i, (eid, etype, level, msg, payload) in enumerate(rows):
        _db(
            "INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (eid, task_id, "hello_agent", etype, level, msg, payload, f"2026-07-15T02:00:{10 + i:02d}+00:00"),
        )
    # tool_runs：mock_echo 首跑失败+重试成功，两条均 mock=1（hello_agent 的
    # mock 工具如实落库）——F3 工具行该报「2 次工具调用 · 含 2 次 mock」+amber。
    for status, fin in (("failed", "2026-07-15T02:00:12+00:00"), ("success", "2026-07-15T02:00:14+00:00")):
        _db(
            "INSERT INTO tool_runs (task_id, tool_id, tool_version, mock, status, input_json, started_at, finished_at)"
            " VALUES (?,?,?,?,?,?,?,?)",
            (task_id, "mock_echo", "0.1.0", 1, status, "{}", "2026-07-15T02:00:11+00:00", fin),
        )
    # model_calls：12000+345=12345 → F1 压缩「12.3k」（rail 断言 12,345/12345 绝迹）。
    for tok in (12000, 345):
        _db(
            "INSERT INTO model_calls (task_id, agent_id, model_profile, model_name, status, token_usage_json, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (task_id, "hello_agent", "default", "stub-model", "success",
             json.dumps({"total_tokens": tok}), "2026-07-15T02:00:13+00:00"),
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

    # ── ③ W2 今日页空态纪律（空库冷开，先于建任务）。批次四 Q2 后的冷态语法：
    #      组头零计数不渲染「· 0」；Agent 动态双空态合并为一行；团队总量零值格
    #      不渲染（期望值按 /api/stats/overview 真值分支——curated 计数来自仓内
    #      固化文件，冷库不必为 0，硬编码会撒谎）──────────────────────────
    page.goto(BASE + "/today", wait_until="networkidle")
    page.wait_for_selector(".today-section", timeout=8000)
    imgs = page.locator(".today .el-empty__image img")
    check("③插画空态恰 1 张（待签发=行动召唤）", imgs.count() == 1)

    since_iso = page.evaluate(
        "() => { const d = new Date(); d.setHours(0,0,0,0); "
        "d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d.toISOString(); }"
    )
    cold_stats = API.get("/api/stats/overview", params={"since": since_iso}, timeout=10).json()
    stat_fields = ["tasks_completed", "reviews_approved", "curated_cases_total", "promotions"]
    stats_all_zero = all(not cold_stats.get(f) for f in stat_fields)
    # 轻量行期望：进行中 1 + 今日交付 1 + Agent 动态合并 1 + （团队全 0 时再 +1）
    expected_lines = 3 + (1 if stats_all_zero else 0)
    lines = page.locator(".today .empty-line")
    check(f"③纯数据空态恰 {expected_lines} 行（Agent 动态双空态已合并为一行）",
          lines.count() == expected_lines, f"count={lines.count()} stats_all_zero={stats_all_zero}")
    body = page.locator("body").inner_text()
    texts = ["没有等你签发的任务", "当前没有进行中的任务", "今天还没有交付的任务", "今天还没有 Agent 动态"]
    check("③空态文案 4 段逐字不变（双空态合并文案）", all(t in body for t in texts),
          "缺:" + ",".join(t for t in texts if t not in body))
    # Q2 零计数豁口：冷态三个组头绝不出现「· 0」。
    heads = page.locator(".today-section-head").all_inner_texts()
    check("③零值组头无「· 0」后缀（零不是信息）", all("· 0" not in h for h in heads), str(heads))
    # Q2 团队总量零值格：API==0 ⇒ 格不渲染；>0 ⇒ 恰 1 格且数字逐字相等。
    tiles_ok = True
    tiles_detail = {}
    for f in stat_fields:
        tile = page.locator(f'.today-stat-tile[data-stat="{f}"]')
        v = cold_stats.get(f)
        if isinstance(v, int) and v > 0:
            ok_f = tile.count() == 1 and tile.locator(".today-stat-num").inner_text().strip() == str(v)
        else:
            ok_f = tile.count() == 0
        tiles_ok = tiles_ok and ok_f
        tiles_detail[f] = f"api={v} ui={'shown' if tile.count() else 'hidden'}"
    check("③团队总量零值格不渲染（语义对表 data-stat）", tiles_ok is True, str(tiles_detail))
    # Q3 方法论口径同屏唯一：页脚一行保留，版块内不再复述「近 100 条」note。
    check("③窗口口径只在页脚一行（today-subhead-note 退役）",
          page.locator(".today-subhead-note").count() == 0 and "基于最近 100 条任务窗口" in body)
    line_color = lines.first.evaluate("el => getComputedStyle(el).color")
    check("③line 空态走 ink-soft（4.5:1 可读阈，非 faint）",
          line_color == resolved_color(page, "var(--ink-soft)"), line_color)
    page.screenshot(path=str(SHOTS / "today_empty_light.png"), full_page=True)

    # ── ② W0 全局工具类：批次四 Q2 后冷态今日页无 .num-token 实例（零计数
    #      收敛），断言迁往 ⑩c 状态中心（待签组头带真实计数处）；CTA 探针
    #      仍在 ⑧ 导引页真实 .send-btn 上做——绝不造假元素。──────────────

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

    # ══ ⑨ 批次二 F1-F6 细粒度探针 ══════════════════════════════════════════

    # ── ⑨a/b F1+F4+F3 于 task A（completed·mock 工具·签发链·12345 tokens）──
    page.goto(BASE + f"/tasks/{task_a}", wait_until="networkidle")
    page.wait_for_selector(".completion-seal", timeout=8000)
    seal_text = page.locator(".seal-text").inner_text()
    check("⑨F1 盖章时长秒补零（125s→2 分 05 秒）", "2 分 05 秒" in seal_text, seal_text)
    import re as _re
    check("⑨F4 盖章落定时刻（绝对时间戳，同日 HH:MM/跨日 MM-DD HH:MM）",
          _re.search(r"(\d{2}-\d{2} )?\d{2}:\d{2}$", seal_text.strip()) is not None, seal_text)
    rail_usage = page.locator(".model-usage").inner_text()
    check("⑨F1 rail tokens 千位压缩（12.3k 在场、原始 12345/12,345 绝迹）",
          "12.3k" in rail_usage and "12345" not in rail_usage and "12,345" not in rail_usage,
          rail_usage)
    vcard = page.locator(".verify-card")
    check("⑨F3 核验段在完成态渲染（工具/签发两行）", vcard.count() == 1 and vcard.locator(".verify-row").count() >= 2)
    tool_row = vcard.locator(".verify-row").first.inner_text().replace("\n", " ")
    check("⑨F3 mock 如实披露（2 次调用 · 含 2 次 mock + amber 未经真实核验）",
          "2" in tool_row and "mock" in tool_row and vcard.locator(".pill-amber", has_text="未经真实核验").count() == 1,
          tool_row)
    sign_text = vcard.locator(".verify-signoff").inner_text()
    sign_color = vcard.locator(".verify-signoff").evaluate("el => getComputedStyle(el).color")
    check("⑨F3 签发行 teal（✓ 由 验收工程师 批准放行，与 WorkLog 同措辞 SSOT）",
          "✓ 由 验收工程师 批准放行" in sign_text and sign_color == resolved_color(page, "var(--trust-signed)"),
          f"{sign_text} / {sign_color}")
    # 同措辞 SSOT 复核（3-lens paradigm P3）：WorkLog 口播与核验段逐字同串。
    wl_sign = page.locator(".worklog-signoff").inner_text()
    check("⑨F3 WorkLog 口播同措辞（deriveSignoff/signoffText 真同源）",
          wl_sign.strip() == sign_text.strip(), f"worklog={wl_sign!r} verify={sign_text!r}")
    page.screenshot(path=str(SHOTS / "verify_card_completed_light.png"), full_page=True)

    # ── ⑨c F3 waiting_review：待签 amber；无 tool_runs → 「无工具调用记录」──
    page.goto(BASE + f"/tasks/{task_b}", wait_until="networkidle")
    page.wait_for_selector(".verify-card", timeout=8000)
    vb = page.locator(".verify-card").inner_text()
    pend_color = page.locator(".verify-pending").evaluate("el => getComputedStyle(el).color")
    check("⑨F3 待签任务=「待人工签发」amber + 「无工具调用记录」诚实空",
          "待人工签发" in vb and "无工具调用记录" in vb
          and pend_color == resolved_color(page, "var(--trust-pending)"),
          f"{vb[:80]} / {pend_color}")

    # ── ⑨d F3 cancelled 不渲染（中断非成果，核验段零占位）──────────────────
    page.goto(BASE + f"/tasks/{task_c}", wait_until="networkidle")
    page.wait_for_selector(".td-grid", timeout=8000)
    check("⑨F3 取消任务不渲染核验段", page.locator(".verify-card").count() == 0)

    # ── ⑨e F2 活跳计时（running 任务·断轮询后纯 ticker 驱动）────────────────
    resp_d = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针D"}})
    assert resp_d.status_code < 300, resp_d.text
    task_d = resp_d.json()["id"]
    from datetime import datetime, timezone
    _db("UPDATE tasks SET status='running', started_at=? WHERE id=?",
        (datetime.now(timezone.utc).isoformat(), task_d))
    page.goto(BASE + f"/tasks/{task_d}", wait_until="networkidle")
    page.wait_for_selector(".worklog-head-text", timeout=8000)
    head0 = page.locator(".worklog-head-text").inner_text()
    check("⑨F2 运行态头行=「正在处理 · 已 X」", head0.startswith("正在处理"), head0)
    # 掐断该任务的轮询通道（route abort）：此后文本变化只可能来自组件内 1s
    # ticker——把「活跳与轮询解耦」变成可证伪谓词（轮询驱动的旧实现在此必冻结）。
    ctx.route(f"**/api/tasks/{task_d}", lambda route: route.abort())
    samples = {page.locator(".worklog-head-text").inner_text()}
    for _ in range(3):
        page.wait_for_timeout(1100)
        samples.add(page.locator(".worklog-head-text").inner_text())
    check("⑨F2 断轮询后 3.3s 内文本仍逐秒递增（纯 ticker，≥3 个不同读数）",
          len(samples) >= 3, str(samples))
    ctx.unroute(f"**/api/tasks/{task_d}")

    # ── ⑨f F5+F6+F3 于 task E（5 件真实 .md 产物·真工具 run mock=0）─────────
    file_ids = []
    for i in range(5):
        up = API.post(
            "/api/files/upload",
            files={"file": (f"report_{i}.md", f"# 报告 {i}\n\n第 {i} 份。\n".encode(), "text/markdown")},
        )
        assert up.status_code < 300, up.text
        file_ids.append(up.json()["file_id"] if "file_id" in up.json() else up.json()["id"])
    resp_e = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针E"}})
    assert resp_e.status_code < 300, resp_e.text
    task_e = resp_e.json()["id"]
    # 同 flip 夹具口径：有 tool_runs 派生行必须配 internal 分级戳，否则分级门
    # fail-closed 遮蔽 events/产物元数据（门正确，夹具要自洽）。
    _db("UPDATE tasks SET status='completed', output_file_ids=?, started_at=?, finished_at=?,"
        " data_classification='internal' WHERE id=?",
        (json.dumps(file_ids), "2026-07-15T03:00:00+00:00", "2026-07-15T03:00:42+00:00", task_e))
    _db("INSERT INTO tool_runs (task_id, tool_id, tool_version, mock, status, input_json, started_at, finished_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (task_e, "real_writer", "1.0.0", 0, "success", "{}",
         "2026-07-15T03:00:01+00:00", "2026-07-15T03:00:40+00:00"))
    # 批量摘要事件（3-lens trust P2 探针面）：页头批量 tag 与核验段批量行同数据。
    _db("INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("evt_craft_e1", task_e, "hello_agent", "agent_log", "info", "生成汇总",
         json.dumps({"workflow_event_type": "summary_generated", "ok_count": 4, "failed_count": 1}),
         "2026-07-15T03:00:41+00:00"))
    page.goto(BASE + f"/tasks/{task_e}", wait_until="networkidle")
    page.wait_for_selector(".artifact-card", timeout=8000)
    n_cards = page.locator(".artifact-card").count()
    more_btn = page.locator(".artifact-more")
    check("⑨F5 >3 件产物默认渲染前 3 + 尾部折叠行", n_cards == 3 and more_btn.count() == 1
          and "显示另外 2 个" in more_btn.inner_text(), f"cards={n_cards}")
    badge = page.locator(".artifact-ext-badge").first.inner_text()
    check("⑨F6 类型标签=「文档 · MD」（类型词+格式，非裸后缀）", badge == "文档 · MD", badge)
    more_btn.click()
    page.wait_for_timeout(200)
    check("⑨F5 展开后 5 件全渲染 + 折叠行消失",
          page.locator(".artifact-card").count() == 5 and page.locator(".artifact-more").count() == 0)
    ve_tool = page.locator(".verify-card .verify-row").first.inner_text().replace("\n", " ")
    check("⑨F3 全真工具任务=「1 次工具调用 · 均为真实执行」且无 amber、无绿",
          "均为真实执行" in ve_tool
          and page.locator(".verify-card .pill-amber").count() == 0,
          ve_tool)
    # 「均为真实执行」颜色红线：中性墨（ink-soft），绝不给绿——绿解锁是性能盘
    # 真结果接入后的项目级决策（信任色锁：绿=仅 REAL）。
    real_color = page.locator(".verify-card .verify-row").first.locator(".verify-text").evaluate(
        "el => getComputedStyle(el).color")
    check("⑨F3 「均为真实执行」中性墨不给绿",
          real_color == resolved_color(page, "var(--ink-soft)"), real_color)
    # 页头批量 tag 不给绿（3-lens trust P2）：成功计数=中性 info，绝无 success
    # 绿 tag；核验段批量行同数据同屏一种信任信号（失败>0 计数染红）。
    header = page.locator(".page-header")
    check("⑨F3' 页头批量成功 tag 中性不给绿（同屏同数据一种信号）",
          "成功 4" in header.inner_text() and header.locator(".el-tag--success").count() == 0)
    vfail = page.locator(".verify-card .verify-fail-count")
    check("⑨F3' 核验批量行失败计数染红（红=仅真失败）",
          vfail.count() == 1 and vfail.evaluate("el => getComputedStyle(el).color") == resolved_color(page, "var(--trust-fail)"))
    page.screenshot(path=str(SHOTS / "artifact_fold_verify_real_light.png"), full_page=True)

    # ── ⑨g F4' cancelled 报中断时刻不报时长（3-lens trust P2 补针）＋
    #    ⑨h F3'' 真实分级遮蔽下签发行诚实降级（3-lens trust P1 回归网）────────
    # task_c 补 finished_at：真实后端 set_task_status 对任意终态（含 cancelled）
    # 必写 finished_at（repos.is_terminal），夹具不写就是不自洽故事。无 started_at
    # =从 created/queued 直接取消的合法路径 → 时长 null、时刻在场。
    _db("UPDATE tasks SET finished_at=? WHERE id=?", ("2026-07-15T04:00:00+00:00", task_c))
    page.goto(BASE + f"/tasks/{task_c}", wait_until="networkidle")
    page.wait_for_selector(".completion-seal", timeout=8000)
    seal_c = page.locator(".seal-text").inner_text()
    check("⑨F4' 取消盖章=时刻不时长（已取消 · HH:MM，无「工作/进行了」）",
          "已取消" in seal_c and _re.search(r"(\d{2}-\d{2} )?\d{2}:\d{2}$", seal_c.strip()) is not None
          and "工作" not in seal_c and "进行了" not in seal_c, seal_c)
    # 任务 F：completed+真实签发链+tool_runs+**sensitive 分级**——分级门在 events
    # 端点真实遮蔽 payload（ADR-0025 redact_rows），签发行必须降级「签发记录
    # 不可用（内容受限）」，绝不呈现「未经人工签发流程」（对已发生事实的否定）。
    resp_f = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针F"}})
    assert resp_f.status_code < 300, resp_f.text
    task_f = resp_f.json()["id"]
    _db("UPDATE tasks SET status='completed', started_at=?, finished_at=?, data_classification='sensitive' WHERE id=?",
        ("2026-07-15T05:00:00+00:00", "2026-07-15T05:01:00+00:00", task_f))
    _db("INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("evt_craft_f1", task_f, "hello_agent", "review_approved", "info", "人工已批准",
         json.dumps({"reviewer": "验收工程师"}), "2026-07-15T05:00:30+00:00"))
    _db("INSERT INTO tool_runs (task_id, tool_id, tool_version, mock, status, input_json, started_at, finished_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (task_f, "real_writer", "1.0.0", 0, "success", "{}",
         "2026-07-15T05:00:10+00:00", "2026-07-15T05:00:20+00:00"))
    page.goto(BASE + f"/tasks/{task_f}", wait_until="networkidle")
    page.wait_for_selector(".verify-card", timeout=8000)
    vf = page.locator(".verify-card").inner_text()
    check("⑨F3'' 分级遮蔽下签发行诚实降级（不可用≠未经签发）",
          "签发记录不可用" in vf and "未经人工签发流程" not in vf, vf[:120])

    # ══ ⑩ 批次三 G1-G4（desktop-restudy 深度打磨）═══════════════════════════

    # ── ⑩a G1 工作日志头贴地形态（cd-collapsed-blocks 纯灰字+发丝线三明治）──
    page.goto(BASE + f"/tasks/{task_a}", wait_until="networkidle")
    page.wait_for_selector(".worklog-head", timeout=8000)
    g1 = page.locator(".worklog-head").first.evaluate(
        """el => { const s = getComputedStyle(el);
             return { bg: s.backgroundColor, radius: s.borderRadius,
                      top: s.borderTopWidth, bottom: s.borderBottomWidth,
                      left: s.borderLeftWidth, right: s.borderRightWidth }; }"""
    )
    check("⑩G1 工作日志头贴地（背景透明+左右无边+上下发丝线+无圆角）",
          g1["bg"] in ("rgba(0, 0, 0, 0)", "transparent") and g1["top"] == "1px"
          and g1["bottom"] == "1px" and g1["left"] == "0px" and g1["right"] == "0px"
          and g1["radius"] == "0px",
          str(g1))
    g1w = page.locator(".worklog-head-text").first.evaluate("el => getComputedStyle(el).fontWeight")
    check("⑩G1 头行灰字语法（字重 500，非盒装标题 600）", g1w == "500", g1w)

    # ── ⑩b G2 工作态头行三段式（状态词 · 时间 · 真实事件计数）────────────────
    # task_d（running）种一条真实事件保证计量段有数据——三段式的计量轴用落库
    # 事件计数，不编 token。
    _db("INSERT INTO task_events (event_id, task_id, agent_id, event_type, level, message, payload_json, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        ("evt_craft_d1", task_d, "hello_agent", "agent_log", "info", "运行观察", "{}",
         datetime.now(timezone.utc).isoformat()))
    page.goto(BASE + f"/tasks/{task_d}", wait_until="networkidle")
    page.wait_for_selector(".worklog-head-text", timeout=8000)
    g2a = page.locator(".worklog-head-text").inner_text()
    check("⑩G2 工作态头行三段式（正在处理 · 已 X · N 条事件）",
          _re.match(r"^正在处理 · 已 .+ · \d+ 条事件$", g2a) is not None, g2a)

    # 完成态零事件任务：头行绝不显示「0 条事件」（cd-bg-tasks-panel 零值不显示）。
    resp_g = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "工艺批探针G"}})
    assert resp_g.status_code < 300, resp_g.text
    task_g = resp_g.json()["id"]
    _db("UPDATE tasks SET status='completed', started_at=?, finished_at=? WHERE id=?",
        ("2026-07-15T06:00:00+00:00", "2026-07-15T06:00:42+00:00", task_g))
    _db("DELETE FROM task_events WHERE task_id=?", (task_g,))
    page.goto(BASE + f"/tasks/{task_g}", wait_until="networkidle")
    page.wait_for_selector(".worklog-head-text", timeout=8000)
    g2b = page.locator(".worklog-head-text").inner_text()
    check("⑩G2 完成态零事件头行无「条事件」段（零值豁口）",
          g2b.startswith("已处理") and "条事件" not in g2b, g2b)

    # ── ⑩c G3+G4 状态中心收件箱行级活面───────────────────────────────────────
    page.locator(".status-dock").click()
    page.wait_for_selector(".sc-group-label.working", timeout=8000)
    # ② W0 全局工具类（自冷态今日页迁入——批次四 Q2 零计数收敛后，num-token
    #   只在真实计数 >0 处出现；此刻待签组头带真实计数）。
    num = page.locator(".sc-group-label .num-token").first
    num_style = num.evaluate("el => { const s = getComputedStyle(el); return s.fontFamily + '|' + s.fontVariantNumeric; }")
    check("②.num-token 走 mono+tabular-nums", ("Mono" in num_style or "monospace" in num_style) and "tabular-nums" in num_style,
          num_style)
    working_sub = page.locator(".sc-group:has(.sc-group-label.working) .sc-item-sub").first
    check("⑩G3 运行中行含活跳时长段（· 已 X）", "· 已 " in working_sub.inner_text(),
          working_sub.inner_text())
    # 掐断任务列表轮询：此后行内时长变化只可能来自组件内 1s ticker（与 F2 同
    # 「解耦可证伪」姿势——轮询驱动的旧实现在此必冻结）。
    ctx.route("**/api/tasks?*", lambda route: route.abort())
    g3_samples = {working_sub.inner_text()}
    for _ in range(3):
        page.wait_for_timeout(1100)
        g3_samples.add(working_sub.inner_text())
    ctx.unroute("**/api/tasks?*")
    check("⑩G3 断轮询后 3.3s 内行内时长仍逐秒递增（纯 ticker，≥3 个不同读数）",
          len(g3_samples) >= 3, str(g3_samples))

    # G4 行级紧凑时钟：待签行与最近落定行=同日 HH:MM（跨日 MM-DD HH:MM 前缀
    # 兼容），locale 全量串（含 / 与秒位）绝迹。
    wait_sub = page.locator(".sc-group:has(.sc-group-label.waiting) .sc-item-sub").first.inner_text()
    check("⑩G4 待签行紧凑时钟（无 locale 斜杠串）",
          _re.search(r"(\d{2}-\d{2} )?\d{2}:\d{2}$", wait_sub.strip()) is not None
          and "/" not in wait_sub, wait_sub)
    done_sub = page.locator(".sc-group:has(.sc-group-label:text('最近落定')) .sc-item-sub").first.inner_text()
    check("⑩G4 最近落定行紧凑时钟（无 locale 斜杠串）",
          _re.search(r"(\d{2}-\d{2} )?\d{2}:\d{2}$", done_sub.strip()) is not None
          and "/" not in done_sub, done_sub)
    page.screenshot(path=str(SHOTS / "statuscenter_inbox_live_light.png"))
    page.locator(".sc-close").click()
    page.wait_for_timeout(300)

    # ── ⑩d G4 孪生面：/me 任务行同 SSOT 紧凑时钟（3-lens 孪生点漏改教训——
    #    同一行级语法必须同批落到同类扫读面，绝不留一半 locale 串）────────────
    page.goto(BASE + "/me", wait_until="networkidle")
    page.wait_for_selector(".me-task-time", timeout=8000)
    me_time = page.locator(".me-task-time").first.inner_text()
    check("⑩G4 我的页任务行紧凑时钟（孪生面同 SSOT，无 locale 斜杠串）",
          _re.search(r"^(\d{2}-\d{2} )?\d{2}:\d{2}$", me_time.strip()) is not None
          and "/" not in me_time, me_time)

    # ══ ⑪ 批次四 Q1-Q5（新人极简：人话称呼/零值不显示/脚注收敛/门户最小化/
    #     token 进披露）═══════════════════════════════════════════════════════

    # ── ⑪a Q2 /me 零值格与反馈同律（页已在 /me，夹具任务全由登录身份创建）──
    me_contrib = API.get("/api/me/contributions", params={"since": since_iso}, timeout=10).json()
    me_fields = ["since_created", "since_completed", "waiting_review", "total_created"]
    me_ok = True
    me_detail = {}
    for f in me_fields:
        tile = page.locator(f'.me-stat[data-stat="{f}"]')
        v = me_contrib.get(f)
        if isinstance(v, int) and v > 0:
            ok_f = tile.count() == 1 and tile.locator(".me-stat-num").inner_text().strip() == str(v)
        else:
            ok_f = tile.count() == 0
        me_ok = me_ok and ok_f
        me_detail[f] = f"api={v} ui={'shown' if tile.count() else 'hidden'}"
    check("⑪Q2 /me 四格零值不渲染（语义对表 data-stat）", me_ok is True, str(me_detail))
    me_body = page.locator("body").inner_text()
    fb = me_contrib.get("feedback_count_approx")
    if isinstance(fb, int) and fb > 0:
        fb_ok = f"{fb} 条" in me_body and "按显示名近似统计" in me_body
    else:
        fb_ok = "还没有反馈记录" in me_body and "按显示名近似统计" not in me_body
    check("⑪Q2 /me 反馈零值收敛（0 条=一行空态且无近似口径注；>0 才显计数+口径）",
          fb_ok is True, f"fb={fb}")
    check("⑪Q3 /me 诚实缺口条压缩后红线语义在场（人是唯一签发者）",
          page.locator(".me-honest-gap").count() == 1 and "人是唯一签发者" in me_body)

    # ── ⑪b Q1 行级主文本人话称呼（夹具任务全部未命名——主名必须是注册表
    #    显示名，裸 task_ 前缀绝迹；名册路径实证靠 ⑪c 的失败对照）──────────
    page.locator(".status-dock").click()
    page.wait_for_selector(".sc-item-name", timeout=8000)
    sc_names = page.locator(".sc-item-name").all_inner_texts()
    check("⑪Q1 状态中心行主名=Agent 显示名（含注册表全名，非裸 id）",
          len(sc_names) > 0 and all(not n.strip().startswith("task_") for n in sc_names)
          and any("Hello Agent" in n for n in sc_names), str(sc_names[:5]))
    check("⑪Q3 状态中心口径短句（计数与清单双重范围声明保留，全句叙述只留任务台）",
          page.locator(".sc-foot-note").inner_text().strip() == "口径：计数与清单均来自最近 100 条任务窗口，窗口外不虚报。",
          page.locator(".sc-foot-note").inner_text())
    page.screenshot(path=str(SHOTS / "statuscenter_human_names_light.png"))
    page.locator(".sc-close").click()
    page.wait_for_timeout(300)

    # ── ⑪c Q1 名册缺位诚实回退（route-abort /api/agents → 整页重载重建模块
    #    缓存 → 行主名必须回退 id 切片，绝不编名字）─────────────────────────
    ctx.route("**/api/agents*", lambda route: route.abort())
    page.goto(BASE + "/today", wait_until="networkidle")
    page.wait_for_selector(".today-card-name", timeout=8000)
    fallback_names = page.locator(".today-card-name").all_inner_texts()
    check("⑪Q1 名册拉取失败→行主名诚实回退 id 切片（绝不编名字）",
          len(fallback_names) > 0 and all(_re.match(r"^task_[0-9a-f]+$", n.strip()) for n in fallback_names),
          str(fallback_names[:5]))
    ctx.unroute("**/api/agents*")

    # ── ⑪d Q1 名册恢复后今日页行主名人话（与 ⑪c 同页对照，证明差异只来自
    #    名册可用性）＋ Q2 有数据时组头计数照常渲染──────────────────────────
    page.goto(BASE + "/today", wait_until="networkidle")
    page.wait_for_selector(".today-card-name", timeout=8000)
    today_names = page.locator(".today-card-name").all_inner_texts()
    check("⑪Q1 今日页行主名=Agent 显示名（名册恢复对照）",
          len(today_names) > 0 and all(not n.strip().startswith("task_") for n in today_names)
          and any("Hello Agent" in n for n in today_names), str(today_names[:5]))
    waiting_head = page.locator(".today-section-head.waiting").inner_text()
    check("⑪Q2 有数据时组头计数照常（零值豁口不误伤非零）",
          _re.search(r"· \d+$", waiting_head.strip()) is not None, waiting_head)

    # ── ⑪e Q4 门户最小化（图例句撤下/色条退役/次级 meta 一行/诚实提示进
    #    title）──────────────────────────────────────────────────────────────
    page.goto(BASE + "/portal", wait_until="networkidle")
    page.wait_for_selector(".agent-card", timeout=8000)
    portal_body = page.locator("body").inner_text()
    check("⑪Q4 图例句撤下+色条退役（分类学不再预讲）",
          page.locator(".portal-legend").count() == 0 and page.locator(".cat-bar").count() == 0)
    meta_token = page.locator(".agent-meta-token").first.inner_text()
    check("⑪Q4 id·版本收次级 meta 一行（字面仍可见 DOM）",
          _re.search(r"^[a-z0-9_]+ · v\d", meta_token.strip()) is not None
          and "hello_agent" in portal_body and "不适用范围" in portal_body, meta_token)
    l0_tag = page.locator(".agent-tags .el-tag[title]").first
    l0_tip = l0_tag.get_attribute("title") or ""
    l0_cursor = l0_tag.evaluate("el => getComputedStyle(el).cursor")
    check("⑪Q4 成熟度徽章 title 携诚实提示（L0 勿依赖其结论）+ help 光标可发现性",
          "勿依赖" in l0_tip and l0_cursor == "help", f"tip={l0_tip} cursor={l0_cursor}")

    # ── ⑪f Q5 原始事件 token 只活在展开态（折叠=人话扫读面）────────────────
    page.goto(BASE + f"/tasks/{task_a}", wait_until="networkidle")
    page.wait_for_selector(".worklog-head", timeout=8000)
    collapsed_body = page.locator("body").inner_text()
    check("⑪Q5 折叠态无原始 token（task_created 绝迹于扫读面）",
          "task_created" not in collapsed_body, collapsed_body[collapsed_body.find("事件时间轴"):][:120])
    if page.locator(".worklog-timeline").count() == 0:
        page.locator(".worklog-head").first.click()
        page.wait_for_selector(".worklog-timeline", timeout=3000)
    expanded_body = page.locator("body").inner_text()
    check("⑪Q5 展开态原始 token 在场（检视面证据不减）",
          all(k in expanded_body for k in ("task_created", "tool_finished", "task_completed")))
    page.screenshot(path=str(SHOTS / "worklog_collapsed_human_light.png"))

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
