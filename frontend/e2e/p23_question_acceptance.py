"""P2.3 结构化澄清 Question/Answer 真浏览器验收。

自包含：启动真实 FastAPI + 已构建 Vue 应用，使用隔离临时 SQLite 与确定性模型
边界 stub；除模型外，Question 生成、Answer API、CAS 落库、刷新恢复和 UI 均走
生产路径。截图默认只写临时 artifact，绝不覆盖受跟踪评审证据。

覆盖：
  ① QuestionCard 紧跟 assistant Markdown，且稳定 message_id/题目锚点可恢复；
  ② 原生 radio 键盘选择不发请求，双提交只产生一个 Answer 请求；
  ③ option / 自定义文本 / free-text 三种回答均写入 canonical 用户消息并续写；
  ④ 502 保留草稿与 submission_id，重试只落一轮；
  ⑤ 409/过期后强制 GET resnapshot，卡片收为只读终态；
  ⑥ 390px、focus、暗色、reduced-motion 与 Question 信任色隔离。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/p23_question_acceptance.py
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
from urllib.parse import parse_qs, urlparse

from _artifacts import resolve_shots_dir

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = resolve_shots_dir(REPO, "p23-question-shots")

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
import backend.app.runtime.conversation as conversation_runtime


WORK = Path(tempfile.mkdtemp(prefix="flai_p23_question_"))

CHOICE_PROMPT = "这次先覆盖哪个系统？"
CUSTOM_PROMPT = "请补充更准确的分析范围。"
FREE_TEXT_PROMPT = "请写下本轮验收标准。"
EXPIRY_PROMPT = "是否继续生成下一步建议？"
CUSTOM_ANSWER = "只看应急供电支路"
FREE_TEXT_ANSWER = "故障树节点完整且可追溯"


def _question_reply(
    intro: str,
    *,
    prompt: str,
    kind: str = "single_choice",
    options: list[tuple[str, str | None]] | None = None,
) -> str:
    proposal: dict[str, Any] = {
        "kind": kind,
        "prompt": prompt,
        "description": "请补充准确事实；回答只用于继续本次对话。",
    }
    if kind == "single_choice":
        proposal["options"] = [
            {"label": label, "description": description}
            for label, description in (options or [])
        ]
    return (
        f"{intro}\n\n- 当前只收集澄清事实\n- 回答后再继续分析\n"
        "<<QUESTION>>\n"
        f"{json.dumps(proposal, ensure_ascii=False)}\n"
        "<<END_QUESTION>>"
    )


class _QuestionGateway:
    """五个确定性模型边界调用；第四次故意 502，重试走第五次。"""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.entries: list[str | Exception] = [
            _question_reply(
                "先确认系统边界。",
                prompt=CHOICE_PROMPT,
                options=[
                    ("供电系统", "主电源与应急电源"),
                    ("液压系统", "主液压与备份液压"),
                ],
            ),
            _question_reply(
                "选项回答已用于收窄边界。",
                prompt=CUSTOM_PROMPT,
                options=[
                    ("主供电链路", "只覆盖主供电"),
                    ("应急供电链路", "只覆盖应急供电"),
                ],
            ),
            _question_reply(
                "自定义范围已进入本轮上下文。",
                prompt=FREE_TEXT_PROMPT,
                kind="free_text",
            ),
            ModelUpstreamError("stub 注入的回答轮上游失败"),
            _question_reply(
                "自由文本已用于继续分析。",
                prompt=EXPIRY_PROMPT,
                options=[("继续", None), ("暂不继续", None)],
            ),
        ]

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        self.calls.append({"profile": profile, "messages": messages, **kwargs})
        index = len(self.calls) - 1
        if index >= len(self.entries):
            raise AssertionError("P2.3 验收发生了未声明的额外模型调用")
        entry = self.entries[index]
        if isinstance(entry, Exception):
            raise entry
        return {
            "content": entry,
            "token_usage": None,
            "model_name": "p23-question-stub",
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
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

gateway = _QuestionGateway()
app.state.conversation_service.model_gateway = gateway

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(
        ("PASS" if ok is True else "FAIL"),
        name,
        ("| " + detail if detail and ok is not True else ""),
    )


def card_for(page: Any, prompt: str) -> Any:
    return page.locator(".question-card").filter(has_text=prompt).first


def answer_path(url: str) -> bool:
    return re.search(
        r"/api/conversations/[^/?]+/questions/[^/?]+/answer$",
        urlparse(url).path,
    ) is not None


def stable_snapshot(context: Any, conversation_id: str) -> dict[str, Any]:
    response = context.request.get(f"{BASE}/api/conversations/{conversation_id}")
    if response.status != 200:
        raise AssertionError(
            f"会话快照读取失败：{response.status} {response.text()}"
        )
    return response.json()


def snapshot_ids_are_stable(snapshot: dict[str, Any]) -> tuple[bool, str]:
    messages = snapshot.get("messages") or []
    ids = [message.get("message_id") for message in messages]
    valid = all(
        isinstance(message_id, str)
        and re.fullmatch(r"msg_[0-9a-f]{32}", message_id) is not None
        for message_id in ids
    )
    unique = len(ids) == len(set(ids))
    anchored = all(
        not message.get("question")
        or message["question"].get("prompt_message_id") == message.get("message_id")
        for message in messages
    )
    return valid and unique and anchored, (
        f"messages={len(messages)} valid={valid} unique={unique} anchored={anchored}"
    )


def question_surface_probe(card: Any) -> dict[str, Any]:
    """Computed-style audit: Question subtree may use clay/red/amber, never green/teal."""
    return card.evaluate(
        """(root) => {
          const docStyle = getComputedStyle(document.documentElement);
          const normalize = (value) => {
            const probe = document.createElement('span');
            probe.style.color = value.trim();
            document.body.appendChild(probe);
            const resolved = getComputedStyle(probe).color;
            probe.remove();
            return resolved;
          };
          const banned = new Set([
            normalize(docStyle.getPropertyValue('--trust-real')),
            normalize(docStyle.getPropertyValue('--trust-signed')),
          ]);
          const props = [
            'color', 'backgroundColor', 'borderTopColor', 'borderRightColor',
            'borderBottomColor', 'borderLeftColor', 'outlineColor', 'accentColor',
            'caretColor', 'textDecorationColor', 'columnRuleColor',
          ];
          const hits = [];
          for (const el of [root, ...root.querySelectorAll('*')]) {
            const style = getComputedStyle(el);
            for (const prop of props) {
              const value = style[prop];
              if (banned.has(value)) hits.push(`${el.tagName}.${el.className}:${prop}=${value}`);
            }
          }
          const rootStyle = getComputedStyle(root);
          return {
            theme: document.documentElement.dataset.theme,
            hits,
            background: rootStyle.backgroundColor,
            foreground: rootStyle.color,
          };
        }"""
    )


from _auth import login_context, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "验收工程师")

real_now_iso = conversation_runtime._now_iso
with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(
        viewport={"width": 1440, "height": 900},
        color_scheme="light",
        reduced_motion="no-preference",
    )
    page = context.new_page()
    login_context(context, BASE)

    answer_requests: list[dict[str, Any]] = []
    answer_responses: list[int] = []
    review_requests: list[str] = []
    conversation_gets: list[str] = []

    def record_request(request: Any) -> None:
        path = urlparse(request.url).path
        if answer_path(request.url):
            try:
                body = json.loads(request.post_data or "{}")
            except json.JSONDecodeError:
                body = {"_invalid_json": request.post_data}
            answer_requests.append({"url": request.url, "body": body})
        if re.search(r"/api/tasks/[^/?]+/review(?:/|$)", path):
            review_requests.append(request.url)
        if re.fullmatch(r"/api/conversations/conv_[0-9a-f]{32}", path):
            conversation_gets.append(request.url)

    def record_response(response: Any) -> None:
        if answer_path(response.url):
            answer_responses.append(response.status)

    page.on("request", record_request)
    page.on("response", record_response)

    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("请帮我建立一份可追溯的故障树分析范围")
    page.get_by_role("button", name="发送").click()

    choice_card = card_for(page, CHOICE_PROMPT)
    expect(choice_card).to_be_visible(timeout=8000)
    first_ai_body = choice_card.locator("xpath=ancestor::*[contains(@class,'ai-body')][1]")
    direct_after_markdown = choice_card.evaluate(
        """(card) => card.previousElementSibling?.classList.contains('ai-lead') === true
          && card.previousElementSibling.querySelector('ul') !== null"""
    )
    check(
        "① QuestionCard 直接位于 assistant Markdown 之后",
        direct_after_markdown is True and first_ai_body.count() == 1,
    )

    query = parse_qs(urlparse(page.url).query)
    conversation_id = (query.get("c") or [""])[0]
    snapshot = stable_snapshot(context, conversation_id)
    stable_ok, stable_detail = snapshot_ids_are_stable(snapshot)
    check(
        "① 服务端稳定 message_id 唯一，Question 精确锚定 prompt message",
        bool(conversation_id) and stable_ok,
        stable_detail,
    )

    # 390px：先用键盘选中原生 radio；选择本身绝不触发 Answer 请求。
    page.set_viewport_size({"width": 390, "height": 844})
    choice_card.scroll_into_view_if_needed()
    mobile = choice_card.evaluate(
        """(card) => {
          const rect = card.getBoundingClientRect();
          const targets = [...card.querySelectorAll('.question-option, .question-submit, .question-textarea')]
            .map((el) => ({ cls: el.className, h: el.getBoundingClientRect().height }));
          return {
            docWidth: document.documentElement.scrollWidth,
            innerWidth: window.innerWidth,
            left: rect.left,
            right: rect.right,
            targets,
          };
        }"""
    )
    targets_ok = bool(mobile["targets"]) and all(
        target["h"] >= 44 for target in mobile["targets"]
    )
    check(
        "⑥ 390px 无横向溢出且交互目标高度均不小于 44px",
        mobile["docWidth"] <= mobile["innerWidth"]
        and mobile["left"] >= -0.5
        and mobile["right"] <= mobile["innerWidth"] + 0.5
        and targets_ok,
        str(mobile),
    )

    first_radio = choice_card.locator('input[value="option:option_1"]')
    # 必须用真实 Tab 建立 keyboard modality；程序化 focus 在 Chromium 中可能只
    # 命中 :focus 而不命中 :focus-visible，会把存在的 2px 焦点环测成假红。
    page.evaluate("document.activeElement?.blur()")
    keyboard_reached = False
    for _ in range(120):
        page.keyboard.press("Tab")
        if first_radio.evaluate("(el) => document.activeElement === el"):
            keyboard_reached = True
            break
    focus_probe = first_radio.evaluate(
        """(el) => {
          const label = el.closest('label');
          const style = getComputedStyle(label);
          return {
            active: document.activeElement === el,
            width: parseFloat(style.outlineWidth),
            style: style.outlineStyle,
          };
        }"""
    )
    before_radio = len(answer_requests)
    if keyboard_reached:
        page.keyboard.press("Space")
    else:
        # 让后续 Answer 流仍可给出完整失败汇总；此分支不会把 focus 红点伪绿。
        first_radio.check()
    page.wait_for_timeout(150)
    check(
        "② 原生 radio 可键盘聚焦，2px focus 可见",
        keyboard_reached is True
        and focus_probe["active"] is True
        and focus_probe["width"] >= 2
        and focus_probe["style"] != "none",
        str(focus_probe),
    )
    check(
        "② radio 选择只改本地草稿，不发送 Answer 请求",
        first_radio.is_checked() and len(answer_requests) == before_radio,
        f"before={before_radio} after={len(answer_requests)}",
    )

    light_probe = question_surface_probe(choice_card)
    check(
        "⑥ 亮色 Question surface 不借用 REAL 绿或人签 teal",
        light_probe["theme"] == "light" and light_probe["hits"] == [],
        str(light_probe),
    )
    page.screenshot(path=str(SHOTS / "1_question_light_390.png"), full_page=True)

    page.emulate_media(color_scheme="dark", reduced_motion="reduce")
    page.wait_for_function(
        "document.documentElement.dataset.theme === 'dark'", timeout=3000
    )
    dark_probe = question_surface_probe(choice_card)
    motion_probe = choice_card.evaluate(
        """(root) => [...root.querySelectorAll(
          '.question-card, .question-option, .question-textarea, .question-submit, .question-refresh'
        ), root].map((el) => {
          const s = getComputedStyle(el);
          return { transition: s.transitionDuration, animation: s.animationDuration };
        })"""
    )
    motion_off = all(
        set(item["transition"].split(", ")) <= {"0s"}
        and set(item["animation"].split(", ")) <= {"0s"}
        for item in motion_probe
    )
    check(
        "⑥ 暗色 Question 使用暖色 token 且仍不借用绿/teal",
        dark_probe["theme"] == "dark"
        and dark_probe["hits"] == []
        and dark_probe["background"] != light_probe["background"],
        str(dark_probe),
    )
    check(
        "⑥ prefers-reduced-motion 下 Question 动画与过渡归零",
        motion_off,
        str(motion_probe),
    )
    page.screenshot(path=str(SHOTS / "2_question_dark_reduced_390.png"), full_page=True)
    page.emulate_media(color_scheme="light", reduced_motion="no-preference")
    page.wait_for_function(
        "document.documentElement.dataset.theme === 'light'", timeout=3000
    )
    page.set_viewport_size({"width": 1440, "height": 900})

    # 同一事件循环内双 click：父级 busy guard 必须只发一个 POST。
    before_double = len(answer_requests)
    choice_card.locator(".question-submit").evaluate(
        "(button) => { button.click(); button.click(); }"
    )
    expect(choice_card.locator(".resolution-label")).to_have_text(
        "已回答", timeout=8000
    )
    check(
        "② 双提交只产生一个 Answer 请求",
        len(answer_requests) == before_double + 1,
        f"before={before_double} after={len(answer_requests)}",
    )
    option_request = answer_requests[-1]["body"]
    option_canonical = f"回答「{CHOICE_PROMPT}」：供电系统"
    check(
        "③ option Answer 走冻结 option_id，并追加 canonical user + assistant",
        option_request.get("payload") == {"kind": "option", "option_id": "option_1"}
        and page.locator(".user-text").filter(has_text=option_canonical).count() == 1
        and "选项回答已用于收窄边界。" in page.locator("body").inner_text(),
        str(option_request),
    )

    page.reload(wait_until="networkidle")
    choice_card = card_for(page, CHOICE_PROMPT)
    custom_card = card_for(page, CUSTOM_PROMPT)
    expect(custom_card).to_be_visible(timeout=8000)
    check(
        "③ 刷新后 option 精确恢复为已回答，不退回可编辑态",
        "供电系统" in choice_card.locator(".resolution-value").inner_text()
        and choice_card.locator(".question-form").count() == 0,
    )

    custom_card.locator('input[value="text"]').check()
    custom_card.locator("textarea").fill(CUSTOM_ANSWER)
    custom_card.locator(".question-submit").click()
    expect(custom_card.locator(".resolution-label")).to_have_text(
        "已回答", timeout=8000
    )
    custom_request = answer_requests[-1]["body"]
    custom_canonical = f"回答「{CUSTOM_PROMPT}」：{CUSTOM_ANSWER}"
    check(
        "③ 自定义 Answer 不伪装成选项，并追加唯一 canonical 消息",
        custom_request.get("payload") == {"kind": "text", "text": CUSTOM_ANSWER}
        and page.locator(".user-text").filter(has_text=custom_canonical).count() == 1,
        str(custom_request),
    )

    page.reload(wait_until="networkidle")
    custom_card = card_for(page, CUSTOM_PROMPT)
    free_card = card_for(page, FREE_TEXT_PROMPT)
    expect(free_card).to_be_visible(timeout=8000)
    check(
        "③ 刷新后自定义回答逐字恢复，下一 free-text Question 同步恢复",
        CUSTOM_ANSWER in custom_card.locator(".resolution-value").inner_text()
        and free_card.locator("textarea").count() == 1,
    )

    # 第一次 free-text 回答由 stub 注入 502：草稿与稳定 submission_id 必须保留。
    free_card.locator("textarea").fill(FREE_TEXT_ANSWER)
    failed_before_messages = len(stable_snapshot(context, conversation_id)["messages"])
    before_failure = len(answer_requests)
    free_card.locator(".question-submit").click()
    expect(free_card.locator(".question-error")).to_be_visible(timeout=8000)
    expect(free_card.locator(".question-submit")).to_be_enabled(timeout=3000)
    first_failed_body = answer_requests[-1]["body"]
    check(
        "④ 502 如实上屏并保留 free-text 草稿",
        answer_responses[-1] == 502
        and len(answer_requests) == before_failure + 1
        and free_card.locator("textarea").input_value() == FREE_TEXT_ANSWER,
        f"responses={answer_responses} body={first_failed_body}",
    )
    check(
        "④ 502 本轮零落库，不出现 canonical 幽灵消息",
        len(stable_snapshot(context, conversation_id)["messages"])
        == failed_before_messages
        and page.locator(".user-text").filter(
            has_text=f"回答「{FREE_TEXT_PROMPT}」：{FREE_TEXT_ANSWER}"
        ).count()
        == 0,
    )

    free_card.locator(".question-submit").click()
    expect(free_card.locator(".resolution-label")).to_have_text(
        "已回答", timeout=8000
    )
    retry_body = answer_requests[-1]["body"]
    free_canonical = f"回答「{FREE_TEXT_PROMPT}」：{FREE_TEXT_ANSWER}"
    check(
        "④ 502 重试沿用同一 submission_id，成功只追加一轮",
        retry_body.get("submission_id") == first_failed_body.get("submission_id")
        and retry_body.get("payload") == {
            "kind": "text",
            "text": FREE_TEXT_ANSWER,
        }
        and page.locator(".user-text").filter(has_text=free_canonical).count() == 1
        and len(gateway.calls) == 5,
        f"first={first_failed_body} retry={retry_body} calls={len(gateway.calls)}",
    )

    page.reload(wait_until="networkidle")
    exact_answers = {
        CHOICE_PROMPT: "供电系统",
        CUSTOM_PROMPT: CUSTOM_ANSWER,
        FREE_TEXT_PROMPT: FREE_TEXT_ANSWER,
    }
    restored = True
    restored_detail: list[str] = []
    for prompt, expected_answer in exact_answers.items():
        card = card_for(page, prompt)
        try:
            value = card.locator(".resolution-value").inner_text(timeout=3000)
        except Exception as exc:  # 汇总全部恢复证据，不让首个缺失遮住其它项。
            value = f"<missing: {exc}>"
        restored_detail.append(f"{prompt}={value}")
        restored = restored and expected_answer in value and card.locator(
            ".question-form"
        ).count() == 0
    expiry_card = card_for(page, EXPIRY_PROMPT)
    expect(expiry_card).to_be_visible(timeout=8000)
    snapshot = stable_snapshot(context, conversation_id)
    stable_ok, stable_detail = snapshot_ids_are_stable(snapshot)
    check(
        "③ 刷新后 option/custom/free-text 三类回答逐字恢复",
        restored,
        "; ".join(restored_detail),
    )
    check(
        "③ 全链 canonical 消息稳定 ID 唯一，刷新未重复追加",
        stable_ok
        and sum(message.get("content") == option_canonical for message in snapshot["messages"])
        == 1
        and sum(message.get("content") == custom_canonical for message in snapshot["messages"])
        == 1
        and sum(message.get("content") == free_canonical for message in snapshot["messages"])
        == 1,
        stable_detail,
    )

    # 服务端时钟前移是隔离夹具：不改 Question spec/DB；真实 Answer API 先判过期
    # 返回 409，前端随后必须 GET 最新 projection 并把卡片收成只读。
    before_expiry_messages = len(snapshot["messages"])
    before_expiry_gets = len(conversation_gets)
    before_expiry_requests = len(answer_requests)
    conversation_runtime._now_iso = lambda: "2100-01-01T00:00:00+00:00"
    expiry_card.locator('input[value="option:option_1"]').check()
    expiry_card.locator(".question-submit").click()
    expect(expiry_card.locator(".resolution-label")).to_have_text(
        "已过期", timeout=8000
    )
    expired_snapshot = stable_snapshot(context, conversation_id)
    expired_question = next(
        message["question"]
        for message in expired_snapshot["messages"]
        if message.get("question")
        and message["question"].get("prompt") == EXPIRY_PROMPT
    )
    check(
        "⑤ 409/expired 触发强制 GET resnapshot 并收为只读终态",
        answer_responses[-1] == 409
        and len(answer_requests) == before_expiry_requests + 1
        and len(conversation_gets) > before_expiry_gets
        and expired_question["status"] == "expired"
        and expiry_card.locator(".question-form").count() == 0
        and expiry_card.get_by_role("button", name="提交回答").count() == 0,
        f"responses={answer_responses} gets={len(conversation_gets) - before_expiry_gets} "
        f"status={expired_question['status']}",
    )
    check(
        "⑤ 过期冲突零模型调用、零消息副作用",
        len(gateway.calls) == 5
        and len(expired_snapshot["messages"]) == before_expiry_messages,
        f"calls={len(gateway.calls)} messages={len(expired_snapshot['messages'])}",
    )

    final_probe = question_surface_probe(expiry_card)
    check(
        "⑥ 终态 Question surface 同样不借用 REAL 绿或人签 teal",
        final_probe["hits"] == [],
        str(final_probe),
    )
    check(
        "⑥ 全套 Question 流程从未调用 task review API",
        review_requests == [],
        str(review_requests),
    )
    page.screenshot(path=str(SHOTS / "3_question_expired_terminal.png"), full_page=True)

    context.close()
    browser.close()

conversation_runtime._now_iso = real_now_iso

failed = [result for result in results if result[1] is not True]
print(
    f"\n{'P2.3 QUESTION ACCEPTANCE ALL GREEN' if not failed else 'P2.3 QUESTION ACCEPTANCE FAILED'} "
    f"({len(results) - len(failed)}/{len(results)})"
)
sys.exit(0 if not failed else 1)
