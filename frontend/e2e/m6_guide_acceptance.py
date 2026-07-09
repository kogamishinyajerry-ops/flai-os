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

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m6_guide_"))


class _StubGateway:
    """确定文本 stub：导引首轮即返回一条针对 fta_agent 的推荐——top_event 合法预填，
    外加一个非法字段 bogus 让确定性校验剥离（展示 stripped 告警）。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        payload = {
            "agent_id": "fta_agent",
            "rationale": "你的需求是对供电系统做故障树分析，fta_agent 正是做这个的。",
            "prefilled_inputs": {"top_event": "供电完全丧失", "bogus": "该字段不属于该 Agent"},
        }
        reply = (
            "明白了，你要对双通道供电系统做故障树分析。为你推荐故障树分析 Agent，并预填了顶事件。\n"
            f"<<RECOMMEND>>\n{json.dumps(payload, ensure_ascii=False)}\n<<END>>"
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
app.state.conversation_service.model_gateway = _StubGateway()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900})

    # ① 导引页 = 统一入口（首页）
    page.goto(BASE + "/", wait_until="networkidle")
    body = page.locator("body").inner_text()
    check("①导引页可达且为统一入口", "智能导引" in body and "导引不会替你创建任务" in body, body[:200])
    page.screenshot(path=str(SHOTS / "1_guide_empty.png"), full_page=True)

    # ② 发一句需求
    page.get_by_placeholder("你的名字（对话需具名）").fill("王工")
    page.locator(".composer textarea").fill("我要对双通道供电系统做故障树分析，顶事件是供电完全丧失")
    page.get_by_role("button", name="发送").click()

    # ③ 导引返回推荐卡片
    expect(page.locator(".reco-card")).to_be_visible(timeout=8000)
    body = page.locator("body").inner_text()
    reco_ok = (
        "推荐：" in body
        and "故障树" in body
        and "top_event" in body
        and "供电完全丧失" in body
        and "已剔除不合法字段" in body  # bogus 被确定性剥离并告警
        and "bogus" in body
    )
    check("③推荐卡片：Agent+预填草案+非法字段剔除告警", reco_ok, body[-500:])
    check("③'导引不代签'红线文案在卡片可见", "签发权在你" in body, "")
    page.screenshot(path=str(SHOTS / "2_recommendation.png"), full_page=True)

    # ④ 点确认 → 落创建任务页
    page.get_by_role("button", name="确认草案，去创建任务").click()
    page.wait_for_url(lambda url: "/tasks/new" in url, timeout=5000)
    expect(page.locator(".prefill-note")).to_be_visible(timeout=5000)
    body = page.locator("body").inner_text()

    # ⑤ 预填带入 + 目标 Agent 选中；非法字段未随入（只带合法预填）
    inputs_text = page.locator("textarea").first.input_value()
    prefill_ok = (
        "已从智能导引带入预填草案" in body
        and '"top_event"' in inputs_text
        and "供电完全丧失" in inputs_text
        and "bogus" not in inputs_text  # 剥离字段不会带进创建页
    )
    check("④→⑤确认后预填草案带入创建任务页（仅合法字段）", prefill_ok, inputs_text[:200])
    check("⑤签发仍由人完成（页面有『提交任务』按钮，导引未自动建任务）",
          "提交任务" in body, "")
    page.screenshot(path=str(SHOTS / "3_prefilled_create.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M6 GUIDE ACCEPTANCE ALL GREEN' if not failed else 'M6 GUIDE ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
