"""Issue #75 life draft traceability browser acceptance.

Self-contained and auditable: starts a disposable FastAPI/SQLite instance,
injects a deterministic model gateway that records a real model_calls receipt,
serves the production frontend build, then drives Chromium through the real
HTTP routes.  Explicitly named test seams cover otherwise hard-to-observe
failure boundaries: response loss after a real POST commit, delayed cold-read
visibility after the real storage verifier passes, and a mutated public record
after that same verifier passes.  No seam bypasses the production persistence
path.

Run from the repository root:

    cd frontend && npm run build && cd ..
    uv run --no-project --with playwright==1.61.0 --with uvicorn \
      --with fastapi --with httpx --with jsonschema --with pyyaml \
      --with python-multipart --with "pydantic>2" --with jieba \
      --with openpyxl python frontend/e2e/life_draft_traceability_acceptance.py
"""

from __future__ import annotations

import copy
import json
import re
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
if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行 cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 1.61.0 未安装")

import httpx
import uvicorn

from backend.app.main import create_app
from backend.app.storage import repos
from _auth import login_context, login_httpx, seed_user


DRAFT = {
    "title": "家常红烧肉（带皮五花肉版）",
    "trigger": "家里想吃红烧肉且有两小时",
    "desired_outcome": "一盘可复核咸淡与软硬的红烧肉",
    "inputs": ["带皮五花肉", "冰糖", "生抽与料酒"],
    "outputs": ["一盘红烧肉"],
    "steps": ["切块焯水", "炒糖色后小火炖煮", "人工尝味后收汁"],
    "evidence_requirements": ["糖色达到琥珀色", "人工尝味记录"],
    "human_decision_points": ["收汁前由做饭的人确认咸淡"],
    "limitations": ["不适用于高压锅", "不能替代食品安全判断"],
}


class _DeterministicLifeGateway:
    """Deterministic test-only gateway with an exact, persisted chat receipt."""

    def __init__(self, conn_factory) -> None:
        self.conn_factory = conn_factory

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        **kwargs: Any,
    ) -> dict[str, Any]:
        user_text = next(
            (
                str(message.get("content") or "")
                for message in reversed(messages)
                if isinstance(message, dict) and message.get("role") == "user"
            ),
            "",
        )
        marker = "案例A" if "案例A" in user_text else "案例B"
        reply = (
            f"{marker} 的经历已经整理成待审模型草稿。\n"
            "<<DRAFT>>\n"
            f"{json.dumps(DRAFT, ensure_ascii=False)}\n"
            "<<END>>\n"
            "这不是签发结论，仍需人工复核。"
        )
        on_delta = kwargs.get("on_delta")
        if callable(on_delta):
            on_delta(reply)

        conn = self.conn_factory()
        try:
            row = repos.record_model_call(
                conn,
                task_id=None,
                conversation_id=kwargs.get("conversation_id"),
                agent_id=kwargs.get("agent_id"),
                model_profile=profile,
                model_name="deterministic-life-e2e",
                status="success",
                request_summary="Issue #75 deterministic browser fixture",
                response_summary=reply[:128],
            )
        finally:
            conn.close()

        receipt_sink = kwargs.get("_receipt_sink")
        if callable(receipt_sink):
            receipt_sink(
                {
                    "model_call_id": row["id"],
                    "kind": "chat",
                    "status": "success",
                    "task_id": None,
                    "conversation_id": kwargs.get("conversation_id"),
                    "agent_id": kwargs.get("agent_id"),
                    "model_profile": profile,
                    "model_name": "deterministic-life-e2e",
                }
            )
        return {
            "content": reply,
            "token_usage": None,
            "model_name": "deterministic-life-e2e",
            "finish_reason": "stop",
        }


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = int(sock.getsockname()[1])
    sock.close()
    return port


WORK = Path(tempfile.mkdtemp(prefix="flai_issue75_life_e2e_"))
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
threading.Thread(target=server.run, daemon=True).start()

for _ in range(60):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：Issue #75 E2E 后端 6 秒内未就绪")

seed_user(WORK / "flai_os.db", "王工")
api = login_httpx(BASE)
app.state.conversation_service.model_gateway = _DeterministicLifeGateway(
    app.state.conn_factory
)


def seed_life_conversation(label: str) -> tuple[str, dict[str, Any]]:
    created = api.post(
        BASE + "/api/conversations",
        json={"agent_id": "life_guide_agent"},
    )
    assert created.status_code == 200, created.text
    conversation_id = created.json()["id"]
    posted = api.post(
        BASE + f"/api/conversations/{conversation_id}/messages",
        json={"content": f"{label}：上周末做红烧肉，收汁前由家人尝了咸淡。"},
    )
    assert posted.status_code == 200, posted.text
    return conversation_id, posted.json()["message"]


conv_a, assistant_a = seed_life_conversation("案例A")
conv_b, assistant_b = seed_life_conversation("案例B")
created_recovery = api.post(
    BASE + "/api/conversations",
    json={"agent_id": "life_guide_agent"},
)
assert created_recovery.status_code == 200, created_recovery.text
conv_recovery = created_recovery.json()["id"]
created_pending = api.post(
    BASE + "/api/conversations",
    json={"agent_id": "life_guide_agent"},
)
assert created_pending.status_code == 200, created_pending.text
conv_pending = created_pending.json()["id"]

# Test-only read controls.  The normal path still calls the real service first;
# delay proves the route epoch guard, mutation proves frontend fail-closed
# rendering without weakening backend storage verification.
original_get = app.state.conversation_service.get
delay_a = threading.Event()
mutate_b_record = threading.Event()
pending_read_lock = threading.Lock()
pending_hidden_reads = {"remaining": 0}


def controlled_get(conversation_id: str) -> dict[str, Any]:
    if conversation_id == conv_a and delay_a.is_set():
        time.sleep(0.55)
    result = original_get(conversation_id)
    if conversation_id == conv_b and mutate_b_record.is_set():
        mutated = copy.deepcopy(result)
        for message in mutated.get("messages", []):
            record = message.get("generalization_draft_record")
            if isinstance(record, dict):
                record["id"] = "workflow_claimed_id"
        return mutated
    if conversation_id == conv_pending:
        with pending_read_lock:
            hide_committed_round = pending_hidden_reads["remaining"] > 0
            if hide_committed_round:
                pending_hidden_reads["remaining"] -= 1
        if hide_committed_round:
            # Test-only eventual-visibility seam: the real cold verifier above
            # has already accepted the committed record.  Hide exactly the last
            # persisted round from two public responses so repeated refresh can
            # prove the frontend keeps its ambiguous-round lock.
            mutated = copy.deepcopy(result)
            mutated["messages"] = mutated.get("messages", [])[:-2]
            return mutated
    return result


app.state.conversation_service.get = controlled_get

results: list[tuple[str, bool, str]] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    ok = condition is True
    results.append((name, ok, detail))
    print("PASS" if ok else "FAIL", name, f"| {detail}" if detail and not ok else "")


def router_push(page, path: str) -> None:
    page.evaluate(
        """path => {
          const app = document.querySelector('#app').__vue_app__;
          return app.config.globalProperties.$router.push(path);
        }""",
        path,
    )


browser = None
try:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        page = browser.new_page(
            viewport={"width": 1280, "height": 900},
            color_scheme="light",
        )
        login_context(page.context, BASE)

        browser_create_posts: list[str] = []
        browser_message_posts: list[str] = []
        browser_conversation_gets: list[str] = []

        def observe_request(request) -> None:
            parsed = urlparse(request.url)
            if request.method == "POST" and parsed.path == "/api/conversations":
                browser_create_posts.append(request.url)
            if request.method == "POST" and parsed.path.endswith("/messages"):
                browser_message_posts.append(request.url)
            if request.method == "GET" and re.fullmatch(
                r"/api/conversations/[^/]+", parsed.path
            ):
                browser_conversation_gets.append(request.url)

        page.on("request", observe_request)

        # 0. Invalid routing inputs fail closed before any business API side
        # effect.  A syntactically valid but nonexistent c is GET-only, reports
        # the error explicitly, and reset removes the full s/c deep link.
        creates_before_invalid = len(browser_create_posts)
        gets_before_invalid = len(browser_conversation_gets)
        page.goto(
            BASE + "/demo?s=unknown&c=missing_r2_conversation",
            wait_until="networkidle",
        )
        expect(page.locator(".life-demo__error")).to_contain_text(
            "demo 场景参数不受支持"
        )
        check(
            "invalid s is explicit with zero create or conversation GET side effects",
            len(browser_create_posts) == creates_before_invalid
            and len(browser_conversation_gets) == gets_before_invalid,
            (
                f"create_delta={len(browser_create_posts) - creates_before_invalid} "
                f"get_delta={len(browser_conversation_gets) - gets_before_invalid}"
            ),
        )
        page.get_by_role("button", name="返回场景选择").click()
        expect(page).to_have_url(BASE + "/demo")
        expect(
            page.get_by_role(
                "heading", name="挑一段生活经历,走一遍建模闭环"
            )
        ).to_be_visible()
        check("invalid s can reset to the side-effect-free picker", True)

        creates_before_missing = len(browser_create_posts)
        gets_before_missing = len(browser_conversation_gets)
        page.goto(
            BASE + "/demo?s=cooking&c=missing_r2_conversation",
            wait_until="networkidle",
        )
        expect(page.locator(".life-demo__error")).to_contain_text(
            "资源不存在或不可访问"
        )
        check(
            "nonexistent c is an explicit GET-only error with zero create",
            len(browser_create_posts) == creates_before_missing
            and len(browser_conversation_gets) - gets_before_missing == 1,
            (
                f"create_delta={len(browser_create_posts) - creates_before_missing} "
                f"get_delta={len(browser_conversation_gets) - gets_before_missing}"
            ),
        )
        page.get_by_role("button", name="返回场景选择").click()
        expect(page).to_have_url(BASE + "/demo")
        expect(
            page.get_by_role(
                "heading", name="挑一段生活经历,走一遍建模闭环"
            )
        ).to_be_visible()
        check("missing c reset removes both s and c from the URL", True)

        # 1. Exact c deep links are GET-only and survive a full reload.
        direct_url = BASE + f"/demo?s=cooking&c={conv_a}"
        page.goto(direct_url, wait_until="networkidle")
        expect(page.get_by_text("案例A 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        expect(page.locator('[data-testid="life-draft-card"]')).to_have_count(1)
        check(
            "direct s+c load is GET-only",
            len(browser_create_posts) == 0,
            f"create_posts={len(browser_create_posts)}",
        )
        record_text = page.locator('[data-testid="life-draft-record-binding"]').inner_text()
        check(
            "persisted record identity and content digest are visible",
            assistant_a["generalization_draft_record"]["id"] in record_text
            and assistant_a["generalization_draft_record"]["content_digest"] in record_text,
            record_text[:240],
        )
        page.reload(wait_until="networkidle")
        expect(page.locator('[data-testid="life-draft-card"]')).to_have_count(1)
        check(
            "full reload keeps c GET-only",
            len(browser_create_posts) == 0,
            f"create_posts={len(browser_create_posts)}",
        )

        # The record-bound preview proves the payload is no longer resubmitted by
        # the card; request-body exactness is covered by the node API seam test.
        page.get_by_role("button", name="生成待审资产预览").click()
        expect(page.get_by_text("Asset Draft Bundle 摘要", exact=True)).to_be_visible()
        check("record-bound preview renders a separately labelled bundle digest", True)

        # 2. s-only creates once, canonicalizes to s+c, and reload does not create.
        page.goto(BASE + "/demo?s=travel", wait_until="networkidle")
        expect(page).to_have_url(re.compile(r"/demo\?s=travel&c=[A-Za-z0-9_-]+$"))
        check(
            "s-only route creates exactly once and router.replace writes canonical s+c",
            len(browser_create_posts) == 1,
            f"create_posts={len(browser_create_posts)} url={page.url}",
        )
        page.reload(wait_until="networkidle")
        check(
            "canonical reload does not create a duplicate conversation",
            len(browser_create_posts) == 1,
            f"create_posts={len(browser_create_posts)}",
        )

        # 3. Vue-router back/forward restores each persisted conversation.
        path_a = f"/demo?s=cooking&c={conv_a}"
        path_b = f"/demo?s=renovation&c={conv_b}"
        router_push(page, path_a)
        expect(page.get_by_text("案例A 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        router_push(page, path_b)
        expect(page.get_by_text("案例B 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        page.evaluate("history.back()")
        expect(page).to_have_url(re.compile(re.escape(path_a) + "$"))
        expect(page.get_by_text("案例A 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        page.evaluate("history.forward()")
        expect(page).to_have_url(re.compile(re.escape(path_b) + "$"))
        expect(page.get_by_text("案例B 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        check("browser back and forward restore canonical persisted histories", True)

        # 4. A delayed older GET cannot overwrite a newer route.
        delay_a.set()
        router_push(page, path_a)
        router_push(page, path_b)
        expect(page.get_by_text("案例B 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        time.sleep(0.75)
        expect(page).to_have_url(re.compile(re.escape(path_b) + "$"))
        check(
            "route epoch ignores the late response from the previous c",
            page.get_by_text(
                "案例A 的经历已经整理成待审模型草稿。", exact=False
            ).count()
            == 0,
        )
        delay_a.clear()

        # 5. Explicit deterministic mutation: bad record hides only the card.
        mutate_b_record.set()
        page.reload(wait_until="networkidle")
        expect(page.get_by_text("案例B 的经历已经整理成待审模型草稿。", exact=False)).to_be_visible()
        expect(page.locator('[data-testid="life-draft-card"]')).to_have_count(0)
        expect(page.get_by_text("草稿记录未通过契约校验", exact=False)).to_be_visible()
        check(
            "invalid record suppresses the card while persisted assistant text remains",
            True,
        )
        mutate_b_record.clear()

        # 6. The real POST commits, but its response is then dropped at the
        # browser boundary.  The page must reconcile once through GET and must
        # never issue a duplicate POST.
        commit_then_drop_statuses: list[int] = []
        recovery_path = f"/api/conversations/{conv_recovery}/messages"

        def commit_then_drop(route) -> None:
            upstream = route.fetch()
            commit_then_drop_statuses.append(upstream.status)
            route.abort("connectionreset")

        page.route(
            re.compile(re.escape(BASE + recovery_path) + "$"),
            commit_then_drop,
            times=1,
        )
        page.goto(
            BASE + f"/demo?s=cooking&c={conv_recovery}",
            wait_until="networkidle",
        )
        posts_before_recovery = len(browser_message_posts)
        recovery_text = "断线恢复案例A：上周末做红烧肉，收汁前人工尝味。"
        page.locator(".life-demo__textarea").fill(recovery_text)
        page.get_by_role("button", name="发送 ↵").click()
        expect(
            page.get_by_text("案例A 的经历已经整理成待审模型草稿。", exact=False)
        ).to_be_visible()
        expect(
            page.get_by_text("已通过会话冷读确认本轮只保存一次", exact=False)
        ).to_be_visible()
        time.sleep(0.2)
        check(
            "commit-after-response-drop recovers through one cold GET",
            commit_then_drop_statuses == [200],
            f"upstream_statuses={commit_then_drop_statuses}",
        )
        recovered_cold = api.get(
            BASE + f"/api/conversations/{conv_recovery}"
        )
        assert recovered_cold.status_code == 200, recovered_cold.text
        recovered_messages = recovered_cold.json()["messages"]
        check(
            "ambiguous POST is never blindly retried or duplicated",
            len(browser_message_posts) - posts_before_recovery == 1
            and len(recovered_messages) == 2
            and sum(
                1
                for message in recovered_messages
                if message.get("role") == "user"
                and message.get("content") == recovery_text
            )
            == 1,
            (
                f"browser_posts={len(browser_message_posts) - posts_before_recovery} "
                f"persisted_messages={len(recovered_messages)}"
            ),
        )

        # 7. Even repeated cold reads that still show the old baseline must not
        # clear the ambiguous-round lock.  Only a later exact user/assistant
        # append, including record lineage, may reopen the composer.
        pending_commit_statuses: list[int] = []
        pending_path = f"/api/conversations/{conv_pending}/messages"

        def commit_pending_then_drop(route) -> None:
            upstream = route.fetch()
            pending_commit_statuses.append(upstream.status)
            route.abort("connectionreset")

        page.route(
            re.compile(re.escape(BASE + pending_path) + "$"),
            commit_pending_then_drop,
            times=1,
        )
        page.goto(
            BASE + f"/demo?s=cooking&c={conv_pending}",
            wait_until="networkidle",
        )
        with pending_read_lock:
            pending_hidden_reads["remaining"] = 2
        pending_posts_before = len(browser_message_posts)
        pending_text = "延迟可见案例A：做完后必须由家人确认咸淡。"
        pending_textarea = page.locator(".life-demo__textarea")
        pending_textarea.fill(pending_text)
        page.get_by_role("button", name="发送 ↵").click()
        expect(page.get_by_text("无法按发送前基线完成唯一核对", exact=False)).to_be_visible()
        expect(pending_textarea).to_be_disabled()
        check(
            "first baseline-only cold read keeps ambiguous composer locked",
            pending_commit_statuses == [200]
            and len(browser_message_posts) - pending_posts_before == 1,
            (
                f"upstream_statuses={pending_commit_statuses} "
                f"browser_posts={len(browser_message_posts) - pending_posts_before}"
            ),
        )

        pending_get_path = f"/api/conversations/{conv_pending}"
        refresh_button = page.get_by_role("button", name="刷新会话核对")
        with page.expect_response(
            lambda response: urlparse(response.url).path == pending_get_path
            and response.request.method == "GET"
        ):
            refresh_button.click()
        expect(page.get_by_text("无法按发送前基线完成唯一核对", exact=False)).to_be_visible()
        expect(pending_textarea).to_be_disabled()
        check(
            "second baseline-only refresh stays locked and sends no duplicate POST",
            len(browser_message_posts) - pending_posts_before == 1,
            f"browser_posts={len(browser_message_posts) - pending_posts_before}",
        )

        with page.expect_response(
            lambda response: urlparse(response.url).path == pending_get_path
            and response.request.method == "GET"
        ):
            refresh_button.click()
        expect(
            page.get_by_text("已通过会话冷读确认本轮只保存一次", exact=False)
        ).to_be_visible()
        expect(pending_textarea).to_be_enabled()
        check(
            "exact later append clears the pending ambiguous round lock",
            len(browser_message_posts) - pending_posts_before == 1,
            f"browser_posts={len(browser_message_posts) - pending_posts_before}",
        )

        browser.close()
        browser = None
finally:
    if browser is not None:
        try:
            browser.close()
        except Exception:
            # Playwright may already have closed its event loop while unwinding
            # an assertion; cleanup must not replace the original failure.
            pass
    server.should_exit = True

failed = [name for name, ok, _ in results if not ok]
print(f"Issue #75 life draft E2E: {len(results) - len(failed)}/{len(results)} passed")
if failed:
    print("Failed:", ", ".join(failed))
    raise SystemExit(1)
