"""范式 2a 对话轴闭环验收（真浏览器）：召集任务零跳页 + 状态来找人全链。

把「零跳页」这一范式核心承诺纳入回归网（双镜头 P2：back=chat 回流分支此前
在 5 套 e2e 中执行次数=0，只有代码走读级信心）：
  ① 导引 orchestrate 方案（对话流内方案卡）；
  ② 从对话流点「去创建此任务」→ 创建页 URL 带 back=chat（GuidePage 专属，
     WorkbenchSession 召集不带——m8_collab_chain 断言④的详情页契约不受影响）；
  ③ 补全表单亲手提交 → **回流对话轴 /?c=conv_xxx**（不跳详情页）；
  ④ 回流后 hero 不闪现（restoring 门控）+ 对话流督战条原地亮起（排队中）；
  ⑤ 夹具把任务翻成 completed+产物 → 轮询窗口内「N 件产物」锚点行长出
     （夹具直写 temp DB：只为渲染路径提供 fixture，不冒充业务状态机行为）；
  ⑥ 点锚点 → 状态中心速览打开，产物区可见（加载失败也如实显示非静默）；
  ⑦ 对照组：workbench 路径召集 URL 不带 back=chat（回流不越界）。
  ⑧ 单 Agent 计划提交成功 → 先归档会话，再进入新任务详情（不回流已归档会话）。
  ⑨ concluded 会话深链直开 → 明显只读，composer 禁用，篡改 DOM 也不产生消息 POST。
  ⑩ 单 Agent 归档失败 → 已创建任务不丢，仍进详情，并明确告知会话未归档。
  ⑪ active→concluded 快速切换且响应逆序返回 → 目标会话仍只读，零消息 POST。

自包含：自起后端（tmp DB）+ stub gateway + 真 chromium，不起 worker。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m9_guide_loop_acceptance.py

截图落 docs/reviews/m9-guide-loop-shots/。
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

from _artifacts import artifact_dir

DIST = REPO / "frontend" / "dist"
SHOTS = artifact_dir(REPO, "m9-guide-loop-shots")

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m9_loop_"))


class _StubGateway:
    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        content = str((messages[-1] if messages else {}).get("content") or "")
        if "单 Agent" in content:
            plan = {
                "decision": "orchestrate",
                "analysis": "这个任务由一个故障树 Agent 承接。",
                "goal": "完成单 Agent 故障树分析。",
                "workflow": "fta_agent 独立出草案。",
                "agents": [
                    {"agent_id": "fta_agent", "role": "搭建并分析故障树", "rationale": "单 Agent 可完成", "prefilled_inputs": {"top_event": "供电完全丧失"}},
                ],
            }
            lead = "这个任务交给一个 Agent。"
        else:
            plan = {
                "decision": "orchestrate",
                "analysis": "这个任务要先做控制逻辑，再做故障树。",
                "goal": "完成双通道供电的控制逻辑与故障树分析。",
                "workflow": "control_logic_agent 先出控制逻辑，fta_agent 再做故障树。",
                "agents": [
                    {"agent_id": "control_logic_agent", "role": "生成控制逻辑状态机", "rationale": "结构化生成", "prefilled_inputs": {}},
                    {"agent_id": "fta_agent", "role": "搭建并分析故障树", "rationale": "推理辅助", "prefilled_inputs": {"top_event": "供电完全丧失"}},
                ],
            }
            lead = "这需要两个 Agent 接力协作。"
        reply = f"{lead}\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
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


def flip_task_completed_with_artifact(task_id: str) -> None:
    """夹具（temp DB 直写）：把 queued 任务翻成 completed+产物——只为前端渲染
    路径提供 fixture（锚点行/速览的响应性），不冒充业务状态机行为（真实完成
    链路由 m2 的 worker 路径验收）。"""
    import sqlite3

    conn = sqlite3.connect(WORK / "flai_os.db")
    conn.execute(
        "UPDATE tasks SET status='completed', output_file_ids=?, started_at=?, finished_at=? WHERE id=?",
        (json.dumps(["file_probe_0001"]), "2026-07-11T02:00:00+00:00", "2026-07-11T02:01:35+00:00", task_id),
    )
    conn.commit()
    conn.close()



from _auth import login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")
API = login_httpx(BASE)  # 直连 API 的已登录客户端（ADR-0019）


def force_legacy_plan_only(route) -> None:
    """M9 专测历史手工回流/异常恢复；产品 safe_auto 主链由 M6/M8 单独验收。"""
    request = route.request
    payload = json.loads(request.post_data or "{}")
    payload["execution_mode"] = "plan_only"
    payload.pop("request_id", None)
    headers = {k: v for k, v in request.headers.items() if k.lower() != "content-length"}
    route.continue_(
        post_data=json.dumps(payload, ensure_ascii=False),
        headers={**headers, "content-type": "application/json"},
    )

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    page.route("**/api/conversations/*/messages", force_legacy_plan_only)
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ① 导引对话 → orchestrate 方案卡
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("做双通道供电的控制逻辑和故障树")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    convs = API.get("/api/conversations?limit=5").json()
    conv_list = convs if isinstance(convs, list) else convs.get("items", [])
    conv_id = conv_list[0]["id"] if conv_list else None
    check("①对话流出方案卡+拿到会话id", bool(conv_id))
    page.screenshot(path=str(SHOTS / "1_plan_card.png"), full_page=True)

    # ② 对话流点 fta「去创建此任务」→ URL 带 back=chat
    page.locator(".agent-card").nth(1).get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    check("②GuidePage 召集路径带 back=chat", "back=chat" in page.url)

    # ③ 补全+亲手提交 → 回流对话轴（零跳页，2a 核心承诺）
    page.locator('textarea[placeholder="请填写系统描述"]').first.fill("双通道供电系统（发电机A/B + 汇流条 + 转换开关）")
    page.locator('input[placeholder="组件列表 第 1 项"]').first.fill("发电机A")
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_url(re.compile(r"\?c=conv_[0-9a-f]+"), timeout=8000)
    check("③提交后回流对话轴 /?c=<conv>（零跳页）", f"c={conv_id}" in page.url)

    # ④ 回流后：hero 不闪现（restoring 门控）+ 督战条原地亮起
    check("④回流落地不露空态 hero（restoring 门控）", page.locator(".guide-hero").count() == 0)
    page.wait_for_selector(".agent-status", timeout=8000)
    body = page.locator("body").inner_text()
    check("④督战条原地亮起（排队中）", page.locator(".agent-status").count() >= 1 and "排队中" in body)
    page.screenshot(path=str(SHOTS / "2_returned_live_chip.png"), full_page=True)

    # ⑤ 夹具翻完成+产物 → 轮询窗口内锚点行长出
    tasks = API.get(f"/api/conversations/{conv_id}/tasks").json()
    flip_task_completed_with_artifact(tasks[0]["id"])
    page.wait_for_selector(".status-artifact", timeout=12000)
    check("⑤产物锚点行长出（1 件产物）", "1 件产物" in page.locator(".status-artifact").inner_text())
    page.screenshot(path=str(SHOTS / "3_artifact_anchor.png"), full_page=True)

    # ⑥ 点锚点 → 速览面板打开，产物区如实可见
    page.locator(".status-artifact").click()
    page.wait_for_selector(".sc-shell", timeout=5000)
    check("⑥锚点直开速览面板", page.locator(".sc-back").count() == 1)
    # drawer 外壳先开、任务详情随后异步拉取；必须等真实产物区出现，不能在
    # v-loading 的空壳瞬间取 inner_text 造竞态假红。
    expect(page.locator(".peek-label").filter(has_text="产物")).to_be_visible(timeout=8000)
    peek_body = page.locator(".sc-body").inner_text()
    check(
        "⑥速览产物区可见（失败也如实显示非静默）",
        "产物" in peek_body,
        f"visible={page.locator('.sc-shell').is_visible()} body={peek_body[:300]!r}",
    )
    page.screenshot(path=str(SHOTS / "4_peek_from_anchor.png"))
    page.keyboard.press("Escape")
    page.wait_for_timeout(300)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)

    # ⑦ 对照组：workbench 召集路径不带 back=chat（回流不越界；
    #    「提交后落详情页」由 m8_collab_chain 断言④实测覆盖，此处不重复）
    page.goto(BASE + f"/workbench/{conv_id}", wait_until="networkidle")
    page.wait_for_selector(".member", timeout=5000)
    page.locator(".member").nth(0).get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    check("⑦workbench 召集路径不带 back=chat（契约不越界）", "back=chat" not in page.url)

    # ⑧ 单 Agent：创建成功后必须先 conclude，再落新任务详情；
    #    UI-PARADIGM Phase 2a 明确 conclude_after 不回流已归档会话。
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("请只用单 Agent 完成故障树分析")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    single_convs = API.get("/api/conversations?limit=5").json()
    single_conv_list = single_convs if isinstance(single_convs, list) else single_convs.get("items", [])
    single_conv_id = single_conv_list[0]["id"]
    page.get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    page.locator('textarea[placeholder="请填写系统描述"]').first.fill("双通道供电系统")
    page.locator('input[placeholder="组件列表 第 1 项"]').first.fill("发电机A")
    held_conclude_routes = []

    def hold_single_conclude(route) -> None:
        # 不 continue/fulfill：把真请求挂起，以可观测路由证明前端确实 await。
        held_conclude_routes.append(route)

    single_conclude_pattern = f"**/api/conversations/{single_conv_id}/conclude"
    page.route(single_conclude_pattern, hold_single_conclude)
    page.get_by_role("button", name="提交任务").click()
    for _ in range(50):
        if held_conclude_routes:
            break
        page.wait_for_timeout(20)
    page.wait_for_timeout(350)  # 超过提交动效时长；fire-and-forget 旧实现会在此时已跳走
    pending_conv = API.get(f"/api/conversations/{single_conv_id}").json()
    check(
        "⑧conclude 未完成前不得离开创建页",
        bool(held_conclude_routes)
        and pending_conv.get("status") == "active"
        and "/tasks/new" in page.url,
        f"held={len(held_conclude_routes)} status={pending_conv.get('status')} url={page.url}",
    )
    single_tasks = API.get(f"/api/conversations/{single_conv_id}/tasks").json()
    single_task_id = single_tasks[0]["id"] if single_tasks else ""
    held_conclude_routes[0].continue_()
    page.wait_for_url(re.compile(rf"/tasks/{re.escape(single_task_id)}$"), timeout=5000)
    page.unroute(single_conclude_pattern, hold_single_conclude)
    single_conv = API.get(f"/api/conversations/{single_conv_id}").json()
    check(
        "⑧单 Agent 先归档会话再落任务详情",
        single_conv.get("status") == "concluded" and page.url.endswith(f"/tasks/{single_task_id}"),
        f"status={single_conv.get('status')} url={page.url} task={single_task_id}",
    )

    # ⑨ 已归档会话即使被深链直开，也必须明显只读；双层守卫：
    #    控件 disabled 防正常误操作，send 硬守卫防 DOM 篡改/程序触发落 POST。
    message_posts: list[str] = []

    def record_message_post(request) -> None:
        if request.method == "POST" and f"/api/conversations/{single_conv_id}/messages" in request.url:
            message_posts.append(request.url)

    page.on("request", record_message_post)
    page.goto(BASE + f"/?c={single_conv_id}", wait_until="networkidle")
    textarea = page.locator(".composer textarea")
    check(
        "⑨已归档会话明显只读且 composer 禁用",
        "会话已归档，只读展示" in page.locator("body").inner_text()
        and textarea.is_disabled()
        and page.get_by_role("button", name="发送").is_disabled(),
        f"disabled={textarea.is_disabled()} body={page.locator('body').inner_text()[-240:]}",
    )
    textarea.evaluate(
        """el => {
          el.disabled = false;
          el.value = '已归档会话不应发送';
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
        }"""
    )
    page.wait_for_timeout(500)
    check("⑨已归档会话 send 硬守卫零 POST", not message_posts, f"posts={message_posts}")

    # ⑩ conclude 是 createTask 之后的次级收口：失败不得把已建任务伪装成未创建，
    #    也不得将用户送回 active 对话；进任务详情并诚实告知归档欠账。
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("请只用单 Agent 完成故障树分析，验证归档失败")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    failure_convs = API.get("/api/conversations?limit=5").json()
    failure_conv_list = failure_convs if isinstance(failure_convs, list) else failure_convs.get("items", [])
    failure_conv_id = failure_conv_list[0]["id"]
    page.get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(re.compile(r"/tasks/new"), timeout=5000)
    page.locator('textarea[placeholder="请填写系统描述"]').first.fill("双通道供电系统")
    page.locator('input[placeholder="组件列表 第 1 项"]').first.fill("发电机A")

    def reject_conclude(route) -> None:
        route.fulfill(
            status=503,
            content_type="application/json",
            body=json.dumps({"detail": "归档服务暂不可用"}, ensure_ascii=False),
        )

    conclude_pattern = f"**/api/conversations/{failure_conv_id}/conclude"
    page.route(conclude_pattern, reject_conclude)
    page.get_by_role("button", name="提交任务").click()
    page.wait_for_timeout(1500)
    failure_tasks = API.get(f"/api/conversations/{failure_conv_id}/tasks").json()
    failure_task_id = failure_tasks[0]["id"] if failure_tasks else ""
    failure_conv = API.get(f"/api/conversations/{failure_conv_id}").json()
    warning_visible = page.locator(".el-message--warning").filter(has_text="任务已创建，但会话归档失败").count() > 0
    check(
        "⑩归档失败不丢任务、落详情且诚实告警",
        bool(failure_task_id)
        and failure_conv.get("status") == "active"
        and page.url.endswith(f"/tasks/{failure_task_id}")
        and warning_visible,
        f"task={failure_task_id} status={failure_conv.get('status')} url={page.url} warning={warning_visible}",
    )
    page.unroute(conclude_pattern, reject_conclude)

    # ⑪ 快速从 active A 切到 concluded B：先挂起 A 的恢复响应，让 B 先返回，
    #    再释放过期 A。逆序响应不得把 URL 已指向的 B 篡改回可发送的 A。
    active_response = API.post("/api/conversations", json={"agent_id": "guide_agent"})
    active_response.raise_for_status()
    race_active_id = active_response.json()["id"]
    concluded_response = API.post("/api/conversations", json={"agent_id": "guide_agent"})
    concluded_response.raise_for_status()
    race_concluded_id = concluded_response.json()["id"]
    conclude_response = API.post(f"/api/conversations/{race_concluded_id}/conclude")
    conclude_response.raise_for_status()
    race_active_payload = API.get(f"/api/conversations/{race_active_id}").json()
    race_concluded_payload = API.get(f"/api/conversations/{race_concluded_id}").json()

    page.goto(BASE + "/", wait_until="networkidle")
    race_convs = API.get("/api/conversations?limit=30").json()
    race_conv_list = race_convs if isinstance(race_convs, list) else race_convs.get("items", [])
    race_indices = {conv["id"]: index for index, conv in enumerate(race_conv_list)}
    if race_active_id not in race_indices or race_concluded_id not in race_indices:
        raise RuntimeError("竞态验收夹具会话未出现在左栏最近 30 条中")

    held_active_loads = []

    def hold_active_load(route) -> None:
        # 不 continue/fulfill：稳定制造 A 比 B 更晚返回的真实浏览器请求。
        held_active_loads.append(route)

    def fulfill_concluded_load(route) -> None:
        route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps(race_concluded_payload, ensure_ascii=False),
        )

    race_active_pattern = f"**/api/conversations/{race_active_id}"
    race_concluded_pattern = f"**/api/conversations/{race_concluded_id}"
    page.route(race_active_pattern, hold_active_load)
    page.route(race_concluded_pattern, fulfill_concluded_load)

    page.locator(".convo-item").nth(race_indices[race_active_id]).click()
    for _ in range(50):
        if held_active_loads:
            break
        page.wait_for_timeout(20)
    if not held_active_loads:
        raise RuntimeError("active 会话恢复请求未被挂起")

    page.locator(".convo-item").nth(race_indices[race_concluded_id]).click()
    page.wait_for_url(re.compile(rf"\?c={re.escape(race_concluded_id)}$"), timeout=5000)
    expect(page.locator(".conversation-readonly")).to_be_visible(timeout=5000)
    held_active_loads[0].fulfill(
        status=200,
        content_type="application/json",
        body=json.dumps(race_active_payload, ensure_ascii=False),
    )
    page.wait_for_timeout(350)

    race_textarea = page.locator(".composer textarea")
    race_state_ok = (
        page.url.endswith(f"?c={race_concluded_id}")
        and page.locator(".conversation-readonly").is_visible()
        and race_textarea.is_disabled()
        and page.get_by_role("button", name="发送").is_disabled()
    )
    check(
        "⑪逆序响应后仍保持目标 concluded 会话只读",
        race_state_ok,
        f"url={page.url} readonly={page.locator('.conversation-readonly').count()} disabled={race_textarea.is_disabled()}",
    )

    race_message_posts: list[str] = []

    def record_race_message_post(request) -> None:
        if request.method == "POST" and re.search(r"/api/conversations/[^/]+/messages$", request.url):
            race_message_posts.append(request.url)

    page.on("request", record_race_message_post)
    race_textarea.evaluate(
        """el => {
          el.disabled = false;
          el.value = '过期 active 响应不应恢复发送';
          el.dispatchEvent(new Event('input', { bubbles: true }));
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', code: 'Enter', bubbles: true }));
        }"""
    )
    page.wait_for_timeout(500)
    check("⑪逆序响应后 send 硬守卫零 POST", not race_message_posts, f"posts={race_message_posts}")
    page.unroute(race_active_pattern, hold_active_load)
    page.unroute(race_concluded_pattern, fulfill_concluded_load)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M9 GUIDE LOOP ALL GREEN' if not failed else 'M9 GUIDE LOOP FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
