"""M8 P4 协作工作台全链验收：导引规划 → 工作台只读蓝图 → 回对话补充 → 任务归会话。

这是 M8 编排官愿景的端到端闭环（真浏览器）：
  ① 导引给出 orchestrate 协作方案（2 个 Agent），验收脚本从创建响应捕获真实会话；
  ② 深链 /workbench/:sessionId 见目标 + 分工架构（蓝图）+
     roster（2 个 Agent，均「尚未召集」）+ 进度 0/2；
  ③ 成员卡零手工启动 CTA，全页只留一个「回到对话补充信息」；
  ④ 点击后回 /?c=<session>，只用文字/附件继续说明；
  ⑤ 认证 API 仅准备工作台夹具任务，再回会话验证任务归属与进度 1/2；
  ⑥ 结束协作后蓝图只读，既有任务不受影响；
  ⑦ /workbench 旧深链继续重定向任务台。

自包含：自起后端（tmp）+ stub gateway（本机无内网 key）+ 真 chromium。**不起 worker**
（任务停在 queued 即可证分组，避免 fta 无内网 key 的非确定失败干扰断言）。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba python frontend/e2e/m8_collab_chain_acceptance.py

截图落 docs/reviews/m8-collab-chain-shots/。
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
SHOTS = REPO / "docs" / "reviews" / "m8-collab-chain-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_m8_chain_"))


class _StubGateway:
    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        plan = {
            "decision": "orchestrate",
            "analysis": "这个任务要先做控制逻辑，再做故障树。",
            "goal": "完成双通道供电的控制逻辑与故障树分析。",
            "workflow": "control_logic_agent 先出控制逻辑，fta_agent 再做故障树。",
            "agents": [
                {
                    "agent_id": "control_logic_agent",
                    "role": "生成控制逻辑状态机",
                    "rationale": "结构化生成",
                    "prefilled_inputs": {
                        "system_name": "双通道供电系统",
                        "states": ["双路正常", "A路失效", "B路失效", "供电完全丧失"],
                        "transitions": [
                            {"from": "双路正常", "to": "A路失效", "condition": "发电机A失效"},
                            {"from": "双路正常", "to": "B路失效", "condition": "发电机B失效"},
                            {"from": "A路失效", "to": "供电完全丧失", "condition": "发电机B同时失效"},
                            {"from": "B路失效", "to": "供电完全丧失", "condition": "发电机A同时失效"},
                        ],
                    },
                },
                {
                    "agent_id": "fta_agent",
                    "role": "搭建并分析故障树",
                    "rationale": "推理辅助",
                    "prefilled_inputs": {
                        "top_event": "供电完全丧失",
                        "system_description": "双通道供电系统（发电机A/B + 汇流条 + 转换开关）",
                        "components": ["发电机A", "发电机B", "汇流条", "转换开关"],
                    },
                },
            ],
        }
        reply = f"这需要两个 Agent 接力协作。\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
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



from _auth import login_context, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")  # pin 亮色：theme.js 默认跟随系统，颜色断言不许随 CI 环境漂移
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ① 导引 → orchestrate 方案
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("做双通道供电的控制逻辑和故障树")
    with page.expect_response(
        lambda response: response.request.method == "POST"
        and response.url == BASE + "/api/conversations"
    ) as conversation_response_info:
        page.get_by_role("button", name="发送").click()
    conversation_response = conversation_response_info.value
    conversation_body = (
        conversation_response.json()
        if conversation_response.status in (200, 201)
        else {}
    )
    session_id = conversation_body.get("id", "")
    conversation_captured = (
        conversation_response.status in (200, 201)
        and isinstance(session_id, str)
        and re.fullmatch(r"conv_[0-9a-f]{32}", session_id) is not None
    )
    check(
        "①导引创建响应给出真实会话血缘",
        conversation_captured,
        f"status={conversation_response.status} body={conversation_response.text()[:200]}",
    )
    if conversation_captured is not True:
        raise RuntimeError(
            f"导引会话创建失败 {conversation_response.status}: "
            f"{conversation_response.text()[:200]}"
        )
    page.wait_for_url(re.compile(rf"/\?c={re.escape(session_id)}$"), timeout=5000)
    expect(page.locator(".plan-card")).to_be_visible(timeout=8000)
    check("①导引给出 orchestrate 协作方案", page.locator(".plan-card").count() == 1)
    check("①导引 URL 精确绑定创建响应中的会话", page.url == f"{BASE}/?c={session_id}", page.url)

    # ② 工作台是历史/治理深链，不再从方案卡暴露第二套执行入口。
    page.goto(BASE + f"/workbench/{session_id}", wait_until="networkidle")
    session_url = page.url
    page.wait_for_selector(".member", timeout=5000)
    body = page.locator("body").inner_text()
    sess_ok = (
        "协作会话" in body
        and "完成双通道供电的控制逻辑与故障树分析" in body  # goal
        and "分工架构" in body                              # blueprint
        and page.locator(".member").count() == 2            # roster 2 个 Agent
        and body.count("尚未召集") == 2                     # 都还没召集
        and "0 / 2" in body                                 # 进度
    )
    check("②工作台会话：目标+分工架构+roster(2)+进度0/2", sess_ok,
          f"members={page.locator('.member').count()} body={body[-500:]}")
    page.screenshot(path=str(SHOTS / "1_session_before.png"), full_page=True)

    # ③ 成员卡只读，全页只保留一个返回主对话的澄清动作。
    clarify = page.get_by_role("button", name="回到对话补充信息")
    read_only_ok = (
        page.locator(".member button").count() == 0
        and clarify.count() == 1
        and page.get_by_role("button", name="去创建此任务").count() == 0
    )
    check("③工作台成员卡零手工启动，全页唯一澄清动作", read_only_ok,
          f"member_buttons={page.locator('.member button').count()} clarify={clarify.count()}")

    # ④ 缺信息回原对话，用唯一文字框/附件入口继续补充。
    clarify.click()
    page.wait_for_url(re.compile(rf"/\?c={session_id}$"), timeout=5000)
    clarification_ok = (
        page.locator(".composer textarea").count() == 1
        and page.locator('input[type="file"]').count() == 1
        and page.locator(".agent-preview").count() == 0
    )
    check("④回原对话自然澄清：唯一文字框 + 附件，零字段表", clarification_ok, page.url)
    page.screenshot(path=str(SHOTS / "2_back_to_conversation.png"), full_page=True)

    # ⑤ 任务详情/工作台分组的前置数据由认证 API 创建；这只是测试夹具，不冒充
    # 工程师 UI 流程。带 conversation_id 验证真实会话血缘。
    created = page.request.post(
        BASE + "/api/tasks",
        data={
            "agent_id": "fta_agent",
            "conversation_id": session_id,
            "inputs": {
                "top_event": "供电完全丧失",
                "system_description": "双通道供电系统（发电机A/B + 汇流条 + 转换开关）",
                "components": ["发电机A"],
            },
        },
    )
    created_body = created.json() if created.status in (200, 201) else {}
    task_id = created_body.get("id", "")
    created_ok = (
        created.status in (200, 201)
        and isinstance(task_id, str)
        and re.fullmatch(r"task_[0-9a-f]{32}", task_id) is not None
    )
    check("⑤前置：认证 API 创建会话归属任务成功", created_ok,
          f"status={created.status} body={created.text()[:200]}")
    if created_ok is not True:
        raise RuntimeError(f"M8 前置任务创建失败 {created.status}: {created.text()[:200]}")
    page.goto(session_url, wait_until="networkidle")
    page.wait_for_selector(".member", timeout=5000)
    body = page.locator("body").inner_text()
    summoned_ok = (
        "已召集 · 1 个任务" in body
        and "尚未召集" in body           # control_logic 仍未召集
        and "1 / 2" in body              # 进度推进
        and page.locator(".task-chip").count() >= 1
    )
    check("⑤回会话：fta 已召集(1 任务)+进度 1/2+任务归本会话", summoned_ok,
          f"chips={page.locator('.task-chip').count()} body={body[-500:]}")

    # ⑤b 批次五 C3 clay 预算：蓝图徽章/逐 chip 动作字/eyebrow/「已召集」常驻降灰
    #    ——工作台 clay 只留 chip 工作灯与进度大数字（computed 色直断，回染必咬）。
    # ⑤b 前置夹具（Codex R0 P2 暴露的真覆盖空洞）：人签流程下召集产物恒为
    # waiting_review→走 chip-review（amber 状态语义）分支，chip-action 从不渲染，
    # 旧 "(none)" sentinel 把这个洞遮成了绿。直翻一条为 running（m9 同款「只为
    # 渲染路径提供 fixture」口径，不冒充业务状态机）让「查看进度 →」真实上屏受审。
    import sqlite3
    _conn = sqlite3.connect(WORK / "flai_os.db")
    _conn.execute("UPDATE tasks SET status='running' WHERE id IN (SELECT id FROM tasks LIMIT 1)")
    _conn.commit()
    _conn.close()
    # 不 reload：会话 chips 走增量订阅（批A Task 6），翻转 ≤5s 自动上屏——
    # reload 会改变滚动几何，让顶部 fixed dock pill 盖住 ⑥ 的点击目标。
    page.wait_for_selector(".chip-action", timeout=15000)
    # 运行时解析 --clay（诚实 P2：硬编码字面量随调色静默过期→oracle 失咬）。
    clay_rgb = page.evaluate(
        "() => { const s = document.createElement('span'); s.style.color = 'var(--clay)';"
        " document.body.appendChild(s); const v = getComputedStyle(s).color; s.remove(); return v; }")
    # 在场先断言（Codex R0 P2）："(none)" sentinel 会让被审元素被删除时静默跳过
    # （per-element 空真值洞）——夹具已保证 running chip 带行内动作，缺席应当红。
    check("⑤b0 chip-action 在场（夹具契约：任务 chip 带行内动作字）",
          (page.locator(".chip-action").count() >= 1) is True,
          f"count={page.locator('.chip-action').count()}")
    bp_c = page.locator(".bp-tag").first.evaluate("el => getComputedStyle(el).color")
    act_c = page.locator(".chip-action").first.evaluate("el => getComputedStyle(el).color")
    kick_c = page.locator(".sess-goal-kicker").first.evaluate("el => getComputedStyle(el).color")
    sum_c = page.locator(".member-state.summoned").first.evaluate("el => getComputedStyle(el).color")
    clay_budget_ok = all(c != clay_rgb for c in (bp_c, act_c, kick_c, sum_c))
    check("⑤b clay 预算：bp-tag/chip-action/kicker/已召集 全非 clay（降灰承载信息）",
          clay_budget_ok is True, f"clay={clay_rgb} bp={bp_c} act={act_c} kick={kick_c} sum={sum_c}")
    # 夹具窗口收口：探针断言完即翻回召集原生态 waiting_review（同样等订阅
    # 回读，不 reload），⑥ 起流程与夹具零耦合。
    _conn = sqlite3.connect(WORK / "flai_os.db")
    _conn.execute("UPDATE tasks SET status='waiting_review' WHERE status='running'")
    _conn.commit()
    _conn.close()
    page.wait_for_selector(".chip-review", timeout=15000)
    page.screenshot(path=str(SHOTS / "3_session_after.png"), full_page=True)

    # ⑥ 结束协作 → 归档只读（结束 = 真的结束；成员任务不受影响）
    assert page.get_by_role("button", name="结束协作").count() == 1, "active 会话应有结束协作入口"
    page.get_by_role("button", name="结束协作").click()
    page.get_by_role("button", name="确定结束").click()  # ElMessageBox 二次确认
    expect(page.locator(".sess-hero")).to_contain_text("已归档", timeout=6000)
    body = page.locator("body").inner_text()
    conclude_ok = (
        "已归档" in body
        and page.get_by_role("button", name="结束协作").count() == 0   # 归档后不再可结束
        and page.get_by_role("button", name="回到对话补充信息").count() == 0
        and "会话已归档" in body
        and "已召集 · 1 个任务" in body                                  # 已建任务仍在
    )
    check("⑥结束协作→归档只读（澄清入口消失，成员任务不受影响）", conclude_ok,
          f"conclude_btn={page.get_by_role('button', name='结束协作').count()} clarify={page.get_by_role('button', name='回到对话补充信息').count()} body={body[-400:]}")
    page.screenshot(path=str(SHOTS / "4_session_concluded.png"), full_page=True)

    # ⑦（2b 契约重立）：/workbench 旧深链重定向任务台，且左栏「最近对话」
    # 罗列该协作会话（会话列表随双 Surface 收敛进对话侧栏——WorkbenchHome
    # 一级页面已退役）；任务台列表含本链创建的成员任务。
    page.goto(BASE + "/workbench", wait_until="networkidle")
    page.wait_for_url(re.compile(r"/tasks$"), timeout=5000)
    page.wait_for_selector(".cl-item", timeout=5000)
    sidebar = page.locator(".sb-convos").inner_text()
    home_ok = (
        "完成双通道供电的控制逻辑与故障树分析" in sidebar  # 会话在对话侧栏（goal 作标题）
        and page.locator(".cl-item").count() >= 1          # 成员任务在任务台列表
    )
    check("⑦/workbench→任务台重定向 + 会话入对话侧栏 + 成员任务入列", home_ok,
          f"convos={sidebar[:200]} items={page.locator('.cl-item').count()}")
    page.screenshot(path=str(SHOTS / "5_console_home.png"), full_page=True)

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M8 COLLAB CHAIN ALL GREEN' if not failed else 'M8 COLLAB CHAIN FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
