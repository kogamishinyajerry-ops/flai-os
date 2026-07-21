"""Agent 事实投影浏览器验收。

本套件使用临时 SQLite、真实 FastAPI/静态前端、真实登录 cookie 与真实浏览器
请求。JerryAgent 事实只在后端生产 reader seam 注入确定性快照；浏览器网络没有
route/mock，FLAi 的任务、依赖、接力和人签事实仍全部来自真实仓储投影。

覆盖：
  A1 单焦点会话主轴只有一张 72px 摘要，键盘激活后进入既有具名右栏；
  A2 依赖等待、接力、人签、失败、Jerry 结构化 wait 与匿名 subagent 可见；
  A3 普通非关注任务默认折叠，等待人工/失败默认展开；
  A4 关闭右栏不改变服务端任务；
  A5 390px 右栏全宽、无横向溢出、关闭按钮至少 44px；
  A6 reduced-motion 下工作 glyph 静止；
  A7 completed 保持中性，人签使用 teal，不借 REAL 绿；
  A8 亮色桌面、暗色桌面与移动端截图写入隔离 artifact 目录。

运行（仓根，先构建）：
  cd frontend && npm run build
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with httpx --with jsonschema --with pyyaml --with python-multipart \
    --with "pydantic>2" --with jieba --with openpyxl \
    python frontend/e2e/agent_fact_projection_acceptance.py

人工驻留审计必须显式追加 ``--hold-open``；全量门禁不会读取驻留环境变量，
避免继承 shell 状态后永久挂起。
"""
from __future__ import annotations

import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

from _artifacts import resolve_shots_dir

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = resolve_shots_dir(REPO, "agent-fact-projection-shots")
WORK = Path(tempfile.mkdtemp(prefix="flai_agent_facts_e2e_"))

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行 cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app
from backend.app.storage import repos

from _auth import E2E_USERNAME, login_context, login_httpx, seed_user  # noqa: E402


CONVERSATION_ID = "conv_" + "a" * 32
MOTION_CONVERSATION_ID = "conv_" + "b" * 32
MOTION_TASK_ID = "facts-motion-working"
SIGNED_TASK_ID = "facts-signed-upstream"
RELAY_TASK_ID = "facts-relay"
REVIEW_TASK_ID = "facts-awaiting-signoff"
DEPENDENCY_TASK_ID = "facts-waiting-dependency"
FAILED_TASK_ID = "facts-failed"
JERRY_TASK_ID = "facts-jerry-running"
COMPLETED_TASK_ID = "facts-completed-neutral"
RESTORE_TASK_ID = "facts-route-restore-failed"


class _FixtureFactsReader:
    """Deterministic implementation of the production ``read`` seam.

    The projection boundary still requires an intact FLAi-side Jerry binding
    witness before this reader is called.  This fixture deliberately does not
    replace or intercept the browser's ``/agent-facts`` request.
    """

    enabled = True

    def __init__(self, *, created_at: str, updated_at: str) -> None:
        self.calls: list[tuple[str, dict[str, Any] | None]] = []
        self.created_at = created_at.replace("+00:00", "Z")
        self.updated_at = updated_at.replace("+00:00", "Z")

    def close(self) -> None:
        return None

    def read(
        self,
        execution_id: str,
        *,
        expected_binding: dict[str, Any] | None = None,
        timeout_s: float | None = None,
    ) -> dict[str, Any]:
        del timeout_s
        if execution_id != JERRY_TASK_ID or expected_binding is None:
            raise RuntimeError("unexpected fixture read")
        self.calls.append((execution_id, dict(expected_binding)))
        return {
            "sourceEpoch": "c" * 64,
            "revision": 9,
            "status": "running",
            "wait": {
                "kind": "subagent_completion",
                "since": self.updated_at,
                "subjectOrdinal": 1,
                "pendingCount": 1,
                "continueWhen": "subagents_terminal",
            },
            "delegationHold": None,
            "subagentCount": 2,
            "subagentsTruncated": False,
            "subagents": [
                {
                    "ordinal": 1,
                    "status": "running",
                    "retryOfOrdinal": None,
                    "createdAt": self.created_at,
                    "updatedAt": self.updated_at,
                },
                {
                    "ordinal": 2,
                    "status": "completed",
                    "retryOfOrdinal": None,
                    "createdAt": self.created_at,
                    "updatedAt": self.updated_at,
                },
            ],
        }


def _free_port() -> int:
    sock = socket.socket()
    try:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


PORT = _free_port()
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
server = uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
)
thread = threading.Thread(target=server.run, daemon=True)
thread.start()

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")


def _agent(agent_id: str) -> dict[str, Any]:
    value = app.state.agent_registry.get(agent_id)
    if value is None:
        raise RuntimeError(f"验收 Agent 不存在：{agent_id}")
    return value


def _create_task(
    conn: Any,
    task_id: str,
    agent_id: str,
    *,
    depends_on: list[str] | None = None,
    retry_of: str | None = None,
    conversation_id: str = CONVERSATION_ID,
) -> None:
    agent = _agent(agent_id)
    execution = agent.get("execution") or {}
    repos.create_task(
        conn,
        task_id=task_id,
        agent_id=agent_id,
        agent_version=agent["version"],
        name=task_id,
        created_by="事实验收工程师",
        created_by_username=E2E_USERNAME,
        inputs={"name": "Agent 事实验收"},
        conversation_id=conversation_id,
        depends_on=depends_on,
        retry_of=retry_of,
        review_requested_from_username=E2E_USERNAME,
        execution_adapter=execution.get("adapter", "native_python"),
        execution_contract_version=execution.get(
            "contract_version", "native.workflow.v1"
        ),
    )


def _drive(conn: Any, task_id: str, *states: str) -> None:
    for state in states:
        repos.set_task_status(conn, task_id, state)


def _append_jerry_binding(conn: Any) -> None:
    digest = "a" * 64
    identity = {
        "product": "JerryAgent",
        "schema": "flai.agent-layer.v1",
        "runtimeEventSchemaVersion": 1,
        "instanceId": "facts-instance",
        "sessionId": "facts-session",
        "runtimeKind": "external",
    }
    events = [
        (
            "agent layer started",
            {
                "workflow_event_type": "agent_layer_started",
                "adapter": "jerryagent_sidecar",
                "contract_version": "flai.agent-layer.v1",
                "execution_id": JERRY_TASK_ID,
                "request_sha256": digest,
                "runtime_instance_id": identity["instanceId"],
                "runtime_session_id": identity["sessionId"],
                "model_calls_attested_by_flai": False,
            },
        ),
        (
            "agent layer submitted",
            {
                "workflow_event_type": "agent_layer_submitted",
                "execution_id": JERRY_TASK_ID,
                "runtime_task_id": "facts-runtime-task",
                "replayed": False,
                "receipt_recovered": False,
                "submission_attempts": 1,
            },
        ),
        (
            "agent layer identity bound",
            {
                "workflow_event_type": "agent_layer_identity_bound",
                "execution_id": JERRY_TASK_ID,
                "runtime_task_id": "facts-runtime-task",
                "request_sha256": digest,
                "runtime_identity": identity,
            },
        ),
    ]
    for message, payload in events:
        repos.append_event(
            conn,
            task_id=JERRY_TASK_ID,
            agent_id="jerryagent_research_agent",
            event_type="agent_log",
            level="info",
            message=message,
            payload=payload,
        )


def _seed_facts() -> _FixtureFactsReader:
    seed_user(WORK / "flai_os.db", "事实验收工程师")
    conn = app.state.conn_factory()
    try:
        repos.create_conversation(
            conn,
            conversation_id=CONVERSATION_ID,
            agent_id="guide_agent",
            created_by="事实验收工程师",
            created_by_username=E2E_USERNAME,
        )
        repos.append_message(
            conn,
            conversation_id=CONVERSATION_ID,
            role="user",
            content="组织一次可审计的多 Agent 排故。",
        )
        plan = {
            "decision": "orchestrate",
            "analysis": "以最少打扰投影真实依赖、接力和签发状态。",
            "goal": "Agent 事实投影验收",
            "workflow": "研究 Agent 运行，确定性 Agent 接力，工程师负责最终签发。",
            "agents": [
                {
                    "agent_id": "jerryagent_research_agent",
                    "agent_name": _agent("jerryagent_research_agent")["name"],
                    "category": "research",
                    "status": "active",
                    "maturity": "L0",
                    "role": "并行研究",
                    "rationale": "投影结构化等待与匿名子智能体。",
                    "prefilled_inputs": {},
                    "stripped_fields": [],
                },
                {
                    "agent_id": "fta_agent",
                    "agent_name": _agent("fta_agent")["name"],
                    "category": "safety",
                    "status": "active",
                    "maturity": "L2",
                    "role": "人工签收",
                    "rationale": "候选结论必须由具名工程师签发。",
                    "prefilled_inputs": {},
                    "stripped_fields": [],
                },
                {
                    "agent_id": "hello_agent",
                    "agent_name": _agent("hello_agent")["name"],
                    "category": "utility",
                    "status": "active",
                    "maturity": "L1",
                    "role": "确定性接力",
                    "rationale": "展示依赖与接力见证。",
                    "prefilled_inputs": {"name": "事实验收"},
                    "stripped_fields": [],
                },
            ],
            "dropped_agents": [],
            "capped": False,
        }
        repos.append_message(
            conn,
            conversation_id=CONVERSATION_ID,
            role="assistant",
            content="已形成可审计协作方案。",
            recommendation=plan,
        )
        repos.set_conversation_recommendation(conn, CONVERSATION_ID, plan)

        motion_plan = {
            "decision": "orchestrate",
            "analysis": "用真实运行任务验证低焦虑状态提示。",
            "goal": "Agent 运行提示验收",
            "workflow": "单任务运行，不混入等待或失败优先级。",
            "agents": [
                {
                    "agent_id": "hello_agent",
                    "agent_name": _agent("hello_agent")["name"],
                    "category": "utility",
                    "status": "active",
                    "maturity": "L1",
                    "role": "运行提示",
                    "rationale": "验证真实 working 快照与 reduced-motion。",
                    "prefilled_inputs": {"name": "运行提示验收"},
                    "stripped_fields": [],
                }
            ],
            "dropped_agents": [],
            "capped": False,
        }
        repos.create_conversation(
            conn,
            conversation_id=MOTION_CONVERSATION_ID,
            agent_id="guide_agent",
            created_by="事实验收工程师",
            created_by_username=E2E_USERNAME,
        )
        repos.append_message(
            conn,
            conversation_id=MOTION_CONVERSATION_ID,
            role="user",
            content="验证真实运行提示。",
        )
        repos.append_message(
            conn,
            conversation_id=MOTION_CONVERSATION_ID,
            role="assistant",
            content="已形成单任务运行方案。",
            recommendation=motion_plan,
        )
        repos.set_conversation_recommendation(
            conn, MOTION_CONVERSATION_ID, motion_plan
        )
        _create_task(
            conn,
            MOTION_TASK_ID,
            "hello_agent",
            conversation_id=MOTION_CONVERSATION_ID,
        )
        _drive(conn, MOTION_TASK_ID, "queued", "validating", "running")

        _create_task(conn, SIGNED_TASK_ID, "fta_agent")
        _drive(
            conn,
            SIGNED_TASK_ID,
            "queued",
            "validating",
            "running",
            "analyzing",
            "waiting_review",
        )
        repos.apply_human_review(
            conn,
            SIGNED_TASK_ID,
            action="approve",
            reviewer="王工",
            reviewer_username=E2E_USERNAME,
            reason_code=None,
            comment="同意进入下游接力。",
        )

        _create_task(conn, RELAY_TASK_ID, "hello_agent", depends_on=[SIGNED_TASK_ID])
        repos.enqueue_dependent_task(
            conn,
            RELAY_TASK_ID,
            [],
            event={
                "agent_id": "hello_agent",
                "event_type": "agent_log",
                "level": "info",
                "message": "dependency resolved",
                "payload": {
                    "workflow_event_type": "dependency_resolved",
                    "upstream_task_ids": [SIGNED_TASK_ID],
                },
            },
        )

        _create_task(conn, REVIEW_TASK_ID, "fta_agent")
        _drive(
            conn,
            REVIEW_TASK_ID,
            "queued",
            "validating",
            "running",
            "analyzing",
            "waiting_review",
        )
        _create_task(
            conn,
            DEPENDENCY_TASK_ID,
            "hello_agent",
            depends_on=[REVIEW_TASK_ID],
        )

        _create_task(
            conn,
            JERRY_TASK_ID,
            "jerryagent_research_agent",
            depends_on=[SIGNED_TASK_ID],
            retry_of=SIGNED_TASK_ID,
        )
        _drive(conn, JERRY_TASK_ID, "queued", "validating", "running")
        _append_jerry_binding(conn)
        jerry_task = repos.get_task(conn, JERRY_TASK_ID)
        if jerry_task is None:
            raise RuntimeError("Jerry fixture task disappeared")

        _create_task(conn, COMPLETED_TASK_ID, "hello_agent")
        _drive(
            conn,
            COMPLETED_TASK_ID,
            "queued",
            "validating",
            "running",
            "analyzing",
            "completed",
        )
    finally:
        conn.close()

    current_reader = app.state.jerryagent_facts_reader
    current_reader.close()
    fixture = _FixtureFactsReader(
        created_at=str(jerry_task["created_at"]),
        updated_at=str(jerry_task["updated_at"]),
    )
    app.state.jerryagent_facts_reader = fixture
    return fixture


def _seed_failed_fact() -> None:
    """Introduce the failure only after real working-motion checks finish."""

    conn = app.state.conn_factory()
    try:
        if repos.get_task(conn, FAILED_TASK_ID) is None:
            _create_task(conn, FAILED_TASK_ID, "hello_agent")
            _drive(conn, FAILED_TASK_ID, "queued", "validating", "failed")
    finally:
        conn.close()


def _seed_route_restore_fact() -> None:
    """Change authoritative server facts only while the conversation is absent."""

    conn = app.state.conn_factory()
    try:
        if repos.get_task(conn, RESTORE_TASK_ID) is None:
            _create_task(conn, RESTORE_TASK_ID, "hello_agent")
            _drive(conn, RESTORE_TASK_ID, "queued", "validating", "failed")
    finally:
        conn.close()


reader = _seed_facts()
API = login_httpx(BASE)
SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    marker = "PASS" if ok is True else "FAIL"
    print(marker, name, ("| " + detail if detail and ok is not True else ""))


def _task_witness(task_id: str) -> dict[str, Any]:
    task = API.get(f"/api/tasks/{task_id}").json()
    return {"id": task["id"], "status": task["status"], "updated_at": task["updated_at"]}


_CONTRAST_SCRIPT = r"""() => {
  const selectors = [
    '.agent-monitor-head-copy > span',
    '.agent-monitor-persistence',
    '.agent-monitor-group h3',
    '.agent-monitor-duration',
    '.agent-monitor-facts > summary',
  ];
  const rgba = (value) => {
    const parts = String(value).match(/[\d.]+/g)?.map(Number) || [];
    return {r: parts[0] || 0, g: parts[1] || 0, b: parts[2] || 0,
      a: parts.length > 3 ? parts[3] : 1};
  };
  const channel = (value) => {
    const scaled = value / 255;
    return scaled <= 0.04045 ? scaled / 12.92 : ((scaled + 0.055) / 1.055) ** 2.4;
  };
  const luminance = (color) => 0.2126 * channel(color.r)
    + 0.7152 * channel(color.g) + 0.0722 * channel(color.b);
  const contrast = (a, b) => {
    const high = Math.max(luminance(a), luminance(b));
    const low = Math.min(luminance(a), luminance(b));
    return (high + 0.05) / (low + 0.05);
  };
  const solidBackground = (element) => {
    let current = element;
    while (current) {
      const color = rgba(getComputedStyle(current).backgroundColor);
      if (color.a >= 0.95) return color;
      current = current.parentElement;
    }
    return rgba(getComputedStyle(document.documentElement).backgroundColor);
  };
  return selectors.map((selector) => {
    const element = [...document.querySelectorAll(selector)]
      .find((candidate) => candidate.getClientRects().length > 0);
    if (!element) return {selector, missing: true, ratio: 0};
    const foreground = rgba(getComputedStyle(element).color);
    const background = solidBackground(element);
    return {selector, ratio: contrast(foreground, background), foreground, background};
  });
}"""


if "--hold-open" in sys.argv:
    print(f"--hold-open BASE={BASE}")
    print(f"CONVERSATION_ID={CONVERSATION_ID}")
    print(f"OPEN={BASE}/?c={CONVERSATION_ID}")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        API.close()
        server.should_exit = True
        thread.join(timeout=5)
    raise SystemExit(0)


try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()

        desktop = browser.new_context(viewport={"width": 1440, "height": 900})
        login_context(desktop, BASE)
        page = desktop.new_page()
        agent_fact_requests: list[str] = []
        page.on(
            "request",
            lambda request: agent_fact_requests.append(request.url)
            if "/api/conversations/" in request.url and "/agent-facts" in request.url
            else None,
        )
        page.goto(BASE + f"/?c={MOTION_CONVERSATION_ID}", wait_until="networkidle")

        summary = page.locator(".agent-fact-summary")
        expect(summary).to_be_visible(timeout=12_000)
        check("A1a 主轴只有一张 Agent 事实摘要", summary.count() == 1)
        box = summary.bounding_box() or {}
        check("A1b 摘要保持紧凑单焦点高度", 72 <= float(box.get("height", 0)) <= 96, str(box))
        expect(summary).to_contain_text("个任务")
        summary_classes = summary.get_attribute("class") or ""
        check("A6a 真实 working 摘要自然启用运行提示", "is-working" in summary_classes)
        motion_control = summary.locator(".agent-fact-glyph").evaluate(
            "el => getComputedStyle(el).animationName"
        )
        check(
            "A6b 普通动效下真实工作 glyph 低频呼吸",
            motion_control.startswith("agent-fact-breathe"),
            motion_control,
        )

        # reduced-motion 也使用后端真实 working 快照，不手工篡改 DOM class。
        mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            reduced_motion="reduce",
        )
        login_context(mobile, BASE)
        mobile_page = mobile.new_page()
        mobile_page.goto(BASE + f"/?c={MOTION_CONVERSATION_ID}", wait_until="networkidle")
        mobile_summary = mobile_page.locator(".agent-fact-summary")
        expect(mobile_summary).to_be_visible(timeout=12_000)
        mobile_classes = mobile_summary.get_attribute("class") or ""
        check("A6c reduced-motion 样本仍由真实 working 事实驱动", "is-working" in mobile_classes)
        motion = mobile_summary.locator(".agent-fact-glyph").evaluate(
            """el => ({
              animation: getComputedStyle(el).animationName,
              transition: getComputedStyle(el).transitionDuration,
            })"""
        )
        check(
            "A6d reduced-motion 下 glyph 静止",
            motion["animation"] == "none" and set(motion["transition"].split(", ")) <= {"0s"},
            str(motion),
        )
        mobile_summary.click()
        mobile_drawer = mobile_page.get_by_role("dialog", name="Agent 运行监控")
        expect(mobile_drawer).to_be_visible(timeout=8_000)
        metrics = mobile_page.evaluate(
            """() => {
              const drawer = document.querySelector('[role="dialog"][aria-labelledby="status-center-drawer-title"]');
              const close = document.querySelector('.sc-close');
              const d = drawer?.getBoundingClientRect();
              const c = close?.getBoundingClientRect();
              return {
                drawer: d && {x: d.x, width: d.width, right: d.right},
                close: c && {width: c.width, height: c.height},
                innerWidth: window.innerWidth,
                scrollWidth: document.documentElement.scrollWidth,
              };
            }"""
        )
        drawer_box = metrics["drawer"] or {}
        close_box = metrics["close"] or {}
        check(
            "A5a 390px 下右栏全宽",
            abs(float(drawer_box.get("x", -1))) < 1
            and abs(float(drawer_box.get("width", 0)) - 390) < 1
            and abs(float(drawer_box.get("right", 0)) - 390) < 1,
            str(metrics),
        )
        check("A5b 390px 下无横向溢出", metrics["scrollWidth"] <= metrics["innerWidth"], str(metrics))
        check(
            "A5c 移动端关闭目标至少 44px",
            float(close_box.get("width", 0)) >= 44 and float(close_box.get("height", 0)) >= 44,
            str(metrics),
        )
        mobile_page.screenshot(path=str(SHOTS / "03-mobile-390-reduced-motion.png"))
        mobile.close()

        # 真实工作动效验证完成后再引入失败事实，确保 failure-priority 与默认展开
        # 也在同一浏览器批次内被门禁，而不靠 DOM class 注入制造假绿。
        _seed_failed_fact()
        page.goto(BASE + f"/?c={CONVERSATION_ID}", wait_until="networkidle")
        summary = page.locator(".agent-fact-summary")
        expect(summary).to_be_visible(timeout=12_000)
        expect(summary).to_contain_text("1 个任务失败")

        before_close = _task_witness(JERRY_TASK_ID)
        baseline_request_base = sum(
            f"/api/conversations/{CONVERSATION_ID}/agent-facts" in url
            for url in agent_fact_requests
        )
        page.wait_for_timeout(6200)
        baseline_request_delta = sum(
            f"/api/conversations/{CONVERSATION_ID}/agent-facts" in url
            for url in agent_fact_requests
        ) - baseline_request_base
        monitor_request_base = baseline_request_base + baseline_request_delta
        # 摘要是单焦点主轴的原生 button；桌面首条路径故意用键盘进入，
        # 把 focus/Enter 语义纳入真实浏览器门禁。移动端路径仍覆盖指针点击。
        summary.press("Enter")
        drawer = page.get_by_role("dialog", name="Agent 运行监控")
        expect(drawer).to_be_visible(timeout=8_000)
        check("A1c 进入既有具名右栏", drawer.count() == 1)
        expect(drawer.get_by_text("关闭监控栏不会停止服务端任务")).to_be_visible()
        page.wait_for_timeout(6200)
        monitor_request_delta = sum(
            f"/api/conversations/{CONVERSATION_ID}/agent-facts" in url
            for url in agent_fact_requests
        ) - monitor_request_base
        check(
            "A4c 监控栏复用单一 conversation poller",
            baseline_request_delta == 1 and monitor_request_delta == baseline_request_delta,
            f"baseline={baseline_request_delta}, while-open={monitor_request_delta}",
        )

        monitor_text = page.locator(".agent-monitor").text_content() or ""
        for fact_name, needle in (
            ("A2a 依赖等待", "等待接力"),
            ("A2b 接力", "接力 1"),
            ("A2c 人签", "等待 e2e_engineer 签收"),
            ("A2d Jerry 结构化等待", "等待子智能体完成"),
            ("A2e 匿名子智能体", "子智能体 2"),
        ):
            check(fact_name, needle in monitor_text, monitor_text[:500])
        check("A2f reader seam 在完整 FLAi 绑定后被调用", len(reader.calls) > 0)
        check(
            "A2g 员工界面隐藏运行时品牌与内部任务标识",
            "JerryAgent" not in monitor_text and "facts-runtime-task" not in monitor_text,
            monitor_text[:500],
        )

        # 人话 agent 名不含 task id；按 task 序对应的可见事实内容定位更稳。
        ordinary_facts = page.locator(".agent-monitor-task").filter(
            has_text="子智能体 2"
        ).locator("details.agent-monitor-facts")
        review_facts = page.locator(".agent-monitor-task").filter(
            has_text="等待 e2e_engineer 签收"
        ).locator("details.agent-monitor-facts")
        failed_facts = page.locator(".agent-monitor-task.tone-failure details.agent-monitor-facts")
        check(
            "A3a 非关注 Jerry 事实默认折叠",
            ordinary_facts.count() == 1 and ordinary_facts.first.get_attribute("open") is None,
        )
        check(
            "A3b 等待人工事实默认展开",
            review_facts.count() == 1 and review_facts.first.get_attribute("open") is not None,
        )
        check(
            "A3c 失败事实默认展开",
            failed_facts.count() >= 1 and failed_facts.first.get_attribute("open") is not None,
        )
        ordinary_facts.first.locator(":scope > summary").click()
        expect(ordinary_facts.first.get_by_text("等待子智能体完成")).to_be_visible()
        expect(ordinary_facts.first.get_by_text("继续条件：子智能体全部落定后继续")).to_be_visible()
        expect(ordinary_facts.first.get_by_text("#1", exact=True)).to_be_visible()
        check("A3d 展开后 exact Jerry wait 与匿名序号可见", True)

        runtime_task = page.locator(".agent-monitor-task").filter(
            has_text="研究复利候选 Agent"
        )
        check("A3e 运行层任务在人话名称下唯一可定位", runtime_task.count() == 1)
        runtime_task.locator(".agent-monitor-task-head").press("Enter")
        monitor_back = page.get_by_role("button", name="返回 Agent 运行监控")
        expect(monitor_back).to_be_visible(timeout=8_000)
        # peek 会把同一 dialog 的 accessible name 切成任务人话标题；读取稳定
        # shell，而不是继续用旧的 monitor accessible-name locator。
        peek_text = page.locator(".sc-shell").text_content() or ""
        check(
            "A2h task peek 同样隐藏运行时品牌与内部标识",
            all(
                secret.lower() not in peek_text.lower()
                for secret in (
                    "JerryAgent",
                    "jerryagent_research_agent",
                    JERRY_TASK_ID,
                    SIGNED_TASK_ID,
                    "facts-runtime-task",
                    "facts-instance",
                    "facts-session",
                )
            ),
            peek_text[:500],
        )
        detail_page = desktop.new_page()
        detail_page.goto(BASE + f"/tasks/{JERRY_TASK_ID}", wait_until="networkidle")
        expect(detail_page.locator(".task-detail")).to_be_visible(timeout=8_000)
        detail_text = detail_page.locator(".task-detail").text_content() or ""
        check(
            "A2i 普通完整页隐藏 runtime 品牌与内部 handle",
            all(
                secret.lower() not in detail_text.lower()
                for secret in (
                    "JerryAgent",
                    "jerryagent_research_agent",
                    JERRY_TASK_ID,
                    SIGNED_TASK_ID,
                    "facts-runtime-task",
                    "facts-instance",
                    "facts-session",
                )
            ),
            detail_text[:500],
        )
        check(
            "A2k 血缘只显示可理解名称且仍可辨认重跑与接力关系",
            "重跑自 上次失败任务" in detail_text
            and "故障树分析辅助 Agent（FTA 草案生成）" in detail_text,
            detail_text[:500],
        )
        detail_page.close()
        monitor_back.press("Enter")
        focus_target = page.locator('[data-agent-fact-focus-target="true"]')
        expect(focus_target).to_be_focused(timeout=8_000)
        check("A3f task peek 返回后精确恢复任务焦点", focus_target.count() == 1)

        light_contrast = page.evaluate(_CONTRAST_SCRIPT)
        check(
            "A8a 亮色普通小字达到 WCAG AA",
            all(not item.get("missing") and item["ratio"] >= 4.5 for item in light_contrast),
            str(light_contrast),
        )
        page.screenshot(path=str(SHOTS / "01-light-desktop.png"))
        page.evaluate("document.documentElement.setAttribute('data-theme', 'dark')")
        page.wait_for_timeout(250)
        dark_contrast = page.evaluate(_CONTRAST_SCRIPT)
        check(
            "A8b 暗色普通小字达到 WCAG AA",
            all(not item.get("missing") and item["ratio"] >= 4.5 for item in dark_contrast),
            str(dark_contrast),
        )
        page.screenshot(path=str(SHOTS / "02-dark-desktop.png"))

        completed = page.locator(".agent-monitor-completed")
        expect(completed).to_be_visible()
        completed.locator(":scope > summary").click()
        trust_check = page.evaluate(
            """() => {
              const root = getComputedStyle(document.documentElement);
              const probes = Object.fromEntries([
                ['real', '--trust-real'],
                ['signed', '--trust-signed'],
                ['pending', '--trust-pending'],
                ['fail', '--trust-fail'],
                ['clay', '--clay'],
              ].map(([key, token]) => {
                const probe = document.createElement('span');
                probe.style.color = `var(${token})`;
                document.body.append(probe);
                return [key, probe];
              }));
              const semantic = Object.fromEntries(Object.entries(probes)
                .map(([key, probe]) => [key, getComputedStyle(probe).color]));
              Object.values(probes).forEach(probe => probe.remove());
              const rows = [...document.querySelectorAll('.agent-monitor-completed-row')];
              const signedRows = rows.filter(row => row.classList.contains('tone-signed'));
              const neutralRows = rows.filter(row => row.classList.contains('tone-neutral'));
              const samples = rows.flatMap(row => {
                const style = getComputedStyle(row);
                return [style.color, style.backgroundColor, style.borderTopColor,
                  style.borderRightColor, style.borderBottomColor, style.borderLeftColor];
              });
              const neutralSamples = neutralRows.flatMap(row => {
                const style = getComputedStyle(row);
                return [style.color, style.backgroundColor, style.borderTopColor,
                  style.borderRightColor, style.borderBottomColor, style.borderLeftColor];
              });
              return {
                ...semantic,
                samples,
                hasRealClass: rows.some(row => row.classList.contains('tone-real') ||
                  row.querySelector('.tone-real, .el-tag--success')),
                signedRowCount: signedRows.length,
                signedBorders: signedRows.map(row => getComputedStyle(row).borderLeftColor),
                neutralRowCount: neutralRows.length,
                neutralSamples,
              };
            }"""
        )
        check(
            "A7 completed 未借 REAL 绿",
            trust_check["hasRealClass"] is False
            and trust_check["real"] not in trust_check["samples"],
            str(trust_check),
        )
        check(
            "A7b 具名批准以 teal 边轨承载独立人签语义",
            trust_check["signedRowCount"] >= 1
            and trust_check["signed"] in trust_check["signedBorders"],
            str(trust_check),
        )
        check(
            "A7c 普通 completed 保持中性且不借任一信任语义色",
            trust_check["neutralRowCount"] >= 1
            and all(
                trust_check[token] not in trust_check["neutralSamples"]
                for token in ("real", "signed", "pending", "fail", "clay")
            ),
            str(trust_check),
        )

        page.get_by_role("button", name="关闭").press("Enter")
        expect(drawer).to_be_hidden(timeout=8_000)
        after_close = _task_witness(JERRY_TASK_ID)
        check("A4 关闭右栏不改变服务端任务", after_close == before_close, str(after_close))
        focus_return = page.evaluate(
            """() => ({
              tag: document.activeElement?.tagName || null,
              label: document.activeElement?.getAttribute('aria-label') || null,
            })"""
        )
        check(
            "A4b 键盘关闭后焦点回到单焦点摘要",
            focus_return == {"tag": "BUTTON", "label": "1 个任务失败，展开 Agent 监控"},
            str(focus_return),
        )

        page.locator(".status-dock").click()
        inbox = page.get_by_role("dialog", name="状态中心")
        expect(inbox).to_be_visible(timeout=8_000)
        expect(inbox.locator(".sc-item-name").first).to_be_visible(timeout=8_000)
        inbox_text = inbox.text_content() or ""
        check(
            "A2j 状态中心收件箱隐藏内部 task handle",
            all(
                secret.lower() not in inbox_text.lower()
                for secret in (
                    JERRY_TASK_ID,
                    REVIEW_TASK_ID,
                    FAILED_TASK_ID,
                    "jerryagent_research_agent",
                )
            ),
            inbox_text[:500],
        )
        inbox.get_by_role("button", name="关闭").click()
        expect(inbox).to_be_hidden(timeout=8_000)

        page.goto(BASE + "/today", wait_until="networkidle")
        restore_request_base = sum(
            f"/api/conversations/{CONVERSATION_ID}/agent-facts" in url
            for url in agent_fact_requests
        )
        _seed_route_restore_fact()
        page.goto(BASE + f"/?c={CONVERSATION_ID}", wait_until="networkidle")
        restored_summary = page.locator(".agent-fact-summary")
        expect(restored_summary).to_be_visible(timeout=12_000)
        expect(restored_summary).to_contain_text("2 个任务失败")
        restore_request_delta = sum(
            f"/api/conversations/{CONVERSATION_ID}/agent-facts" in url
            for url in agent_fact_requests
        ) - restore_request_base
        check(
            "A4d 路由离开后的服务端变化由新 Agent 快照恢复",
            restore_request_delta >= 1,
            f"agent-facts requests on return={restore_request_delta}",
        )
        restored_summary.press("Enter")
        restored_drawer = page.get_by_role("dialog", name="Agent 运行监控")
        expect(restored_drawer).to_be_visible(timeout=8_000)
        restored_monitor_text = page.locator(".agent-monitor").text_content() or ""
        restored_failure_count = page.locator(
            ".agent-monitor-task.tone-failure"
        ).count()
        check(
            "A4e 恢复的完整监控同时保留依赖、等待、接力、人签与子智能体事实",
            restored_failure_count >= 2
            and all(
                needle in restored_monitor_text
                for needle in (
                    "等待接力",
                    "接力 1",
                    "等待 e2e_engineer 签收",
                    "等待子智能体完成",
                    "子智能体 2",
                )
            ),
            restored_monitor_text[:500],
        )
        restored_drawer.get_by_role("button", name="关闭").click()
        expect(restored_drawer).to_be_hidden(timeout=8_000)
        desktop.close()
        browser.close()
finally:
    API.close()
    server.should_exit = True
    thread.join(timeout=5)

failed = [item for item in results if item[1] is not True]
print(f"Agent fact projection acceptance: {len(results) - len(failed)}/{len(results)} passed")
print(f"Screenshots: {SHOTS}")
if failed:
    for name, _, detail in failed:
        print(f"  - {name}: {detail}")
    raise SystemExit(1)
