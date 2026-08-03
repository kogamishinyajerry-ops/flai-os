"""V1 发布级真实纵向产品验收：主会话 → 人签 → 资产 → 自动复用 → 地图。

这条套件刻意不拼接既有横向夹具，也不直写业务表：

* 临时 SQLite + FastAPI 静态托管真实 ``frontend/dist``；
* 浏览器走真实登录、附件上传、Guide 自动路由与原子开工；
* ``fta_agent`` 由真实 JobRunner 执行到 ``waiting_review``；
* 人工放行、Candidate 决定、隔离包字节复核与包级批准都从 UI 发起；
* 第二个真实会话由生产 SkillReuseMatcher 自动附加已批准包；
* 最后展开生产 FeatureAssetMapDisclosure，捕获真实 owner-scoped GET 响应。

仅模型上游使用确定性 stub：会话 stub 只给编排建议，runtime stub 只给 FTA
草案文本；任务状态、事件、候选、物化、字节核验、匹配和地图均为生产代码。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python \
    frontend/e2e/v1_vertical_release_acceptance.py
"""

from __future__ import annotations

import hashlib
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
if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行 cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_v1_vertical_"))
SHOTS = WORK / "shots"
SHOTS.mkdir(parents=True, exist_ok=True)

TASK_TITLE = "起落架控制逻辑核对"
REQUEST_TEXT = (
    "请完成起落架控制逻辑核对：分析双通道供电完全丧失的故障树，"
    "并保留来源、草案和人工签发证据，工况见附件。"
)
FTA_INPUTS = {
    "top_event": "双通道供电完全丧失",
    "system_description": "起落架控制系统由双通道电源、控制器与作动链路组成。",
    "components": ["电源通道A", "电源通道B", "控制器", "作动链路"],
}


class _ConversationStub:
    """只替代模型生成的编排建议；生产边界会重校验 Agent、输入和 Skill 引用。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, "kwargs": kwargs})
        prompt_text = "\n".join(
            str(message.get("content") or "")
            for message in messages
            if isinstance(message, dict)
        )
        has_current_attachment = REQUEST_TEXT in prompt_text
        agent_plan: dict[str, Any] = {
            "agent_id": "fta_agent",
            "role": "形成故障树分析草案",
            "rationale": (
                "输入已从主会话与附件自动整理齐备。"
                if has_current_attachment
                else "输入已从本轮主会话自动整理齐备。"
            ),
            "prefilled_inputs": FTA_INPUTS,
        }
        # 已审核 Skill 方法本身可能引用历史附件标签，不能把方法文本里的
        # “附件1”误当成本轮 roster。测试首轮请求明确带附件，第二轮不带；
        # 这里据本轮用户原文决定模型计划是否声明 attachment partition，随后
        # 仍由生产 Guide 用真实 file_id roster 复核。
        if has_current_attachment:
            agent_plan["attachments"] = ["附件1"]
        plan = {
            "decision": "orchestrate",
            "analysis": "这项工作需要形成 FTA 草案并由工程师复核。",
            "goal": TASK_TITLE,
            "workflow": "故障树分析 Agent 形成草案，工程师核对后签发。",
            "agents": [agent_plan],
        }
        if has_current_attachment:
            plan["ignored_attachments"] = []
        source_label = "文字与附件" if has_current_attachment else "本轮文字"
        reply = (
            f"系统已根据{source_label}整理执行方案；开工仍由工程师确认。\n"
            f"<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
        )
        return {
            "content": reply,
            "token_usage": None,
            "model_name": "v1-conversation-stub",
            "finish_reason": "stop",
        }


class _RuntimeStub:
    """只替代 fta_agent 的推理模型，真实 workflow 仍写带水印的 FTA 草案。"""

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {
            "content": (
                "顶事件可由双通道电源共同失效、控制器失效或作动链路中断触发。"
                "请逐项核对共同原因失效、独立性假设与逻辑门关系。"
            ),
            "token_usage": None,
            "model_name": "v1-runtime-stub",
            "finish_reason": "stop",
        }


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
server = uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
)
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except httpx.HTTPError:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

conversation_stub = _ConversationStub()
app.state.conversation_service.model_gateway = conversation_stub
app.state.runtime.model_gateway = _RuntimeStub()

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

from _auth import E2E_PASSWORD, E2E_USERNAME, login_context, login_httpx, seed_user

seed_user(WORK / "flai_os.db", "V1验收工程师")
OTHER_USERNAME = "v1_other_engineer"
seed_user(
    WORK / "flai_os.db",
    "另一位V1工程师",
    username=OTHER_USERNAME,
    password=E2E_PASSWORD,
)
API = login_httpx(BASE)
OTHER_API = login_httpx(
    BASE,
    username=OTHER_USERNAME,
    password=E2E_PASSWORD,
)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def latest_conversation_id(client: httpx.Client = API) -> str:
    payload = client.get("/api/conversations?limit=5").json()
    items = payload if isinstance(payload, list) else payload.get("items", [])
    if not items:
        raise AssertionError("真实 API 未返回当前账号会话")
    return items[0]["id"]


def conversation_tasks(
    conversation_id: str,
    client: httpx.Client = API,
) -> list[dict[str, Any]]:
    payload = client.get(f"/api/conversations/{conversation_id}/tasks").json()
    return payload if isinstance(payload, list) else payload.get("items", [])


def wait_task(task_id: str, status: str, timeout_s: float = 45.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        response = API.get(f"/api/tasks/{task_id}")
        if response.status_code == 200:
            last = response.json()
            if last.get("status") == status:
                return last
        time.sleep(0.35)
    return last


attachment = WORK / "起落架控制逻辑核对工况.txt"
attachment.write_text(
    "双通道电源经控制器驱动作动链路；顶事件为双通道供电完全丧失。",
    encoding="utf-8",
)

with sync_playwright() as playwright:
    browser = playwright.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        color_scheme="light",
    )
    login_context(context, BASE)
    page = context.new_page()

    # Slice 1：真实登录 → 主会话附件/自动路由 → 人确认开工 → JobRunner 待签。
    page.goto(BASE + "/", wait_until="networkidle")
    check(
        "①真实登录进入生产主会话（非 UI Lab）",
        page.url.rstrip("/") == BASE and page.locator(".guide-page").count() == 1,
        page.url,
    )
    page.locator('.composer input[type="file"]').set_input_files(str(attachment))
    expect(page.locator(".composer")).to_contain_text(attachment.name)
    page.locator(".composer textarea").fill(REQUEST_TEXT)
    page.get_by_role("button", name="发送").click()
    plan_card = page.locator(".plan-card").last
    expect(plan_card).to_be_visible(timeout=12_000)
    conversation_id = latest_conversation_id()
    first_conversation_response = API.get(f"/api/conversations/{conversation_id}")
    first_conversation = (
        first_conversation_response.json()
        if first_conversation_response.status_code == 200
        else {}
    )
    first_user_messages = [
        message
        for message in first_conversation.get("messages", [])
        if message.get("role") == "user"
    ]
    bound_file_ids = (
        first_user_messages[-1].get("file_ids", []) if first_user_messages else []
    )
    bound_file_id = bound_file_ids[0] if len(bound_file_ids) == 1 else None
    first_user_content = (
        first_user_messages[-1].get("content") if first_user_messages else None
    )
    check(
        "②附件进入真实会话且系统自动路由为单一 FTA 执行单元",
        first_conversation_response.status_code == 200
        and f"c={conversation_id}" in page.url
        and attachment.name in page.locator(".bubble-row.user").last.inner_text()
        and first_user_content == REQUEST_TEXT
        and bool(bound_file_id)
        and "已自动编排 · 1 个执行单元" in plan_card.locator(".route-summary").inner_text(),
        page.url,
    )
    start_button = plan_card.get_by_role("button", name="按方案开工", exact=True)
    expect(start_button).to_be_visible(timeout=8_000)
    check(
        "③开工前任务为零且唯一主动作由人触发",
        conversation_tasks(conversation_id) == []
        and plan_card.locator(".plan-foot .cta-clay").count() == 1,
    )
    start_button.click()

    deadline = time.time() + 10
    tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        tasks = conversation_tasks(conversation_id)
        if len(tasks) == 1:
            break
        time.sleep(0.25)
    task = tasks[0] if len(tasks) == 1 else {}
    task_id = str(task.get("id") or "")
    waiting = wait_task(task_id, "waiting_review") if task_id else {}
    check(
        "④同一真实 task_id 由 JobRunner 跑到 waiting_review",
        re.fullmatch(r"task_[0-9a-f]{32}", task_id) is not None
        and task.get("conversation_id") == conversation_id
        and task.get("agent_id") == "fta_agent"
        and waiting.get("id") == task_id
        and waiting.get("status") == "waiting_review"
        and waiting.get("input_file_ids") == [bound_file_id],
        json.dumps(waiting, ensure_ascii=False)[:360],
    )
    page.goto(BASE + f"/tasks/{task_id}", wait_until="networkidle")
    expect(page.locator(".review-card")).to_be_visible(timeout=12_000)
    page.screenshot(path=str(SHOTS / "1_waiting_review.png"), full_page=True)

    # Slice 2：UI 具名人签 → completed → Candidate 接受 → 精确包字节复核并批准。
    review_card = page.locator(".review-card")
    check(
        "⑤待签卡显示当前登录工程师且没有代填签发身份",
        "V1验收工程师" in review_card.inner_text()
        and review_card.locator("input").count() == 0,
        review_card.inner_text()[:260],
    )
    review_comment = "已核对草案水印、输入边界与逻辑门，批准放行。"
    review_card.locator("textarea").fill(review_comment)
    review_card.get_by_role("button", name="批准放行", exact=True).click()
    page.get_by_role("button", name="确定", exact=True).click()
    expect(page.locator(".el-message-box")).to_be_hidden(timeout=8_000)
    completed = wait_task(task_id, "completed", timeout_s=20)
    expect(page.locator("body")).to_contain_text("已完成", timeout=12_000)
    task_events_response = API.get(f"/api/tasks/{task_id}/events?limit=2000&offset=0")
    task_events = (
        task_events_response.json()
        if task_events_response.status_code == 200
        else []
    )
    review_events = [
        event for event in task_events
        if event.get("event_type") == "review_approved"
    ]
    check(
        "⑥UI 具名签发后仍是同一 task_id，completed 与 review_approved 同时闭合",
        completed.get("id") == task_id
        and completed.get("status") == "completed"
        and len(review_events) == 1
        and review_events[0].get("payload", {}).get("reviewer_username") == E2E_USERNAME
        and review_events[0].get("payload", {}).get("comment") == review_comment,
        json.dumps(review_events, ensure_ascii=False)[:360],
    )
    page.screenshot(path=str(SHOTS / "2_human_signed_completed.png"), full_page=True)

    page.goto(BASE + f"/?c={conversation_id}", wait_until="networkidle")
    candidate_callout = page.locator(".asset-candidate-callout")
    expect(candidate_callout).to_be_visible(timeout=20_000)
    expect(candidate_callout).to_contain_text("这次任务里，有一套方法值得你看一眼")
    candidate_response = API.get(f"/api/tasks/{task_id}/asset-candidate")
    candidate = candidate_response.json() if candidate_response.status_code == 200 else {}
    check(
        "⑦完成证据自动形成 Candidate，来源仍钉住同一 task_id",
        candidate_response.status_code == 200
        and candidate.get("source", {}).get("task_id") == task_id
        and candidate.get("source", {}).get("conversation_id") == conversation_id
        and candidate.get("state") == "awaiting_human_review",
        candidate_response.text[:360],
    )

    candidate_callout.get_by_role("button", name="查看并决定", exact=True).click()
    drawer = page.locator(".asset-candidate-review")
    expect(drawer).to_be_visible(timeout=8_000)
    drawer.get_by_role("button", name="查看来源与摘要证据", exact=True).click()
    expect(drawer).to_contain_text(task_id)
    drawer.get_by_role("button", name="接受这个候选", exact=True).click()
    expect(drawer.locator(".candidate-package")).to_contain_text(
        "隔离包待复核", timeout=12_000
    )

    accepted_response = API.get(f"/api/tasks/{task_id}/asset-candidate")
    accepted_candidate = (
        accepted_response.json() if accepted_response.status_code == 200 else {}
    )
    package = accepted_candidate.get("skill_package") or {}
    package_id = str(package.get("id") or "")
    candidate_decision = accepted_candidate.get("decision") or {}
    first_method_step = accepted_candidate["bundle"]["skill"]["instructions"][0]
    check(
        "⑧人接受 Candidate 后确定性物化隔离包，来源 task_id 未断链",
        accepted_candidate.get("state") == "accepted"
        and package.get("state") == "pending_review"
        and package.get("reuse_eligible") is False
        and package.get("source", {}).get("task_id") == task_id
        and candidate_decision.get("decided_by_username") == E2E_USERNAME
        and candidate_decision.get("signer_source") == "authenticated_session"
        and candidate_decision.get("signer_session_bound") is True
        and re.fullmatch(r"skill_package_[0-9a-f]{24}", package_id) is not None,
        json.dumps(package, ensure_ascii=False)[:400],
    )

    package_approve_button = drawer.get_by_role(
        "button", name="批准复用", exact=True
    )
    check(
        "⑨a 未读取真实包内容前，UI 禁止包级批准",
        package_approve_button.is_disabled(),
    )
    with page.expect_response(
        lambda response: (
            response.request.method == "GET"
            and response.url.endswith(f"/api/skill-packages/{package_id}/review-content")
        ),
        timeout=12_000,
    ) as review_content_info:
        drawer.get_by_role(
            "button", name="读取并审阅真实包内容", exact=True
        ).click()
    review_content_response = review_content_info.value
    review_content = review_content_response.json()
    package_files_ui = drawer.locator(".candidate-package-files")
    expect(package_files_ui).to_be_visible(timeout=8_000)

    package_root = app.state.candidate_skill_packages_dir / package["storage_relpath"]
    manifest_by_path = {item["path"]: item for item in package.get("files", [])}
    byte_witnesses: list[bool] = []
    ui_witnesses: list[bool] = []
    review_files = review_content.get("files", [])
    ui_articles = package_files_ui.locator(".candidate-package-file")
    for index, file_projection in enumerate(review_files):
        path = file_projection.get("path")
        manifest = manifest_by_path.get(path, {})
        disk_bytes = (package_root / str(path)).read_bytes()
        byte_witnesses.append(
            file_projection.get("text", "").encode("utf-8") == disk_bytes
            and hashlib.sha256(disk_bytes).hexdigest() == manifest.get("sha256")
            and len(disk_bytes) == manifest.get("size_bytes")
        )
        article = ui_articles.nth(index)
        ui_witnesses.append(
            article.locator("h4").text_content() == path
            and article.locator("pre").text_content() == file_projection.get("text")
        )
    package_digest = str(package.get("package_digest") or "")
    package_digest_hex = package_digest.removeprefix("sha256:")
    package_digest_ui = (
        f"{package_digest[:15]}…{package_digest[-8:]}"
        if len(package_digest) >= 24
        else ""
    )
    check(
        "⑨UI 逐文件展示真实路径/正文/包摘要，并与冷读字节及磁盘清单交叉核对",
        review_content_response.status == 200
        and review_content.get("package_id") == package_id
        and review_content.get("package_digest") == package.get("package_digest")
        and package_digest == f"sha256:{package_digest_hex}"
        and re.fullmatch(r"[0-9a-f]{64}", package_digest_hex) is not None
        and len(byte_witnesses) == 4
        and all(byte_witnesses)
        and ui_articles.count() == 4
        and len(ui_witnesses) == 4
        and all(ui_witnesses)
        and "隔离包摘要" in drawer.inner_text()
        and package_digest_ui in drawer.inner_text()
        and package_approve_button.is_enabled(),
        json.dumps(review_content, ensure_ascii=False)[:300],
    )
    page.screenshot(path=str(SHOTS / "3_package_bytes_reviewed.png"), full_page=True)

    package_approve_button.click()
    expect(drawer.locator(".candidate-package")).to_contain_text(
        "工程师已批准复用", timeout=12_000
    )
    approved_response = API.get(f"/api/skill-packages/{package_id}")
    approved_package = approved_response.json() if approved_response.status_code == 200 else {}
    check(
        "⑩包级批准绑定登录会话且只把精确版本标为 reuse_eligible",
        approved_package.get("state") == "approved"
        and approved_package.get("reuse_eligible") is True
        and approved_package.get("source", {}).get("task_id") == task_id
        and approved_package.get("review", {}).get("reviewed_by_username") == E2E_USERNAME
        and approved_package.get("isolation")
        == {"zone": "candidate_quarantine", "registered": False, "executable": False},
        json.dumps(approved_package, ensure_ascii=False)[:420],
    )
    page.screenshot(path=str(SHOTS / "4_package_approved.png"), full_page=True)

    # Slice 3a：换成第二个真实账号，生产地图不得泄露首账号资产；随后切回
    # 主账号继续同一纵向链，避免“当前库只有一个 owner 所以看似 owner-scoped”
    # 的平凡绿。
    drawer.get_by_role("button", name="回到对话", exact=True).click()
    expect(drawer).to_be_hidden(timeout=8_000)
    login_context(
        context,
        BASE,
        username=OTHER_USERNAME,
        password=E2E_PASSWORD,
    )
    page.goto(BASE + "/", wait_until="networkidle")
    other_request = "请整理起落架控制逻辑核对的工作步骤，但暂不启动任何任务。"
    page.locator(".composer textarea").fill(other_request)
    page.get_by_role("button", name="发送").click()
    other_plan = page.locator(".plan-card").last
    expect(other_plan).to_be_visible(timeout=12_000)
    expect(other_plan.locator(".skill-reuse-inline")).to_have_count(0)
    other_conversation_id = latest_conversation_id(OTHER_API)
    other_conversation_response = OTHER_API.get(
        f"/api/conversations/{other_conversation_id}"
    )
    other_conversation = (
        other_conversation_response.json()
        if other_conversation_response.status_code == 200
        else {}
    )
    other_reuse_ref = (other_conversation.get("recommendation") or {}).get(
        "skill_reuse"
    )
    other_system_prompt = conversation_stub.calls[-1]["messages"][0]["content"]
    other_map_disclosure = page.locator(".feature-asset-map")
    expect(other_map_disclosure).to_be_visible(timeout=8_000)
    with page.expect_response(
        lambda response: (
            response.request.method == "GET"
            and response.url.endswith("/api/feature-asset-map")
        ),
        timeout=12_000,
    ) as other_map_response_info:
        other_map_disclosure.locator("summary").click()
    other_map_response = other_map_response_info.value
    other_map_document = other_map_response.json()
    other_map_text = other_map_response.text()
    expect(other_map_disclosure.locator(".asset-empty")).to_be_visible(timeout=8_000)
    check(
        "⑪第二真实账号的生产地图 owner 隔离：零资产且不泄露首账号摘要",
        other_map_response.status == 200
        and other_conversation_response.status_code == 200
        and conversation_tasks(other_conversation_id, OTHER_API) == []
        and not other_reuse_ref
        and first_method_step not in other_system_prompt
        and package_id not in other_system_prompt
        and package_digest not in other_system_prompt
        and other_map_document.get("source", {}).get("owner_username")
        == OTHER_USERNAME
        and other_map_document.get("source", {}).get("owner_scoped") is True
        and other_map_document.get("summary", {}).get("asset_candidate_count") == 0
        and other_map_document.get("assets") == []
        and accepted_candidate.get("id") not in other_map_text
        and accepted_candidate.get("candidate_digest") not in other_map_text
        and TASK_TITLE not in other_map_text
        and TASK_TITLE not in other_map_disclosure.locator(".asset-empty").inner_text(),
        json.dumps(other_map_document, ensure_ascii=False)[:420],
    )
    page.screenshot(path=str(SHOTS / "5_other_owner_empty_map.png"), full_page=True)

    login_context(context, BASE)

    # Slice 3b：主账号新会话生产匹配器自动复用 → 按需展开 owner 地图。
    map_requests: list[str] = []

    def record_map_request(request: Any) -> None:
        if (
            request.method == "GET"
            and request.url.endswith("/api/feature-asset-map")
        ):
            map_requests.append(request.url)

    page.on("request", record_map_request)
    page.goto(BASE + "/", wait_until="networkidle")
    second_request = "请再次完成起落架控制逻辑核对，并沿用上次方法。"
    page.locator(".composer textarea").fill(second_request)
    page.get_by_role("button", name="发送").click()
    second_plan = page.locator(".plan-card").last
    expect(second_plan).to_be_visible(timeout=12_000)
    second_conversation_id = latest_conversation_id()
    second_conversation_response = API.get(
        f"/api/conversations/{second_conversation_id}"
    )
    second_conversation = (
        second_conversation_response.json()
        if second_conversation_response.status_code == 200
        else {}
    )
    second_recommendation = second_conversation.get("recommendation") or {}
    reuse_ref = second_recommendation.get("skill_reuse") or {}
    injected_system_prompt = conversation_stub.calls[-1]["messages"][0]["content"]
    expect(second_plan.locator(".skill-reuse-inline")).to_contain_text(
        accepted_candidate["bundle"]["skill"]["name"], timeout=8_000
    )
    check(
        "⑫切回主账号后，新会话由生产匹配器唯一命中已批准包并注入真实方法",
        second_conversation_id != conversation_id
        and reuse_ref.get("package_id") == package_id
        and reuse_ref.get("package_digest") == approved_package.get("package_digest")
        and reuse_ref.get("candidate_digest") == accepted_candidate.get("candidate_digest")
        and reuse_ref.get("matched_agent_id") == "fta_agent"
        and reuse_ref.get("review_state") == "approved"
        and "已审核可复用 Skill 方法" in injected_system_prompt
        and TASK_TITLE in injected_system_prompt
        and first_method_step in injected_system_prompt,
        json.dumps(reuse_ref, ensure_ascii=False)[:420],
    )
    check(
        "⑬地图保持主会话内按需冷读：展开前无请求且流程未跳转 /map",
        map_requests == []
        and f"c={second_conversation_id}" in page.url
        and "/map" not in page.url,
        f"url={page.url} requests={map_requests}",
    )
    page.screenshot(path=str(SHOTS / "5_new_conversation_auto_reuse.png"), full_page=True)

    map_disclosure = page.locator(".feature-asset-map")
    expect(map_disclosure).to_be_visible(timeout=8_000)
    with page.expect_response(
        lambda response: (
            response.request.method == "GET"
            and response.url.endswith("/api/feature-asset-map")
        ),
        timeout=12_000,
    ) as map_response_info:
        map_disclosure.locator("summary").click()
    map_response = map_response_info.value
    map_document = map_response.json()
    expect(map_disclosure.locator(".map-metrics")).to_be_visible(timeout=8_000)
    map_assets = map_document.get("assets") or []
    mapped_asset = map_assets[0] if len(map_assets) == 1 else {}
    check(
        "⑭生产 FeatureAssetMapDisclosure 从真实 owner-scoped GET 回读同一 task_id 资产",
        map_response.status == 200
        and map_requests == [f"{BASE}/api/feature-asset-map"]
        and map_document.get("source")
        == {
            "kind": "owner_scoped_cold_projection",
            "owner_username": E2E_USERNAME,
            "owner_scoped": True,
            "read_only": True,
        }
        and map_document.get("summary", {}).get("asset_candidate_count") == 1
        and map_document.get("summary", {}).get("approved_skill_package_count") == 1
        and mapped_asset.get("candidate_id") == accepted_candidate.get("id")
        and mapped_asset.get("source", {}).get("task_id") == task_id
        and mapped_asset.get("skill_package", {}).get("id") == package_id
        and mapped_asset.get("skill_package", {}).get("state") == "approved"
        and mapped_asset.get("skill_package", {}).get("reuse_eligible") is True
        and map_document.get("effects")
        == {
            "writes_database": False,
            "executes_work": False,
            "registers_asset": False,
            "promotes_asset": False,
        },
        json.dumps(map_document, ensure_ascii=False)[:500],
    )
    asset_card = map_disclosure.locator(".asset-card")
    check(
        "⑮主会话地图 UI 如实显示一个已批准 Skill 包，Workflow/Agent 仍未形成",
        asset_card.count() == 1
        and TASK_TITLE in asset_card.inner_text()
        and "包级人审通过" in map_disclosure.inner_text()
        and "Workflow 未形成" in asset_card.inner_text()
        and "Agent 未形成" in asset_card.inner_text(),
        map_disclosure.inner_text()[-500:],
    )
    page.screenshot(path=str(SHOTS / "6_feature_asset_map_owner_asset.png"), full_page=True)

    browser.close()

failed = [result for result in results if result[1] is not True]
print(f"\n{'V1 VERTICAL RELEASE ALL GREEN' if not failed else 'V1 VERTICAL RELEASE FAILED'} ({len(results) - len(failed)}/{len(results)})")
print(f"SCREENSHOTS={SHOTS}")
sys.exit(0 if not failed else 1)
