"""P2.4 exact addressing/search real-browser acceptance.

Self-contained: starts the real FastAPI app with an isolated SQLite database,
serves the built Vue application, authenticates through the production login
endpoint, and drives Chromium at 390 px with reduced motion enabled.

Coverage:
  1. exact username authority despite duplicate display names; foreign and
     legacy-NULL conversations/messages remain non-oracles;
  2. a conversation outside the old 100-row client window is server-searchable,
     and a stable message result lands on/focuses the exact ``?m=`` target;
  3. task inputs are never indexed; one delayed scope stays visibly pending
     instead of flashing a global empty state; a slow stale query cannot replace
     a newer query;
  4. a fourth authoritative output artifact lands on ``?file=``, expands and
     focuses with no preview beyond TaskDetail's existing cold-load baseline
     and no download request;
  5. stale message/file anchors produce an explicit warning, with no horizontal
     overflow on the mobile viewport.

Run from the repository root after building ``frontend/dist``::

  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with httpx --with python-multipart --with "pydantic>2" --with jieba \
    python frontend/e2e/p24_search_acceptance.py
"""
from __future__ import annotations

import asyncio
import hashlib
import re
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from _artifacts import resolve_shots_dir

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = resolve_shots_dir(REPO, "p24-search-shots")
if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn
from starlette.responses import JSONResponse

from backend.app.main import create_app
from backend.app.storage import repos


WORK = Path(tempfile.mkdtemp(prefix="flai_p24_search_"))
DB_PATH = WORK / "flai_os.db"
DISPLAY_NAME = "同名验收工程师"
ALICE = "p24_alice"
BOB = "p24_bob"
ALICE_PASSWORD = "p24-alice-pass"
BOB_PASSWORD = "p24-bob-pass"

ALICE_CONVERSATION = "conv_" + "a" * 32
BOB_CONVERSATION = "conv_" + "b" * 32
LEGACY_CONVERSATION = "conv_" + "c" * 32
MESSAGE_NEEDLE = "outside-window-message-p24"
LEGACY_NEEDLE = "legacy-null-owner-p24"
OLD_QUERY = "slow-old-result-p24"
NEW_QUERY = "fresh-new-result-p24"
DELAYED_TASK_QUERY = "scope-delay-truth-p24"
PARTIAL_FAILURE_QUERY = "partial-source-truth-p24"
INPUT_ONLY_NEEDLE = "input-only-phantom-p24"
ARTIFACT_NEEDLE = "authoritative-fourth-p24"
ARTIFACT_TASK = "task_p24_artifact_anchor"
STALE_MESSAGE = "msg_" + "f" * 32
STALE_FILE = "file_p24_stale_missing"


_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

app = create_app(
    agents_dir=REPO / "agents",
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=DB_PATH,
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)

# Test-only latency injection keeps the production response/auth/search path
# intact.  It delays, but never fabricates, a search response.
delayed_requests: list[tuple[str, str]] = []


@app.middleware("http")
async def _p24_latency_probe(request: Any, call_next: Any) -> Any:
    query = request.query_params.get("q")
    scope = request.query_params.get("scope")
    if request.url.path == "/api/search":
        if query == PARTIAL_FAILURE_QUERY and scope == "artifact":
            return JSONResponse(
                status_code=503,
                content={"detail": "search_source_unavailable"},
                headers={"Cache-Control": "no-store"},
            )
        if query == OLD_QUERY and scope == "message":
            delayed_requests.append((query, scope))
            await asyncio.sleep(1.2)
        elif query == DELAYED_TASK_QUERY and scope == "task":
            delayed_requests.append((query, scope))
            await asyncio.sleep(1.5)
    return await call_next(request)


server = uvicorn.Server(
    uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error")
)
threading.Thread(target=server.run, daemon=True).start()
for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")


from _auth import login_context, login_httpx, seed_user  # noqa: E402


seed_user(DB_PATH, DISPLAY_NAME, username=ALICE, password=ALICE_PASSWORD)
seed_user(DB_PATH, DISPLAY_NAME, username=BOB, password=BOB_PASSWORD)


def _seed_fixtures() -> dict[str, Any]:
    conn = app.state.conn_factory()
    try:
        # The target is inserted first; 101 newer Alice conversations guarantee
        # it is outside GET /api/conversations' historical default window (100).
        repos.create_conversation(
            conn,
            conversation_id=ALICE_CONVERSATION,
            agent_id="guide_agent",
            created_by=DISPLAY_NAME,
            created_by_username=ALICE,
        )
        alice_message = repos.append_message(
            conn,
            conversation_id=ALICE_CONVERSATION,
            role="user",
            content=MESSAGE_NEEDLE,
        )
        repos.append_message(
            conn,
            conversation_id=ALICE_CONVERSATION,
            role="user",
            content=OLD_QUERY,
        )
        repos.append_message(
            conn,
            conversation_id=ALICE_CONVERSATION,
            role="assistant",
            content=NEW_QUERY,
        )
        repos.append_message(
            conn,
            conversation_id=ALICE_CONVERSATION,
            role="assistant",
            content=DELAYED_TASK_QUERY,
        )
        partial_failure_message = repos.append_message(
            conn,
            conversation_id=ALICE_CONVERSATION,
            role="assistant",
            content=PARTIAL_FAILURE_QUERY,
        )
        for index in range(101):
            repos.create_conversation(
                conn,
                conversation_id=f"conv_{index + 1024:032x}",
                agent_id="guide_agent",
                created_by=DISPLAY_NAME,
                created_by_username=ALICE,
            )

        repos.create_conversation(
            conn,
            conversation_id=BOB_CONVERSATION,
            agent_id="guide_agent",
            created_by=DISPLAY_NAME,
            created_by_username=BOB,
        )
        bob_message = repos.append_message(
            conn,
            conversation_id=BOB_CONVERSATION,
            role="user",
            content=MESSAGE_NEEDLE,
        )

        legacy_created_at = "2025-01-01T00:00:00+00:00"
        conn.execute(
            """
            INSERT INTO conversations
                (id, agent_id, status, created_by, created_by_username,
                 recommendation_json, created_at, updated_at)
            VALUES (?, 'guide_agent', 'active', ?, NULL, NULL, ?, ?)
            """,
            (LEGACY_CONVERSATION, DISPLAY_NAME, legacy_created_at, legacy_created_at),
        )
        legacy_message = repos.append_message(
            conn,
            conversation_id=LEGACY_CONVERSATION,
            role="user",
            content=LEGACY_NEEDLE,
        )

        repos.create_task(
            conn,
            task_id="task_p24_input_only",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="metadata-only task",
            created_by=DISPLAY_NAME,
            created_by_username=ALICE,
            inputs={"secret_probe": INPUT_ONLY_NEEDLE},
        )
        repos.create_task(
            conn,
            task_id="task_p24_delayed_scope",
            agent_id="hello_agent",
            agent_version="0.1.0",
            name=DELAYED_TASK_QUERY,
            created_by=DISPLAY_NAME,
            created_by_username=ALICE,
        )
        repos.create_task(
            conn,
            task_id=ARTIFACT_TASK,
            agent_id="hello_agent",
            agent_version="0.1.0",
            name="P2.4 exact artifact addressing",
            created_by=DISPLAY_NAME,
            created_by_username=ALICE,
        )

        artifact_dir = WORK / "task_runs" / ARTIFACT_TASK
        artifact_dir.mkdir(parents=True, exist_ok=True)
        file_ids: list[str] = []
        for index in range(4):
            file_id = f"file_p24_output_{index + 1}"
            filename = (
                f"p24-output-{index + 1}.md"
                if index < 3
                else f"{ARTIFACT_NEEDLE}.md"
            )
            payload = f"# P2.4 output {index + 1}\n\nauthoritative fixture\n".encode()
            path = artifact_dir / filename
            path.write_bytes(payload)
            repos.create_file(
                conn,
                file_id=file_id,
                task_id=ARTIFACT_TASK,
                kind="output",
                filename=filename,
                path=str(path),
                size_bytes=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                classification="internal",
            )
            file_ids.append(file_id)
        repos.set_task_outputs(conn, ARTIFACT_TASK, file_ids)
        now = "2026-07-19T00:00:00+00:00"
        conn.execute(
            """
            UPDATE tasks
            SET status = 'completed', data_classification = 'internal',
                started_at = ?, finished_at = ?, updated_at = ?
            WHERE id = ?
            """,
            (now, now, now, ARTIFACT_TASK),
        )
        return {
            "alice_message": alice_message,
            "bob_message": bob_message,
            "legacy_message": legacy_message,
            "partial_failure_message": partial_failure_message,
            "artifact_file_id": file_ids[-1],
        }
    finally:
        conn.close()


fixtures = _seed_fixtures()
SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(
        "PASS" if ok is True else "FAIL",
        name,
        ("| " + detail if detail and ok is not True else ""),
    )


def _search_url(query: str, scope: str) -> str:
    return f"{BASE}/api/search?{urlencode({'q': query, 'scope': scope, 'limit': 6})}"


def _scope_group(page: Any, label: str) -> Any:
    label_node = page.locator(".qs-group-label > span:first-child").filter(
        has_text=re.compile(rf"^{re.escape(label)}$")
    )
    return label_node.locator("xpath=../..").first


def _open_search(page: Any) -> Any:
    if page.locator(".qs-panel").count() == 0:
        page.keyboard.press("Control+K")
    panel = page.locator(".qs-panel")
    expect(panel).to_be_visible(timeout=5000)
    field = panel.locator(".qs-input")
    expect(field).to_be_focused()
    return field


def _close_search(page: Any) -> None:
    if page.locator(".qs-panel").count():
        page.keyboard.press("Escape")
        expect(page.locator(".qs-panel")).to_have_count(0)


def _wait_for_delay(query: str, scope: str, page: Any) -> bool:
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        if (query, scope) in delayed_requests:
            return True
        page.wait_for_timeout(50)
    return False


def _wait_for_search_response(
    responses: list[tuple[str, int]], query: str, scope: str, page: Any
) -> int | None:
    deadline = time.monotonic() + 4
    while time.monotonic() < deadline:
        for url, status in responses:
            params = parse_qs(urlparse(url).query)
            if params.get("q") == [query] and params.get("scope") == [scope]:
                return status
        page.wait_for_timeout(50)
    return None


def _wait_for_file_request_count(requests: list[str], count: int, page: Any) -> bool:
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        if len(requests) >= count:
            return True
        page.wait_for_timeout(50)
    return False


def _mobile_overflow_probe(page: Any, selector: str) -> dict[str, float]:
    return page.locator(selector).evaluate(
        """(root) => {
          const rect = root.getBoundingClientRect();
          return {
            doc: document.documentElement.scrollWidth,
            viewport: window.innerWidth,
            left: rect.left,
            right: rect.right,
          };
        }"""
    )


bob_api = login_httpx(BASE, username=BOB, password=BOB_PASSWORD)
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        color_scheme="light",
        reduced_motion="reduce",
    )
    page = context.new_page()
    login_context(context, BASE, username=ALICE, password=ALICE_PASSWORD)

    file_requests: list[str] = []
    search_requests: list[str] = []
    search_responses: list[tuple[str, int]] = []

    def record_request(request: Any) -> None:
        parsed = urlparse(request.url)
        if parsed.path.startswith("/api/files/") and (
            parsed.path.endswith("/preview") or parsed.path.endswith("/download")
        ):
            file_requests.append(request.url)
        if parsed.path == "/api/search":
            search_requests.append(request.url)

    page.on("request", record_request)
    page.on(
        "response",
        lambda response: search_responses.append((response.url, response.status))
        if urlparse(response.url).path == "/api/search"
        else None,
    )

    # ── Authority: same display name never merges principals ────────────
    alice_search = context.request.get(_search_url(MESSAGE_NEEDLE, "message"))
    bob_search = bob_api.get(
        "/api/search",
        params={"q": MESSAGE_NEEDLE, "scope": "message", "limit": 6},
    )
    alice_ids = [item["id"] for item in alice_search.json()["items"]]
    bob_ids = [item["id"] for item in bob_search.json()["items"]]
    check(
        "① 同显示名用户仍按 exact username 隔离消息搜索",
        alice_search.ok
        and bob_search.status_code == 200
        and alice_ids == [fixtures["alice_message"]["message_id"]]
        and bob_ids == [fixtures["bob_message"]["message_id"]],
        f"alice={alice_ids} bob={bob_ids}",
    )

    foreign = context.request.get(
        _search_url(fixtures["bob_message"]["message_id"], "message")
    )
    legacy_content = context.request.get(_search_url(LEGACY_NEEDLE, "message"))
    legacy_exact = context.request.get(
        _search_url(fixtures["legacy_message"]["message_id"], "message")
    )
    foreign_conversation = context.request.get(
        _search_url(BOB_CONVERSATION, "conversation")
    )
    legacy_conversation = context.request.get(
        _search_url(LEGACY_CONVERSATION, "conversation")
    )
    check(
        "① foreign 与 legacy-NULL 会话/消息均为非 oracle 空页",
        foreign.ok
        and legacy_content.ok
        and legacy_exact.ok
        and foreign_conversation.ok
        and legacy_conversation.ok
        and foreign.json()["items"] == []
        and legacy_content.json()["items"] == []
        and legacy_exact.json()["items"] == []
        and foreign_conversation.json()["items"] == []
        and legacy_conversation.json()["items"] == [],
        (
            f"foreign_message={foreign.json()} legacy_message={legacy_content.json()} "
            f"foreign_conversation={foreign_conversation.json()} "
            f"legacy_conversation={legacy_conversation.json()}"
        ),
    )

    input_only = context.request.get(_search_url(INPUT_ONLY_NEEDLE, "task"))
    check(
        "② 任务 inputs 内容不进入寻址索引",
        input_only.ok and input_only.json()["items"] == [],
        str(input_only.json()),
    )

    # ── Old-window conversation and exact stable message anchor ─────────
    recent = context.request.get(BASE + "/api/conversations?limit=100")
    recent_ids = [item["id"] for item in recent.json()]
    check(
        "③ 目标会话确实在旧 100 行客户端窗口之外",
        recent.ok and len(recent_ids) == 100 and ALICE_CONVERSATION not in recent_ids,
        f"count={len(recent_ids)} target_in_window={ALICE_CONVERSATION in recent_ids}",
    )

    page.goto(BASE + "/", wait_until="networkidle")
    field = _open_search(page)
    field.fill(ALICE_CONVERSATION)
    conversation_group = _scope_group(page, "会话")
    expect(conversation_group.locator(".qs-item")).to_have_count(1, timeout=5000)
    conversation_query_scopes = {
        (parse_qs(urlparse(url).query).get("scope") or [""])[0]
        for url in search_requests
        if (parse_qs(urlparse(url).query).get("q") or [""])[0]
        == ALICE_CONVERSATION
    }
    check(
        "③ 有效查询由真实 UI 并行请求四个独立服务端 scope",
        conversation_query_scopes == {"conversation", "message", "task", "artifact"},
        str(conversation_query_scopes),
    )
    conversation_group.locator(".qs-item").click()
    page.wait_for_function(
        "id => new URL(location.href).searchParams.get('c') === id",
        arg=ALICE_CONVERSATION,
    )
    check(
        "③ 服务端会话搜索可打开旧窗口之外的 exact conversation",
        parse_qs(urlparse(page.url).query).get("c") == [ALICE_CONVERSATION],
        page.url,
    )

    field = _open_search(page)
    field.fill(MESSAGE_NEEDLE)
    message_group = _scope_group(page, "消息")
    message_result = message_group.locator(".qs-item").filter(has_text=MESSAGE_NEEDLE)
    expect(message_result).to_have_count(1, timeout=5000)
    message_result.click()
    message_id = fixtures["alice_message"]["message_id"]
    page.wait_for_function(
        "id => new URL(location.href).searchParams.get('m') === id",
        arg=message_id,
    )
    target_message = page.locator(f'[data-message-id="{message_id}"]')
    expect(target_message).to_be_visible(timeout=5000)
    page.wait_for_function(
        "id => document.activeElement?.dataset?.messageId === id", arg=message_id
    )
    check(
        "③ 消息结果落到稳定 ?m 并精确聚焦目标消息",
        target_message.evaluate("el => document.activeElement === el") is True,
        page.url,
    )

    message_mobile = _mobile_overflow_probe(page, ".guide-page")
    check(
        "③ 390px 消息深链无横向溢出",
        message_mobile["doc"] <= message_mobile["viewport"]
        and message_mobile["left"] >= -0.5
        and message_mobile["right"] <= message_mobile["viewport"] + 0.5,
        str(message_mobile),
    )

    page.goto(
        f"{BASE}/?{urlencode({'c': ALICE_CONVERSATION, 'm': STALE_MESSAGE})}",
        wait_until="domcontentloaded",
    )
    stale_message_warning = page.locator(".el-message").filter(
        has_text="消息定位失效"
    )
    expect(stale_message_warning).to_be_visible(timeout=6000)
    check(
        "④ stale message anchor 明示定位失效",
        "不在当前会话快照" in stale_message_warning.inner_text(),
    )

    # ── Generation guard: slow old response cannot overwrite newer query ─
    page.goto(BASE + "/", wait_until="networkidle")
    field = _open_search(page)
    field.fill(OLD_QUERY)
    old_started = _wait_for_delay(OLD_QUERY, "message", page)
    field.fill(NEW_QUERY)
    message_group = _scope_group(page, "消息")
    new_result = message_group.locator(".qs-item").filter(has_text=NEW_QUERY)
    expect(new_result).to_have_count(1, timeout=5000)
    old_response_status = _wait_for_search_response(
        search_responses, OLD_QUERY, "message", page
    )
    check(
        "⑤ 慢旧查询回包不能覆盖较新的搜索结果",
        old_started
        and old_response_status == 200
        and new_result.count() == 1
        and page.locator(".qs-item").filter(has_text=OLD_QUERY).count() == 0,
        (
            f"delayed={delayed_requests} old_response={old_response_status} "
            f"requests={len(search_requests)}"
        ),
    )
    _close_search(page)

    # ── Honest per-scope pending state + reduced motion + mobile ─────────
    field = _open_search(page)
    field.fill(DELAYED_TASK_QUERY)
    task_started = _wait_for_delay(DELAYED_TASK_QUERY, "task", page)
    task_group = _scope_group(page, "任务")
    pending = task_group.locator(".qs-scope-state").filter(has_text="正在查找")
    expect(pending).to_be_visible(timeout=3000)
    fast_message_result = _scope_group(page, "消息").locator(".qs-item").filter(
        has_text=DELAYED_TASK_QUERY
    )
    expect(fast_message_result).to_have_count(1, timeout=1200)
    pending_animation = task_group.locator(".qs-pending-dot").evaluate(
        "el => getComputedStyle(el).animationName"
    )
    search_mobile = _mobile_overflow_probe(page, ".qs-panel")
    check(
        "⑥ 单轴延迟保持 pending，不闪全局空态",
        task_started
        and pending.is_visible()
        and fast_message_result.count() == 1
        and page.locator(".qs-empty").count() == 0,
        (
            f"pending={task_started} fast_message={fast_message_result.count()} "
            f"global_empty={page.locator('.qs-empty').count()}"
        ),
    )
    check(
        "⑥ reduced-motion 下 pending 点不闪动，390px 面板无横溢出",
        pending_animation in ("none", "")
        and search_mobile["doc"] <= search_mobile["viewport"]
        and search_mobile["left"] >= -0.5
        and search_mobile["right"] <= search_mobile["viewport"] + 0.5,
        f"animation={pending_animation} mobile={search_mobile}",
    )
    expect(task_group.locator(".qs-item").filter(has_text=DELAYED_TASK_QUERY)).to_have_count(
        1, timeout=5000
    )
    page.screenshot(path=str(SHOTS / "1_search_mobile_reduced.png"), full_page=True)
    _close_search(page)

    # One source failure must remain distinct from an honest empty result, while
    # a successful source in the same query remains operable.
    field = _open_search(page)
    field.fill(PARTIAL_FAILURE_QUERY)
    artifact_error = _scope_group(page, "产物").locator(".qs-scope-state.is-error")
    expect(artifact_error).to_contain_text("此来源暂不可用", timeout=5000)
    artifact_error_text = artifact_error.inner_text()
    partial_message_result = _scope_group(page, "消息").locator(".qs-item").filter(
        has_text=PARTIAL_FAILURE_QUERY
    )
    expect(partial_message_result).to_have_count(1, timeout=5000)
    partial_message_result.click()
    partial_message_id = fixtures["partial_failure_message"]["message_id"]
    page.wait_for_function(
        "id => new URL(location.href).searchParams.get('m') === id",
        arg=partial_message_id,
    )
    partial_target = page.locator(f'[data-message-id="{partial_message_id}"]')
    expect(partial_target).to_be_focused(timeout=5000)
    check(
        "⑥ 单 scope 503 明示不可用，其它 scope 结果仍可打开",
        "search_source_unavailable" in artifact_error_text
        and partial_target.evaluate("el => document.activeElement === el") is True,
    )

    # ── Fourth authoritative artifact anchor ────────────────────────────
    # Establish TaskDetail's ordinary cold-load request baseline on a separate
    # page.  The user journey below then starts from / and must issue exactly
    # that baseline (not a fifth anchor preview) and never a download.
    baseline_page = context.new_page()
    baseline_file_requests: list[str] = []
    baseline_page.on(
        "request",
        lambda request: baseline_file_requests.append(request.url)
        if urlparse(request.url).path.startswith("/api/files/")
        and (
            urlparse(request.url).path.endswith("/preview")
            or urlparse(request.url).path.endswith("/download")
        )
        else None,
    )
    baseline_page.goto(f"{BASE}/tasks/{ARTIFACT_TASK}", wait_until="networkidle")
    expect(baseline_page.locator(".artifact-card")).to_have_count(3, timeout=8000)
    baseline_page.close()
    baseline_preview_count = sum("/preview" in url for url in baseline_file_requests)
    check(
        "⑦ 夹具基线是 >3 产物默认只渲染前三件",
        baseline_preview_count == 4
        and not any("/download" in url for url in baseline_file_requests),
        f"baseline_file_requests={baseline_file_requests}",
    )

    page.goto(BASE + "/", wait_until="networkidle")
    file_requests.clear()
    field = _open_search(page)
    field.fill(ARTIFACT_NEEDLE)
    artifact_group = _scope_group(page, "产物")
    artifact_result = artifact_group.locator(".qs-item").filter(has_text=ARTIFACT_NEEDLE)
    expect(artifact_result).to_have_count(1, timeout=5000)
    artifact_result.click()
    artifact_file_id = fixtures["artifact_file_id"]
    page.wait_for_function(
        "id => new URL(location.href).searchParams.get('file') === id",
        arg=artifact_file_id,
    )
    expect(page.locator(".artifact-card")).to_have_count(4, timeout=5000)
    target_artifact = page.locator(f'.artifact-card[data-file-id="{artifact_file_id}"]')
    target_toggle = target_artifact.locator(".artifact-toggle")
    expect(target_toggle).to_be_focused(timeout=5000)
    cold_requests_settled = _wait_for_file_request_count(
        file_requests, len(baseline_file_requests), page
    )
    check(
        "⑦ 第四件 authoritative output 由 ?file 自动展开并精确聚焦",
        parse_qs(urlparse(page.url).query).get("file") == [artifact_file_id]
        and target_toggle.get_attribute("aria-expanded") == "true",
        page.url,
    )
    check(
        "⑦ 冷导航只发生详情既有 preview 基线，?file 不追加 preview 且零 download",
        cold_requests_settled
        and sorted(file_requests) == sorted(baseline_file_requests)
        and not any("/download" in url for url in file_requests),
        f"baseline={baseline_file_requests} cold_navigation={file_requests}",
    )
    artifact_mobile = _mobile_overflow_probe(page, ".task-detail")
    check(
        "⑦ 390px 产物深链无横向溢出",
        artifact_mobile["doc"] <= artifact_mobile["viewport"]
        and artifact_mobile["left"] >= -0.5
        and artifact_mobile["right"] <= artifact_mobile["viewport"] + 0.5,
        str(artifact_mobile),
    )
    page.screenshot(path=str(SHOTS / "2_artifact_anchor_mobile.png"), full_page=True)

    page.goto(
        f"{BASE}/tasks/{ARTIFACT_TASK}?{urlencode({'file': STALE_FILE})}",
        wait_until="domcontentloaded",
    )
    stale_file_warning = page.locator(".el-message").filter(
        has_text="产物定位失效"
    )
    expect(stale_file_warning).to_be_visible(timeout=6000)
    check(
        "⑧ stale file anchor 明示定位失效",
        "不在当前任务的产物清单" in stale_file_warning.inner_text()
        and not any("/download" in url for url in file_requests),
    )

    browser.close()

bob_api.close()
server.should_exit = True
failed = [result for result in results if result[1] is not True]
print(
    f"\n{'P2.4 SEARCH ACCEPTANCE ALL GREEN' if not failed else 'P2.4 SEARCH ACCEPTANCE FAILED'} "
    f"({len(results) - len(failed)}/{len(results)})"
)
sys.exit(0 if not failed else 1)
