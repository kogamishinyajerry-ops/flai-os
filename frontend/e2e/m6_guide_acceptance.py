"""M6 导引 Agent 全链 UI 走查（可重跑评审证据，ADR-0012）。

自包含：脚本自起后端（tmp db，绝不碰真实 data/）+ 注入 **stub gateway**（本机无
内网 key，真实对话不可跑；stub 返回一条确定的推荐，验证 UI 全链）+ 真 chromium。

覆盖导引全链：
  ① 导引页只有文字/附件两个原始输入 → ② 发一句需求并带附件 → ③ 系统自动
  路由，路由依据默认折叠、按需披露 → ④ 全方案输入齐备后只出现一个「按方案
  开工」主按钮 → ⑤ 原地原子创建任务，不跳 /tasks/new、不让工程师填写字段；
  ⑥ 失败任务回到同一文字/附件入口，重新开工后自动保留 retry_of 血缘；产物
  放行仍由人完成。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" python frontend/e2e/m6_guide_acceptance.py

截图落 docs/reviews/m6-guide-shots/（每次重跑覆盖）。
"""
from __future__ import annotations

import json
import re
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
SHOTS = REPO / "docs" / "reviews" / "m6-guide-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.core.errors import ModelUpstreamError
from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m6_guide_"))


class _StubGateway:
    """确定文本 stub：导引首轮即返回一份 orchestrate 计划（M8 编排官），召集
    fta_agent——从对话/附件自动整理齐全部 required 输入 + 带分工 role，外加一个
    非法字段 bogus 让确定性校验剥离（展示 stripped 告警）。

    fail_next=True 时下一次 chat 抛 ModelUpstreamError（→ API 502「本轮零落库」），
    用于验收失败轮的 UI 契约：乐观 user 气泡回滚 + 草稿还原，重试不堆重复气泡
    （Codex R1-P2）。"""

    def __init__(self) -> None:
        self.fail_next = False
        self.delay_next_seconds = 0.0

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise ModelUpstreamError("stub 注入的上游失败（验收失败轮 UI 回滚）")
        delay = self.delay_next_seconds
        self.delay_next_seconds = 0.0
        if delay > 0:
            time.sleep(delay)
        plan = {
            "decision": "orchestrate",
            "analysis": "你要对双通道供电系统做故障树分析。",
            "goal": "对双通道供电系统完成故障树分析，定位供电完全丧失的根因。",
            "workflow": "由故障树分析 Agent 独立完成。",
            "agents": [
                {
                    "agent_id": "fta_agent",
                    "role": "搭建并分析故障树",
                    "rationale": "你的需求是对供电系统做故障树分析，fta_agent 正是做这个的。",
                    "prefilled_inputs": {
                        "top_event": "供电完全丧失",
                        "system_description": "双通道供电系统（发电机 A/B、汇流条与转换开关）",
                        "components": ["发电机A", "发电机B", "汇流条", "转换开关"],
                        "bogus": "该字段不属于该 Agent",
                    },
                }
            ],
        }
        reply = (
            "明白了，你要对双通道供电系统做故障树分析。系统已整理执行输入并自动路由。\n"
            f"<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
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

# 健康就绪后 app.state 已装配：注入 stub（本机无内网 key，用 stub 验 UI 全链）。
stub = _StubGateway()
app.state.conversation_service.model_gateway = stub

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def flip_task_failed(task_id: str) -> None:
    """仅为失败回流 UI 提供临时库状态；真实 worker 失败链由状态机测试覆盖。"""
    import sqlite3

    conn = sqlite3.connect(WORK / "flai_os.db")
    conn.execute(
        "UPDATE tasks SET status='failed', error_message=?, updated_at=? WHERE id=?",
        ("验收夹具：第一次执行失败", "2026-08-01T08:00:00+00:00", task_id),
    )
    conn.commit()
    conn.close()



from _auth import E2E_PASSWORD, login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")
seed_user(WORK / "flai_os.db", "新同事", username="xin_tongshi")
API = login_httpx(BASE)

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ① 导引页 = 统一入口（首页）
    page.goto(BASE + "/", wait_until="networkidle")
    body = page.locator("body").inner_text()
    # 2b 契约重立：「智能导引」原命中侧栏导航项，双 Surface 后导航收敛为
    # 「对话/任务台」——改锚 hero 主标题（导引页身份的稳定语义锚）。
    shell_ok = (
        "说说你要做的工程活儿" in body
        and "系统会在后台自动编排所需能力" in body
        and page.locator(".guide-page textarea").count() == 1
        and page.locator('.guide-page input[type="file"]').count() == 1
        and page.locator(
            '.guide-page input:not([type="file"]), .guide-page select, '
            '.guide-page form, .guide-page [contenteditable="true"]'
        ).count() == 0
        and page.get_by_role("button", name="浏览可用 Agent").count() == 0
    )
    check("①导引页可达：唯一文字输入+附件入口，其余能力后台编排", shell_ok, body[:260])
    page.screenshot(path=str(SHOTS / "1_guide_empty.png"), full_page=True)

    # ② 失败轮 UI 契约（Codex R1-P2 / M7 扩附件）：后端失败零落库，前端同样
    #    回滚乐观气泡并还原草稿；附件 chips 留在待发区（已上传项重试不重传）。
    REQUEST_TEXT = "我要对双通道供电系统做故障树分析，顶事件是供电完全丧失，工况见附件"
    ATTACH_NAME = "工况数据.txt"
    attach_path = WORK / ATTACH_NAME
    attach_path.write_text("双通道供电，顶事件：供电完全丧失；工况共 3 组。", encoding="utf-8")
    page.locator(".composer input[type=file]").set_input_files(str(attach_path))
    composer_chip = ATTACH_NAME in page.locator(".composer").inner_text()
    check("②附件选中入待发区（chip 可见）", composer_chip, page.locator(".composer").inner_text()[:120])

    stub.fail_next = True
    page.locator(".composer textarea").fill(REQUEST_TEXT)
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".page-alert")).to_be_visible(timeout=8000)
    user_bubbles_after_fail = page.locator(".bubble-row.user").count()
    draft_restored = page.locator(".composer textarea").input_value()
    chip_kept = ATTACH_NAME in page.locator(".composer").inner_text()
    check(
        "②失败轮：乐观气泡回滚+草稿还原+附件 chips 保留（与后端『失败零落库』对齐）",
        user_bubbles_after_fail == 0 and draft_restored == REQUEST_TEXT and chip_kept,
        f"user_bubbles={user_bubbles_after_fail} draft={draft_restored[:40]!r} chip_kept={chip_kept}",
    )
    page.screenshot(path=str(SHOTS / "1b_failed_turn_rollback.png"), full_page=True)

    # ②' 重试同一句（草稿已还原、附件已在待发区，直接再点发送；stub 已恢复健康）
    page.get_by_role("button", name="发送").click()

    # ③ 导引返回协作方案卡片（M8 orchestrate）。路由细节默认折叠，避免把
    #    Agent 名册和结构化输入变成常驻字段墙；工程师需要时再展开查看依据。
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    disclosure = page.locator(".route-disclosure")
    check(
        "③自动路由摘要常驻、路由细节默认折叠",
        "已自动编排" in page.locator(".route-summary").inner_text()
        and disclosure.get_attribute("open") is None
        and page.locator(".agent-card").first.is_visible() is False,
    )
    disclosure.locator("summary").click()
    expect(page.locator(".agent-card").first).to_be_visible(timeout=3000)
    body = page.locator("body").inner_text()
    reco_ok = (
        "协作方案" in body
        and "故障树" in body
        and "分工" in body          # 编排官给出的 role
        and "已从对话整理 3 项执行输入" in body
        and "供电完全丧失" in body
        and "已剔除不合法字段" in body  # bogus 被确定性剥离并告警
        and "bogus" in body
    )
    check("③按需披露：路由依据+分工+自动整理输入+非法字段剔除告警", reco_ok, body[-500:])
    check(
        "③重试后无重复 user 气泡（幂等重试全链）",
        page.locator(".bubble-row.user").count() == 1,
        f"count={page.locator('.bubble-row.user').count()}",
    )
    check(
        "③user 气泡带附件 chip（M7）",
        ATTACH_NAME in page.locator(".bubble-row.user").first.inner_text(),
        page.locator(".bubble-row.user").first.inner_text()[:120],
    )
    check("③'系统代路由、人掌开工与签发'红线文案可见", "签发权" in body and "开工由你确认" in body, "")
    page.screenshot(path=str(SHOTS / "2_recommendation.png"), full_page=True)

    # ④ 全方案 ready 才给一个主按钮；成员行不提供手工 Agent/参数入口。
    open_btn = page.get_by_role("button", name="按方案开工")
    expect(open_btn).to_be_visible(timeout=8000)
    check(
        "④全方案就绪：只有一个『按方案开工』主按钮，零字段表单/成员级创建钮",
        page.locator(".plan-foot .cta-clay").count() == 1
        and page.get_by_role("button", name="去创建此任务").count() == 0
        and page.locator(".plan-card input, .plan-card textarea, .plan-card select").count() == 0,
    )
    convs = API.get("/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    check("④按钮渲染不等于自动开工：点击前任务数为 0", bool(conv_id) and len(API.get(f"/api/conversations/{conv_id}/tasks").json()) == 0)

    # ⑤ 人只确认开工；系统把已整理输入和唯一 Agent 的附件原地带入任务。
    open_btn.click()
    expect(page.locator(".agent-status")).to_be_visible(timeout=8000)
    tasks = API.get(f"/api/conversations/{conv_id}/tasks").json() if conv_id else []
    task = tasks[0] if tasks else {}
    detail = API.get(f"/api/tasks/{task['id']}").json() if task else {}
    inline_ok = (
        len(tasks) == 1
        and task.get("agent_id") == "fta_agent"
        and (detail.get("inputs") or {}).get("top_event") == "供电完全丧失"
        and "bogus" not in (detail.get("inputs") or {})
        and len(detail.get("input_file_ids") or []) == 1
        and "/tasks/new" not in page.url
        and f"c={conv_id}" in page.url
    )
    check("⑤确认开工后原地建任务：合法输入+附件自动带入，零 /tasks/new 字段墙", inline_ok,
          json.dumps(detail, ensure_ascii=False)[:300])
    page.screenshot(path=str(SHOTS / "3_inline_started.png"), full_page=True)

    # ⑥ 失败恢复仍只有同一个文字/附件入口。旧任务 id 是系统级上下文，不显示
    # 成字段；新方案根任务由 batch 自动写 retry_of，成功后一次性消费 query。
    origin_task_id = task["id"]
    flip_task_failed(origin_task_id)

    # ⑥a retry_of 新会话首发竞态：内部把新 conversation id 镜像到 URL 时，组合
    # watcher 只能消费这一拍，不能 loadConversation(空会话) 抹掉正在发送的乐观轮。
    # gateway 故意慢 1.5s，让 URL 已更新但 POST 尚未完成的 DOM 窗口稳定可观察。
    race_page = page.context.new_page()
    race_page.goto(BASE + f"/?retry_of={origin_task_id}", wait_until="networkidle")
    expect(race_page.locator(".composer-policy")).to_contain_text(
        "正在处理失败任务 · 审计血缘会自动保留", timeout=8000
    )
    race_text = "第一次执行失败，请结合新材料重新处理"
    race_attachment_name = "失败补充材料.txt"
    race_attachment = WORK / race_attachment_name
    race_attachment.write_text("失败现象：双通道同时掉电；请保留原任务血缘。", encoding="utf-8")
    race_page.locator('.composer input[type="file"]').set_input_files(str(race_attachment))
    race_page.locator(".composer textarea").fill(race_text)
    stub.delay_next_seconds = 1.5
    race_page.get_by_role("button", name="发送").click()
    race_page.wait_for_url(
        re.compile(rf"/\?c=[^&]+&retry_of={origin_task_id}$"), timeout=8000
    )
    expect(race_page.locator(".ai-thinking")).to_be_visible(timeout=3000)
    inflight_user = race_page.locator(".bubble-row.user")
    inflight_ok = (
        inflight_user.count() == 1
        and race_text in inflight_user.inner_text()
        and race_attachment_name in inflight_user.inner_text()
    )
    check(
        "⑥a retry_of 新会话首发：内部 c 更新期间乐观文字与附件不消失",
        inflight_ok,
        f"url={race_page.url} bubbles={inflight_user.count()} text={inflight_user.inner_text()[:120] if inflight_user.count() else ''}",
    )
    expect(race_page.locator(".plan-card")).to_be_visible(timeout=8000)
    canonical_user = race_page.locator(".bubble-row.user")
    canonical_ok = (
        canonical_user.count() == 1
        and race_text in canonical_user.inner_text()
        and race_attachment_name in canonical_user.inner_text()
        and race_page.locator(".composer-files .file-chip").count() == 0
    )
    check(
        "⑥a retry_of 新会话首发完成：canonical 用户轮与附件仍保留且待发区已清空",
        canonical_ok,
        canonical_user.inner_text()[:160] if canonical_user.count() else "user bubble missing",
    )
    race_page.close()

    page.goto(BASE + f"/tasks/{origin_task_id}", wait_until="networkidle")
    retry_button = page.get_by_role("button", name="回到对话说明问题")
    expect(retry_button).to_be_visible(timeout=8000)
    retry_button.click()
    page.wait_for_url(re.compile(rf"/\?c={conv_id}&retry_of={origin_task_id}$"), timeout=8000)
    # URL 只是恢复意图；Guide 必须先 GET 权威任务并确认 status=failed，核对前
    # 主输入 fail-closed，也不得提前声称会保留审计血缘。
    expect(page.locator(".composer-policy")).to_contain_text(
        "正在处理失败任务 · 审计血缘会自动保留", timeout=8000
    )
    retry_shell_ok = (
        page.locator(".composer textarea").count() == 1
        and page.locator('.composer input[type="file"]').count() == 1
        and "正在处理失败任务 · 审计血缘会自动保留" in page.locator(".composer").inner_text()
        and page.get_by_role("button", name="按方案开工").count() == 0
    )
    check("⑥失败回流：只回文字/附件主输入，历史方案不可直接复活", retry_shell_ok, page.url)

    page.locator(".composer textarea").fill("第一次执行失败，请保留原目标重新处理")
    page.get_by_role("button", name="发送").click()
    retry_open = page.get_by_role("button", name="按方案开工")
    expect(retry_open).to_be_visible(timeout=8000)
    retry_open.click()
    deadline = time.time() + 8
    retry_tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        raw = API.get(f"/api/conversations/{conv_id}/tasks").json()
        retry_tasks = raw if isinstance(raw, list) else raw.get("items", [])
        if len(retry_tasks) == 2:
            break
        time.sleep(0.3)
    retry_task = next((item for item in retry_tasks if item.get("id") != origin_task_id), {})
    retry_detail = API.get(f"/api/tasks/{retry_task['id']}").json() if retry_task else {}
    lineage_ok = (
        len(retry_tasks) == 2
        and retry_detail.get("retry_of") == origin_task_id
        and f"c={conv_id}" in page.url
        and "retry_of=" not in page.url
        and "/tasks/new" not in page.url
    )
    check("⑥重新开工：系统自动写入 retry_of 血缘并消费一次性 query", lineage_ok,
          json.dumps(retry_detail, ensure_ascii=False)[:300])
    page.screenshot(path=str(SHOTS / "3b_retry_lineage.png"), full_page=True)

    # ── ⑧ 登录门（ADR-0019 真鉴权重立）：未登录首访被全屏拦下，真实登录后进入 ──
    fresh = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    fresh.goto(BASE + "/", wait_until="networkidle")
    gate_input = fresh.get_by_placeholder("用户名")
    gate_seen = gate_input.is_visible()
    gate_input.fill("xin_tongshi")
    fresh.get_by_placeholder("密码").fill(E2E_PASSWORD)
    fresh.locator(".welcome-gate__button").click()
    # 门下页面的 .hero-title 从一开始就在 DOM——必须等门真正卸载，不然断言
    # 跑在登录往返完成之前（竞态假红）
    fresh.wait_for_selector(".welcome-gate", state="detached", timeout=8000)
    fresh.wait_for_selector(".hero-title", timeout=5000)
    hero_body = fresh.locator("body").inner_text()
    no_more_ask = fresh.get_by_placeholder("用户名").count() == 0  # 门关即不再询问
    identity_shown = "新同事" in hero_body  # 侧栏身份行显示登录身份 display_name
    check("⑧登录门：未登录拦下→真实登录→进入且身份上侧栏", gate_seen and no_more_ask and identity_shown,
          f"gate={gate_seen} no_ask={no_more_ask} shown={identity_shown}")
    # ⑧' 门过后身份真被对话取到（created_by 服务端从会话派生）
    fresh.locator(".composer textarea").fill("你好")
    fresh.get_by_role("button", name="发送").click()
    fresh.wait_for_selector(".user-bubble", timeout=8000)
    check("⑧'门过后第一条消息可发出（会话身份生效）",
          fresh.locator(".user-bubble").count() >= 1,
          f"bubble={fresh.locator('.user-bubble').count()}")
    fresh.screenshot(path=str(SHOTS / "4_welcome_gate_passed.png"))
    fresh.close()

    # ── ⑧'' 存储不可用（隐私模式）：会话走 HttpOnly cookie 不依赖 localStorage
    # ——storage 全坏照样登录照样发消息（原 Codex 审 P1 回归的鉴权时代等价物）。──
    priv = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    priv.add_init_script("Storage.prototype.setItem = function() { throw new Error('storage disabled'); };")
    priv.goto(BASE + "/", wait_until="networkidle")
    priv.get_by_placeholder("用户名").fill("xin_tongshi")
    priv.get_by_placeholder("密码").fill(E2E_PASSWORD)
    priv.locator(".welcome-gate__button").click()
    priv.wait_for_selector(".welcome-gate", state="detached", timeout=8000)
    priv.wait_for_selector(".hero-title", timeout=5000)
    priv.locator(".composer textarea").fill("你好")
    priv.get_by_role("button", name="发送").click()
    priv.wait_for_selector(".user-bubble", timeout=8000)
    check("⑧''存储不可用：cookie 会话闭环（登录+第一条消息可发）", True)
    priv.close()

    # ── ⑨ 壳层硬规则：工程师只输入文字/附件；其余能力由后台编排并按需披露，
    # 不再用首屏 picker 让工程师做编排。──
    hon = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(hon.context, BASE)
    hon.goto(BASE + "/", wait_until="networkidle")
    shell_body = hon.locator("body").inner_text()
    check("⑨壳层零手工编排：无执行单元 picker/参数表单",
          hon.get_by_role("button", name="浏览可用 Agent").count() == 0
          and hon.locator(".agent-pick, .guide-context-rail, .intent-card").count() == 0
          and hon.locator(".guide-page textarea").count() == 1
          and hon.locator('.guide-page input[type="file"]').count() == 1
          and hon.locator(
              '.guide-page input:not([type="file"]), .guide-page select, '
              '.guide-page form, .guide-page [contenteditable="true"]'
          ).count() == 0
          and "系统会在后台自动编排所需能力" in shell_body,
          shell_body[:260])
    hon.close()

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M6 GUIDE ACCEPTANCE ALL GREEN' if not failed else 'M6 GUIDE ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
