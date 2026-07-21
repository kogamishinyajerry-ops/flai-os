"""M6 导引 Agent 全链 UI 走查（可重跑评审证据，ADR-0012）。

自包含：脚本自起后端（tmp db，绝不碰真实 data/）+ 注入 **stub gateway**（本机无
内网 key，真实对话不可跑；stub 返回一条确定的推荐，验证 UI 全链）+ 真 chromium。

覆盖导引全链：
  ① 导引页可达（统一入口）→ ② 发一句需求 → ③ 导引返回推荐卡片（Agent 名 +
  类型色标 + 成熟度 + 被剔除非法字段的告警）并被安全门零任务阻断 → ④ 新会话
  提供完整显式 JSON 后，平台零点击自动创建并入队任务；最终工程签发仍由人完成。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" python frontend/e2e/m6_guide_acceptance.py

截图落 docs/reviews/m6-guide-shots/（每次重跑覆盖）。
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
from urllib.parse import urlparse

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

DAG_CONTROL_INPUTS = {
    "system_name": "双通道供电控制",
    "states": ["OFF", "ON"],
    "transitions": [{"from": "OFF", "to": "ON", "condition": "收到启动指令"}],
}
DAG_FTA_INPUTS = {
    "top_event": "供电完全丧失",
    "system_description": "双通道供电控制系统",
    "components": ["主汇流条", "备用汇流条"],
}


class _StubGateway:
    """确定文本 stub：导引首轮即返回一份 orchestrate 计划（M8 编排官），召集
    fta_agent——top_event 合法预填 + 带分工 role，外加一个非法字段 bogus 让确定性
    校验剥离（展示 stripped 告警）。

    fail_next=True 时下一次 chat 抛 ModelUpstreamError（→ API 502「本轮零落库」），
    用于验收失败轮的 UI 契约：乐观 user 气泡回滚 + 草稿还原，重试不堆重复气泡
    （Codex R1-P2）。"""

    def __init__(self) -> None:
        self.fail_next = False
        self.chat_calls = 0

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.chat_calls += 1
        if self.fail_next:
            self.fail_next = False
            raise ModelUpstreamError("stub 注入的上游失败（验收失败轮 UI 回滚）")
        latest = messages[-1]["content"] if messages else ""
        if '"inputs_by_agent"' in latest and '"control_logic_agent"' in latest:
            plan = {
                "decision": "orchestrate",
                "contract": "guide_dag.v1",
                "analysis": "先确定性整理控制结构，再形成 FTA 人审草案。",
                "goal": "形成可审阅的供电失效分析草案。",
                "workflow": "control 节点产物定向传给唯一 FTA 叶节点。",
                "nodes": [
                    {
                        "node_id": "control",
                        "agent_id": "control_logic_agent",
                        "agent_version": "0.2.0",
                        "role": "确定性整理控制状态与转移",
                        "rationale": "先形成不依赖模型的结构化控制骨架。",
                        "prefilled_inputs": DAG_CONTROL_INPUTS,
                        "stripped_fields": [],
                        "depends_on": [],
                        "artifact_binding": {"mode": "none", "from_nodes": []},
                        "attachment_binding": {"mode": "none"},
                    },
                    {
                        "node_id": "fta",
                        "agent_id": "fta_agent",
                        "agent_version": "0.2.0",
                        "role": "基于控制骨架形成待人审的 FTA 草案",
                        "rationale": "唯一叶节点保留人工审核与签发边界。",
                        "prefilled_inputs": DAG_FTA_INPUTS,
                        "stripped_fields": [],
                        "depends_on": ["control"],
                        "artifact_binding": {"mode": "selected", "from_nodes": ["control"]},
                        "attachment_binding": {"mode": "current_turn"},
                    },
                ],
                "dropped_agents": [],
                "capped": False,
            }
            reply = (
                "已形成版本锁定的两节点协作图，附件只绑定到最终 FTA 人审节点。\n"
                f"<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
            )
            return {
                "content": reply,
                "token_usage": None,
                "model_name": "stub",
                "finish_reason": "stop",
            }
        explicit = '"system_description"' in latest and '"components"' in latest
        inputs = (
            {
                "top_event": "供电完全丧失",
                "system_description": "双通道供电系统",
                "components": ["发电机A", "发电机B"],
            }
            if explicit
            else {"top_event": "供电完全丧失", "bogus": "该字段不属于该 Agent"}
        )
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
                    "prefilled_inputs": inputs,
                }
            ],
        }
        reply = (
            "明白了，你要对双通道供电系统做故障树分析。为你召集故障树分析 Agent，并预填了顶事件。\n"
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



from _auth import E2E_PASSWORD, login_context, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")
seed_user(WORK / "flai_os.db", "新同事", username="xin_tongshi")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ① 导引页 = 统一入口（首页）
    page.goto(BASE + "/", wait_until="networkidle")
    body = page.locator("body").inner_text()
    # 2b 契约重立：「智能导引」原命中侧栏导航项，双 Surface 后导航收敛为
    # 「对话/任务台」——改锚 hero 主标题（导引页身份的稳定语义锚）。
    check(
        "①导引页可达且为统一入口",
        "说说你要做的工程活儿" in body and "满足安全门的方案会自动执行" in body,
        body[:200],
    )
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

    # ③ 导引返回协作方案卡片（M8 orchestrate）
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    body = page.locator("body").inner_text()
    reco_ok = (
        "协作方案" in body
        and "故障树" in body
        and "分工" in body          # 编排官给出的 role
        and "top_event" in body
        and "供电完全丧失" in body
        and "已剔除不合法字段" in body  # bogus 被确定性剥离并告警
        and "bogus" in body
    )
    check("③协作方案卡片：召集 Agent+分工+预填草案+非法字段剔除告警", reco_ok, body[-500:])
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
    check(
        "③阻断事实与最终人签边界同屏可见",
        "暂未执行" in body and "没有创建任务" in body and "最终工程签发" in body,
        "",
    )
    page.screenshot(path=str(SHOTS / "2_recommendation.png"), full_page=True)

    # ④ 含附件+非法字段的计划必须零任务，且不再出现手动创建兜底按钮。
    conn = app.state.conn_factory()
    try:
        blocked_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()
    check(
        "④安全门阻断时零任务、零创建页按钮",
        blocked_tasks == 0 and page.get_by_role("button", name="去创建此任务").count() == 0,
        f"tasks={blocked_tasks}",
    )

    # ⑤ 新会话给出完整、字段关系明确的 JSON：不点创建/提交，后端直接原子入队。
    page.goto(BASE + "/", wait_until="networkidle")
    safe_inputs = {
        "top_event": "供电完全丧失",
        "system_description": "双通道供电系统",
        "components": ["发电机A", "发电机B"],
    }
    page.locator(".composer textarea").fill(json.dumps(safe_inputs, ensure_ascii=False))
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".execution-strip:not(.blocked)")).to_be_visible(timeout=8000)
    body = page.locator("body").inner_text()
    conn = app.state.conn_factory()
    try:
        task_rows = conn.execute(
            "SELECT status, agent_id, created_by_username FROM tasks ORDER BY created_at"
        ).fetchall()
    finally:
        conn.close()
    auto_ok = (
        len(task_rows) == 1
        and dict(task_rows[0]) == {
            "status": "queued",
            "agent_id": "fta_agent",
            "created_by_username": "e2e_engineer",
        }
        and "已自动发起，无需手动创建" in body
        and page.get_by_role("button", name="去创建此任务").count() == 0
    )
    check("⑤完整显式 JSON 零点击自动创建并入队", auto_ok, f"tasks={[dict(r) for r in task_rows]}")
    check("⑤自动入队不冒充工程签发", "最终工程签发仍由你完成" in body, "")
    page.screenshot(path=str(SHOTS / "3_prefilled_create.png"), full_page=True)

    # ── ⑥ 版本化多 Agent DAG + 附件来源绑定 + 跨硬刷新幂等 ──
    # 真实浏览器网络 seam：消息 POST 必须先完整穿透到后端并提交；只把紧随其后的
    # 首次 canonical conversation GET 人为改成 503，模拟“服务端已提交、浏览器没拿到
    # 权威回执”。硬刷新后前端必须先 GET 权威历史；命中同 request_id 后清 outbox，
    # 绝不能再 POST 消息、再调用模型或再长出一套任务图。
    dag_page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(dag_page.context, BASE)
    dag_net: dict[str, Any] = {
        "conversation_id": None,
        "message_posts": 0,
        "message_committed": False,
        "canonical_gets": 0,
        "canonical_failures": 0,
        "reload_started": False,
        "conversation_ops_after_reload": [],
    }

    def route_dag_commit_then_lose_first_canonical_get(route, request) -> None:
        path = urlparse(request.url).path
        prefix = "/api/conversations/"
        suffix = "/messages"
        is_message_post = (
            request.method == "POST"
            and path.startswith(prefix)
            and path.endswith(suffix)
            and len(path) > len(prefix) + len(suffix)
        )
        if is_message_post:
            dag_net["message_posts"] += 1
            if dag_net["reload_started"] is True:
                dag_net["conversation_ops_after_reload"].append("POST")
            upstream = route.fetch()
            conversation_id = path[len(prefix) : -len(suffix)]
            if upstream.status == 200:
                dag_net["conversation_id"] = conversation_id
                dag_net["message_committed"] = True
            route.fulfill(response=upstream)
            return

        conversation_id = dag_net["conversation_id"]
        is_canonical_get = (
            request.method == "GET"
            and isinstance(conversation_id, str)
            and path == f"{prefix}{conversation_id}"
        )
        if is_canonical_get:
            dag_net["canonical_gets"] += 1
            if dag_net["reload_started"] is True:
                dag_net["conversation_ops_after_reload"].append("GET")
            if (
                dag_net["message_committed"] is True
                and dag_net["canonical_failures"] == 0
            ):
                dag_net["canonical_failures"] += 1
                route.fulfill(
                    status=503,
                    content_type="application/json",
                    body=json.dumps(
                        {"detail": "stub 丢失消息提交后的首次 canonical GET"},
                        ensure_ascii=False,
                    ),
                )
                return
        route.continue_()

    dag_page.route("**/api/conversations/**", route_dag_commit_then_lose_first_canonical_get)
    dag_page.goto(BASE + "/", wait_until="networkidle")
    dag_attach_name = "DAG工况来源.txt"
    dag_attach_path = WORK / dag_attach_name
    dag_attach_path.write_text(
        "当前轮唯一附件：双通道供电控制工况；仅供最终 FTA 草案节点引用。",
        encoding="utf-8",
    )
    dag_page.locator(".composer input[type=file]").set_input_files(str(dag_attach_path))
    dag_inputs_text = json.dumps(
        {
            "inputs_by_agent": {
                "control_logic_agent": DAG_CONTROL_INPUTS,
                "fta_agent": DAG_FTA_INPUTS,
            }
        },
        ensure_ascii=False,
    )
    conn = app.state.conn_factory()
    try:
        total_tasks_before_dag = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()
    chat_calls_before_dag = stub.chat_calls
    dag_page.locator(".composer textarea").fill(dag_inputs_text)
    dag_page.get_by_role("button", name="发送").click()
    expect(dag_page.locator(".page-alert")).to_be_visible(timeout=8000)
    dag_page.wait_for_function(
        "() => sessionStorage.getItem('flai.guide.safe_auto.outbox.v1') !== null",
        timeout=5000,
    )
    retained_outbox = dag_page.evaluate(
        "JSON.parse(sessionStorage.getItem('flai.guide.safe_auto.outbox.v1'))"
    )
    dag_conversation_id = dag_net["conversation_id"]
    conn = app.state.conn_factory()
    try:
        total_tasks_after_commit = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()
    committed_but_unconfirmed = (
        isinstance(dag_conversation_id, str)
        and dag_net["message_posts"] == 1
        and dag_net["canonical_failures"] == 1
        and retained_outbox["conversation_id"] == dag_conversation_id
        and retained_outbox["phase"] == "awaiting_confirmation"
        and len(retained_outbox["payload"]["file_ids"]) == 1
        and total_tasks_after_commit == total_tasks_before_dag + 2
        and stub.chat_calls == chat_calls_before_dag + 1
    )
    check(
        "⑥POST 已提交但首次权威 GET 丢失：两任务已原子落库且 outbox 保留",
        committed_but_unconfirmed,
        (
            f"net={dag_net} outbox={retained_outbox} "
            f"tasks={total_tasks_before_dag}->{total_tasks_after_commit} "
            f"chat={chat_calls_before_dag}->{stub.chat_calls}"
        ),
    )

    # 硬刷新（不是 SPA 路由切换）：只允许先读权威会话；恢复命中 request_id 后清空
    # sessionStorage。网络记录若出现 POST，或模型/任务增长，均立即假红。
    dag_net["reload_started"] = True
    dag_page.reload(wait_until="domcontentloaded")
    dag_page.wait_for_function(
        "() => sessionStorage.getItem('flai.guide.safe_auto.outbox.v1') === null",
        timeout=8000,
    )
    expect(dag_page.locator(".execution-strip:not(.blocked)")).to_be_visible(timeout=8000)
    dag_page.wait_for_load_state("networkidle")
    conn = app.state.conn_factory()
    try:
        total_tasks_after_reload = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
    finally:
        conn.close()
    reload_ops = dag_net["conversation_ops_after_reload"]
    no_replay_after_reload = (
        reload_ops
        and reload_ops[0] == "GET"
        and "POST" not in reload_ops
        and dag_net["message_posts"] == 1
        and total_tasks_after_reload == total_tasks_after_commit
        and stub.chat_calls == chat_calls_before_dag + 1
    )
    check(
        "⑥硬刷新先 GET 权威历史并清 outbox：零第二次消息 POST/模型调用/任务增长",
        no_replay_after_reload,
        (
            f"ops={reload_ops} posts={dag_net['message_posts']} "
            f"tasks={total_tasks_after_commit}->{total_tasks_after_reload} "
            f"chat={stub.chat_calls}"
        ),
    )

    # 从认证 API 读回 canonical 会话与成员任务，验证浏览器展示所依据的 node_tasks
    # 权威投影和持久化来源证据；不从 stub 计划反推“应该是这样”。
    canonical_response = dag_page.context.request.get(
        BASE + f"/api/conversations/{dag_conversation_id}"
    )
    tasks_response = dag_page.context.request.get(
        BASE + f"/api/conversations/{dag_conversation_id}/tasks"
    )
    canonical = canonical_response.json() if canonical_response.ok else {}
    dag_tasks = tasks_response.json() if tasks_response.ok else []
    canonical_message = next(
        (
            message
            for message in reversed(canonical.get("messages", []))
            if message.get("recommendation", {}).get("execution", {}).get("request_id")
            == retained_outbox["request_id"]
        ),
        None,
    )
    execution = (canonical_message or {}).get("recommendation", {}).get("execution", {})
    tasks_by_agent = {task["agent_id"]: task for task in dag_tasks}
    root_task = tasks_by_agent.get("control_logic_agent", {})
    leaf_task = tasks_by_agent.get("fta_agent", {})
    expected_node_tasks = [
        {
            "node_id": "control",
            "agent_id": "control_logic_agent",
            "task_id": root_task.get("id"),
            "initial_status": "queued",
        },
        {
            "node_id": "fta",
            "agent_id": "fta_agent",
            "task_id": leaf_task.get("id"),
            "initial_status": "created",
        },
    ]
    dag_projection_ok = (
        canonical_response.ok
        and tasks_response.ok
        and canonical_message is not None
        and execution.get("graph_version") == "guide_dag.v1"
        and execution.get("node_tasks") == expected_node_tasks
        and execution.get("task_ids") == [item["task_id"] for item in expected_node_tasks]
        and root_task.get("status") == "queued"
        and leaf_task.get("status") == "created"
        and leaf_task.get("depends_on") == [root_task.get("id")]
    )
    check(
        "⑦guide_dag.v1 两节点 node_tasks 权威投影：根 queued、唯一叶 created",
        dag_projection_ok,
        f"execution={execution} tasks={dag_tasks}",
    )

    dag_file_id = retained_outbox["payload"]["file_ids"][0]
    root_source = root_task.get("source_binding") or {}
    leaf_source = leaf_task.get("source_binding") or {}
    leaf_attachments = leaf_source.get("attachments") or []
    attachment_binding_ok = (
        root_task.get("input_file_ids") == []
        and root_source.get("attachments") == []
        and root_source.get("params", {}).get("json_pointer")
        == "/inputs_by_agent/control_logic_agent"
        and leaf_task.get("input_file_ids") == [dag_file_id]
        and leaf_source.get("params", {}).get("json_pointer") == "/inputs_by_agent/fta_agent"
        and len(leaf_attachments) == 1
        and leaf_attachments[0].get("file_id") == dag_file_id
        and leaf_attachments[0].get("conversation_id") == dag_conversation_id
        and leaf_attachments[0].get("uploaded_by_username") == "e2e_engineer"
        and leaf_attachments[0].get("kind") == "input"
        and leaf_attachments[0].get("task_id") is None
        and root_source.get("graph_digest") == execution.get("graph_digest")
        and leaf_source.get("graph_digest") == execution.get("graph_digest")
    )
    check(
        "⑦当前轮附件来源只绑定 FTA 叶节点，strict inputs_by_agent 分别留痕",
        attachment_binding_ok,
        f"root_source={root_source} leaf_source={leaf_source}",
    )

    conn = app.state.conn_factory()
    try:
        leaf_review_events = conn.execute(
            "SELECT COUNT(*) FROM task_events WHERE task_id = ? AND event_type = 'review_approved'",
            (leaf_task.get("id"),),
        ).fetchone()[0]
    finally:
        conn.close()
    dag_body = dag_page.locator("body").inner_text()
    leaf_still_human = (
        app.state.agent_registry.get("fta_agent")["workflow"]["requires_human_review"] is True
        and leaf_task.get("status") == "created"
        and leaf_review_events == 0
        and "叶节点仍需真人签发" in dag_body
    )
    check(
        "⑦唯一叶节点仍停在真人审核签发边界",
        leaf_still_human,
        f"leaf_status={leaf_task.get('status')} review_events={leaf_review_events}",
    )
    dag_page.close()

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

    # ── ⑧'' 存储不可用（隐私模式）：HttpOnly cookie 仍允许登录/读取，但
    # safe_auto 没有可回读的 sessionStorage outbox 时必须 fail-closed、零 POST。──
    priv = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    priv.add_init_script("Storage.prototype.setItem = function() { throw new Error('storage disabled'); };")
    priv.goto(BASE + "/", wait_until="networkidle")
    priv.get_by_placeholder("用户名").fill("xin_tongshi")
    priv.get_by_placeholder("密码").fill(E2E_PASSWORD)
    priv.locator(".welcome-gate__button").click()
    priv.wait_for_selector(".welcome-gate", state="detached", timeout=8000)
    priv.wait_for_selector(".hero-title", timeout=5000)
    storage_fail_text = "存储不可用时绝不能自动执行"
    conn = app.state.conn_factory()
    try:
        before_storage_fail = (
            conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0],
        )
    finally:
        conn.close()
    priv.locator(".composer textarea").fill(storage_fail_text)
    priv.get_by_role("button", name="发送").click()
    expect(priv.locator(".page-alert")).to_be_visible(timeout=8000)
    conn = app.state.conn_factory()
    try:
        after_storage_fail = (
            conn.execute("SELECT COUNT(*) FROM conversations").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM conversation_messages").fetchone()[0],
        )
    finally:
        conn.close()
    storage_fail_ok = (
        "新同事" in priv.locator("body").inner_text()
        and priv.locator(".user-bubble").count() == 0
        and priv.locator(".composer textarea").input_value() == storage_fail_text
        and priv.locator(".composer textarea").is_disabled()
        and before_storage_fail == after_storage_fail
    )
    check(
        "⑧''存储不可用：可登录读取，但发送回滚并锁 composer、零新会话消息",
        storage_fail_ok,
        (
            f"bubble={priv.locator('.user-bubble').count()} "
            f"disabled={priv.locator('.composer textarea').is_disabled()} "
            f"db={before_storage_fail}->{after_storage_fail}"
        ),
    )
    priv.close()

    # ── ⑨ 诚实前置（M11-A1）：composer Agent 选择器首屏可见 maturity 角标
    # 与首条 limitation 摘要——「L0/模拟」不许藏在两跳深的 /portal 里。──
    hon = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(hon.context, BASE)
    hon.goto(BASE + "/", wait_until="networkidle")
    hon.get_by_role("button", name="浏览可用 Agent").click()
    hon.wait_for_selector(".agent-pick .ap-item", timeout=5000)
    maturity_texts = hon.locator(".agent-pick .ap-maturity").all_inner_texts()
    limit_count = hon.locator(".agent-pick .ap-limit").count()
    item_count = hon.locator(".agent-pick .ap-item").count()
    check("⑨选择器诚实前置：每条目 maturity 角标+limitation 摘要同屏",
          item_count > 0 and len(maturity_texts) == item_count
          and all(m.startswith("L") for m in maturity_texts) and limit_count == item_count,
          f"items={item_count} maturity={maturity_texts} limits={limit_count}")
    hon.close()

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M6 GUIDE ACCEPTANCE ALL GREEN' if not failed else 'M6 GUIDE ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
