"""M6 导引 Agent 全链 UI 走查（可重跑评审证据，ADR-0012）。

自包含：脚本自起后端（tmp db，绝不碰真实 data/）+ 注入 **stub gateway**（本机无
内网 key，真实对话不可跑；stub 返回一条确定的推荐，验证 UI 全链）+ 真 chromium。

覆盖导引全链：
  ① 导引页可达（统一入口）→ ② 发一句需求 → ③ 导引返回推荐卡片（Agent 名 +
  类型色标 + 成熟度 + 预填草案 JSON + 被剔除非法字段的告警）→ ④ 点「确认草案，
  去创建任务」→ ⑤ 落到创建任务页且**预填已带入 + 具名提交仍由人完成**（红线：
  导引不代签）。

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
    fta_agent——top_event 合法预填 + 带分工 role，外加一个非法字段 bogus 让确定性
    校验剥离（展示 stripped 告警）。

    fail_next=True 时下一次 chat 抛 ModelUpstreamError（→ API 502「本轮零落库」），
    用于验收失败轮的 UI 契约：乐观 user 气泡回滚 + 草稿还原，重试不堆重复气泡
    （Codex R1-P2）。"""

    def __init__(self) -> None:
        self.fail_next = False

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        if self.fail_next:
            self.fail_next = False
            raise ModelUpstreamError("stub 注入的上游失败（验收失败轮 UI 回滚）")
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
                    "prefilled_inputs": {"top_event": "供电完全丧失", "bogus": "该字段不属于该 Agent"},
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


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移

    # ① 导引页 = 统一入口（首页）
    page.goto(BASE + "/", wait_until="networkidle")
    body = page.locator("body").inner_text()
    # 2b 契约重立：「智能导引」原命中侧栏导航项，双 Surface 后导航收敛为
    # 「对话/任务台」——改锚 hero 主标题（导引页身份的稳定语义锚）。
    check("①导引页可达且为统一入口", "说说你要做的工程活儿" in body and "导引不会替你创建" in body, body[:200])
    page.screenshot(path=str(SHOTS / "1_guide_empty.png"), full_page=True)

    # ② 失败轮 UI 契约（Codex R1-P2 / M7 扩附件）：后端失败零落库，前端同样
    #    回滚乐观气泡并还原草稿；附件 chips 留在待发区（已上传项重试不重传）。
    REQUEST_TEXT = "我要对双通道供电系统做故障树分析，顶事件是供电完全丧失，工况见附件"
    ATTACH_NAME = "工况数据.txt"
    attach_path = WORK / ATTACH_NAME
    attach_path.write_text("双通道供电，顶事件：供电完全丧失；工况共 3 组。", encoding="utf-8")
    page.get_by_placeholder("你的名字（对话需具名）").fill("王工")
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
    check("③'导引不代签'红线文案在卡片可见", "签发权" in body and "亲手提交" in body, "")
    page.screenshot(path=str(SHOTS / "2_recommendation.png"), full_page=True)

    # ④ 点「去创建此任务」→ 落创建任务页
    page.get_by_role("button", name="去创建此任务").click()
    page.wait_for_url(lambda url: "/tasks/new" in url, timeout=5000)
    expect(page.locator(".prefill-note")).to_be_visible(timeout=5000)
    body = page.locator("body").inner_text()

    # ⑤ 预填带入 + 目标 Agent 选中；非法字段未随入（结构化表单：top_event 字段带值）
    top_event_val = page.locator('input[placeholder="请填写顶事件"]').first.input_value()
    prefill_ok = (
        "已从智能导引带入预填草案" in body
        and "供电完全丧失" in top_event_val
        and "bogus" not in body  # 剥离字段不属于该 Agent schema，结构化表单里根本不存在
    )
    check("④→⑤确认后预填草案带入创建任务页（仅合法字段）", prefill_ok,
          f"top_event={top_event_val!r} bogus_in_body={'bogus' in body}")
    carried_ok = ATTACH_NAME in body and "已上传" in body
    check("⑤会话附件随草案带入创建页（已上传状态，人可移除，M7）", carried_ok,
          f"attach_in_body={ATTACH_NAME in body}")
    check("⑤签发仍由人完成（页面有『提交任务』按钮，导引未自动建任务）",
          "提交任务" in body, "")
    page.screenshot(path=str(SHOTS / "3_prefilled_create.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M6 GUIDE ACCEPTANCE ALL GREEN' if not failed else 'M6 GUIDE ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
