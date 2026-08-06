"""批七编队投影验收（真浏览器 + 真 JobRunner + 真 resolver，O1-O11）。

设计契约 docs/design/AGENT-TEAM-B7-DESIGN.md §四。覆盖：
  O1 batch 携 after → DB depends_on 落列 → 下游滞留 created → 上游 completed 后
     resolver 真接力（dependency_resolved 事件在场）→ UI 行翻活跃（真跑全链非 mock）；
  O2 诚实灯：waiting_upstream 行空心灯（is-hollow 且**无** is-pulsing）+ 无秒表；
  O3 接力回波只播一次（animationstart 计数器；状态沿+事件双通道同一抑制）；
  O4 密级 gate：sensitive 材料 + 缺省 internal 上限 agent → 单建 400 / batch 422
     （中性文案，零写入）；
  O5 依据投影：resolved=false 全链 amber「未核」，依据区计算色**无绿**；
  O6 拒答态：refusals 非空成员 completed（非 failed）+ amber 行（非红）；
  O7 收束假绿禁令：待签发在场时 squad 行无「全部完成/收束」类总结 + amber 段在场；
     全终态且零待签才「协作已收束」；
  O8 guide 含幻觉成员/非法引用 → 整案 fail-closed，只回自然语言澄清与唯一 Composer；
  O9 装载期 fail-closed：L3+job 无人签 / evidence required 无 findings → 拒载；
  O10 completed 状态词计算色=中性非绿；
  O11 prefers-reduced-motion：脉动灯静态降级（animation none）。

tamper witness（S4 tamper 轮实证）：
  - 断开 tasks.py batch 的 after→depends_on 映射 → O1 必红；
  - GuidePage 空心灯强加 is-pulsing → O2 必红；
  - squad.js 收束禁令强改「全部完成」 → O7 必红；
  - 注释 create_task/batch 的 clearance gate → O4 必红。

自包含：自起后端（tmp DB）+ JobRunner worker 线程 + 双 stub gateway（会话编排 /
runtime 排序）+ 真 chromium。fault_history 排序 stub 只在候选白名单内选取（从
prompt 提取 fault_ref），数字判据全在 workflow 确定性层。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" --with jieba --with openpyxl python frontend/e2e/batch_g_squad_acceptance.py

截图落 docs/reviews/batch-g-squad-shots/。
"""
from __future__ import annotations

import json
import re
import shutil
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
SHOTS = REPO / "docs" / "reviews" / "batch-g-squad-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn
import yaml

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

WORK = Path(tempfile.mkdtemp(prefix="flai_batch_g_"))

# fault 语料命中词（agents/fault_history_agent/data/fault_cases.json 的 tags）
FAULT_PROBLEM = "XR-100 连续运行两小时后间歇断电并出现母线复位，热浸时复现，冷却后恢复，怀疑接插件接触阻抗波动。"
REFUSE_PROBLEM = "海岚-9 在热浸后出现间歇断电，冷却后恢复。"
RANK_SLEEP_S = 8.0  # 排序窗人为放宽：给 O11 reduced-motion 与运行态断言一个稳定观察窗
# （3-lens P3：wait_status 轮询+双上下文开销会吃掉窗口前段，8s > 两个 6s expect 预算）


class _ConvStub:
    """会话编排 stub：按用户消息关键词路由三种 orchestrate 方案。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        last = ""
        for m in reversed(messages):
            if m.get("role") == "user":
                last = m.get("content") or ""
                break
        if "接力" in last:
            plan = {
                "decision": "orchestrate",
                "analysis": "先问候预热，再基于其产物检索历史故障。",
                "goal": "验证接力编队。",
                "workflow": "hello 先行，fault_history 等其产物后接力。",
                "agents": [
                    {"agent_id": "hello_agent", "role": "预热", "rationale": "参数已齐",
                     "prefilled_inputs": {"name": "编队验收"}},
                    {"agent_id": "fault_history_agent", "role": "历史故障检索", "rationale": "依赖上游产物",
                     "prefilled_inputs": {"problem_description": FAULT_PROBLEM, "model_type": "XR-100"},
                     "after": [0]},
                ],
            }
        elif "拒答" in last:
            plan = {
                "decision": "orchestrate",
                "analysis": "并行两名成员，其一将诚实拒答。",
                "goal": "验证拒答态。",
                "workflow": "并行执行。",
                "agents": [
                    {"agent_id": "hello_agent", "role": "预热", "rationale": "参数已齐",
                     "prefilled_inputs": {"name": "拒答验收"}},
                    {"agent_id": "fault_history_agent", "role": "未收录型号检索", "rationale": "验证拒答",
                     "prefilled_inputs": {"problem_description": REFUSE_PROBLEM, "model_type": "海岚-9"}},
                ],
            }
        elif "超出已审定" in last:
            # 切片 3 S3：guide 级 refuse 裁决（ADR-0033 三终点之一），
            # 供造第二工作段边界；_validate_refuse 三必填字段齐备。
            plan = {
                "decision": "refuse",
                "reason": "超出平台已审定能力，如实拒绝。",
                "residual_problems": ["该需求仍待解决"],
                "reframe": ["收敛到已审定工程域后重述"],
            }
        else:  # 幻觉 after 引用（O8）
            plan = {
                "decision": "orchestrate",
                "analysis": "含幻觉成员与非法 after 引用。",
                "goal": "验证剥离降级。",
                "workflow": "串行。",
                "agents": [
                    {"agent_id": "ghost_agent_o8", "role": "不存在", "rationale": "幻觉",
                     "prefilled_inputs": {}},
                    {"agent_id": "hello_agent", "role": "预热", "rationale": "真实",
                     "prefilled_inputs": {"name": "O8"}},
                    {"agent_id": "fta_agent", "role": "分析", "rationale": "after 引用被剪条目",
                     "prefilled_inputs": {"top_event": "供电完全丧失"}, "after": [0, 1]},
                ],
            }
        reply = f"方案如下。\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
        return {"content": reply, "token_usage": None, "model_name": "stub", "finish_reason": "stop"}


class _RuntimeStub:
    """runtime 排序 stub：只在 prompt 携带的候选 fault_ref 白名单内选取（workflow
    的 _parse_ranking 是真校验层）；sleep 制造稳定运行窗供 O11 观察。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        text = messages[-1].get("content") or ""
        refs = re.findall(r'"fault_ref":\s*"([^"]+)"', text)
        time.sleep(RANK_SLEEP_S)
        ranked = [
            {"fault_ref": r, "similarity_basis": "现象与触发条件标签重合",
             "disposition_summary": "合成记录处置摘要，仅供人工比对。"}
            for r in refs[:3]
        ]
        return {
            "content": json.dumps({"ranked": ranked}, ensure_ascii=False),
            "token_usage": None,
            "model_name": "stub",
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

app.state.conversation_service.model_gateway = _ConvStub()
app.state.runtime.model_gateway = _RuntimeStub()

# JobRunner 延迟启动：等待相（waiting_upstream）断言需要一个稳定的未执行窗口。
runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
runner_started = threading.Event()


def _run_worker() -> None:
    runner_started.wait()
    runner.run_forever()


threading.Thread(target=_run_worker, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


from _auth import login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")
API = login_httpx(BASE)


def conv_tasks(conv_id: str) -> list[dict[str, Any]]:
    raw = API.get(f"/api/conversations/{conv_id}/tasks").json()
    return raw if isinstance(raw, list) else raw.get("items", [])


def latest_conv_id() -> str:
    convs = API.get("/api/conversations?limit=5").json()
    lst = convs if isinstance(convs, list) else convs.get("items", [])
    assert lst, "诚实失败：拿不到会话"
    return lst[0]["id"]


def wait_status(task_id: str, statuses: set[str], timeout_s: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = API.get(f"/api/tasks/{task_id}").json()
        if last.get("status") in statuses:
            return last
        time.sleep(0.4)
    return last


def rgb_of(css_color: str) -> tuple[int, int, int]:
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", css_color or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else (0, 0, 0)


def is_greenish(css_color: str) -> bool:
    r, g, b = rgb_of(css_color)
    return g > r + 30 and g > b + 30


def open_plan_conv(page, prompt_text: str) -> str:
    """新会话 → stub 方案卡；返回会话 id。"""
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill(prompt_text)
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".plan-card").last).to_be_visible(timeout=8000)
    return latest_conv_id()


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)

    # ══ 会话一：接力编队（O1/O2/O3/O7/O5/O10/O11）══════════════════════════
    conv1 = open_plan_conv(page, "跑一遍接力编队验收")
    expect(page.locator(".open-plan-btn")).to_be_visible(timeout=8000)
    disclosure = page.locator(".route-disclosure").last
    check(
        "开工前只有一个主动作，成员细节默认折叠",
        page.locator(".open-plan-btn").count() == 1
        and page.locator(".open-plan-btn").inner_text().strip() == "按方案开始"
        and disclosure.get_attribute("open") is None
        and page.locator(".agent-card").first.is_visible() is False,
    )

    # 回波计数器先于开工安装（O3）：捕获期监听 animationstart，只认 sa-relay-echo 元素
    page.evaluate(
        """() => {
          window.__echoCount = 0;
          window.__echoProbePaused = false;
          document.addEventListener('animationstart', (e) => {
            const el = e.target;
            if (!window.__echoProbePaused && el && el.classList && el.classList.contains('sa-relay-echo')) {
              window.__echoCount += 1;
            }
          }, true);
        }"""
    )
    page.locator(".open-plan-btn").click()

    # O1（DB 层）：batch 原子创建——上游入队 / 下游滞留 created 且 depends_on 已落列。
    # 上游入队发生在事务 commit 之后（post-commit 原子入队），轮询窗口内可短暂
    # 读到 created——探针等到 queued（runner 未启动，队列态稳定不再前进）。
    deadline = time.time() + 8
    t_hello: dict[str, Any] = {}
    t_fault: dict[str, Any] = {}
    while time.time() < deadline:
        ts = conv_tasks(conv1)
        by_agent = {t["agent_id"]: t for t in ts}
        if len(ts) == 2:
            t_hello = by_agent.get("hello_agent", {})
            t_fault = by_agent.get("fault_history_agent", {})
            if t_hello.get("status") == "queued":
                break
        time.sleep(0.3)
    check("O1a batch 原子创建 2 任务", bool(t_hello) and bool(t_fault))
    check("O1b 上游无依赖原子入队", t_hello.get("status") == "queued", str(t_hello.get("status")))
    check(
        "O1c 下游滞留 created 且 after→depends_on 映射为真 task_id",
        t_fault.get("status") == "created" and t_fault.get("depends_on") == [t_hello.get("id")],
        json.dumps({"status": t_fault.get("status"), "depends_on": t_fault.get("depends_on")}, ensure_ascii=False),
    )

    # ══ S1（批 0 切片 1，P0-1 状态来找人）：编队总览行在可见面 ═══════════════
    # 开工后不展开披露，编队行必须在场（UI-PARADIGM #2）；此刻上游 queued
    # （工作态）→ 可见面脉动点+工作相段词。roster 明细仍属按需披露（下方展开）。
    face = page.locator(".sa-squad-line.sa-squad-face")
    try:
        expect(face).to_be_visible(timeout=8000)
        closed = page.locator(".route-disclosure").last.get_attribute("open") is None
        # 快照到账有窗口；queued/waiting_upstream 不属工作态（无脉动点）——
        # 只等相段词上屏，证明活状态在可见面到账（脉动由 O2 灯族覆盖）。
        deadline = time.time() + 8
        face_text = face.inner_text()
        while time.time() < deadline and not any(
            w in face_text for w in ("运行中", "已入队", "等待交接", "待你签发")
        ):
            page.wait_for_timeout(400)
            face_text = face.inner_text()
        check("S1a 开工后编队行在可见面（披露仍默认收起）", closed is True, face_text)
        check(
            "S1b 可见面编队行相段词到账（运行中/已入队/等待交接/待你签发其一）",
            any(w in face_text for w in ("运行中", "已入队", "等待交接", "待你签发")),
            face_text,
        )
        check("S1c 无待签成员可见面不长 CTA（绝不凑）",
              face.locator(".squad-review-cta").count() == 0)
        # S1g（codex PR#34 a11y 修复无回归面）：tabindex/aria-label 仅敏感行生长；
        # 现 roster 全 internal（仓内无 sensitive Agent，敏感路径 dormant，PR 留痕），
        # 故钉「非敏感行零焦点停点」——修复不得给普通成员行加 tab 噪点。
        check("S1g 非敏感成员行无焦点停点（tabindex/aria-label 零生长）",
              page.locator(".agent-name[tabindex], .agent-name[aria-label]").count() == 0)
    except Exception:
        for probe in ("S1a 开工后编队行在可见面（披露仍默认收起）",
                      "S1b 可见面编队行相段词到账（运行中/已入队/等待交接/待你签发其一）",
                      "S1c 无待签成员可见面不长 CTA（绝不凑）",
                      "S1g 非敏感成员行无焦点停点（tabindex/aria-label 零生长）"):
            check(probe, False, "可见面编队行缺失")

    # 成员级运行状态属于按需披露内容；测试主动展开后再检查，不把它改回常驻面板。
    disclosure.locator("summary").click()
    expect(page.locator(".agent-card").first).to_be_visible(timeout=3000)

    # O2：等待交接行=空心灯（is-hollow 无 is-pulsing）+ 无秒表 + 上游名旁白。
    # 红而不崩（批六 replay 教训）：tamper 断依赖时等待相整体缺失，探针必须
    # 逐条红、套件到达 FAILED 汇总，才算干净咬合（crash-type fail 不算）。
    hollow = page.locator(".status-lamp.is-hollow")
    try:
        expect(hollow).to_be_visible(timeout=8000)
        hollow_present = True
    except Exception:
        hollow_present = False
    if hollow_present:
        check("O2a 空心灯在场且无 is-pulsing", hollow.evaluate("el => !el.classList.contains('is-pulsing')") is True)
        fault_card = page.locator(".agent-card", has=page.locator(".status-lamp.is-hollow"))
        check("O2b 等待行无秒表 DOM", fault_card.locator(".sa-elapsed").count() == 0)
        check("O2c 状态词=等待交接", "等待交接" in fault_card.locator(".status-word").inner_text())
        stage = fault_card.locator(".sa-stageline")
        check(
            "O2d 旁白含上游人话名与自动交接承诺",
            "等待〈" in stage.inner_text() and "就绪后自动交接" in stage.inner_text(),
            stage.inner_text(),
        )
    else:
        for probe in ("O2a 空心灯在场且无 is-pulsing", "O2b 等待行无秒表 DOM",
                      "O2c 状态词=等待交接", "O2d 旁白含上游人话名与自动交接承诺"):
            check(probe, False, "等待相缺失（空心灯未出现）")

    # O7（前置相）：squad 行在场、含等待段、无收束/全部完成类总结
    squad = page.locator(".sa-squad-line")
    expect(squad).to_be_visible(timeout=8000)
    squad_text = squad.inner_text()
    check("O7a 编队行含「等待交接」段", "等待交接" in squad_text, squad_text)
    check(
        "O7b 非全终态绝无收束/全部完成措辞",
        ("收束" not in squad_text) and ("全部完成" not in squad_text),
        squad_text,
    )
    page.screenshot(path=str(SHOTS / "1_waiting_upstream.png"), full_page=True)

    # ══ 放行 worker：上游真跑 → resolver 真接力 ══
    runner_started.set()

    running_fault = wait_status(t_fault["id"], {"running", "validating", "parsing", "analyzing"}, timeout_s=30)
    check("O1d resolver 真把下游送进工作态", running_fault.get("status") in {"running", "validating", "parsing", "analyzing"}, str(running_fault.get("status")))

    # O11：排序窗内（RANK_SLEEP_S）同一真实页面切换媒体偏好做对照——
    # 正常态真脉动；reduce 后保留状态但 animation 必须归零。
    try:
        expect(page.locator(".status-lamp.is-pulsing").first).to_be_visible(timeout=6000)
        main_anim = page.locator(".status-lamp.is-pulsing").first.evaluate(
            "el => getComputedStyle(el).animationName"
        )
        check("O11a 正常上下文运行灯真有动画", main_anim not in ("none", ""), str(main_anim))
    except Exception as exc:  # 观察窗错过=诚实红，不静默
        check("O11a 正常上下文运行灯真有动画", False, f"观察窗错过：{exc}")
    # 媒体偏好切回 no-preference 会让同一个 CSS animation 重新触发 animationstart；
    # 这不是产品的状态/事件双通道重播，媒体探针窗口从 O3 计数器中隔离。
    page.evaluate("() => { window.__echoProbePaused = true; }")
    page.emulate_media(reduced_motion="reduce")
    try:
        expect(page.locator(".status-lamp.is-pulsing").first).to_be_visible(timeout=3000)
        r_anim = page.locator(".status-lamp.is-pulsing").first.evaluate(
            "el => getComputedStyle(el).animationName"
        )
        check("O11b reduced-motion 运行灯 animation=none", r_anim in ("none", ""), str(r_anim))
    except Exception as exc:
        check("O11b reduced-motion 运行灯 animation=none", False, f"观察窗错过：{exc}")
    finally:
        page.emulate_media(reduced_motion="no-preference")
        page.wait_for_timeout(250)
        page.evaluate("() => { window.__echoProbePaused = false; }")

    # O1（事件层）：dependency_resolved 事件真实在场（resolver 留痕）
    events = API.get(f"/api/tasks/{t_fault['id']}/events?limit=200").json()
    dep_events = [
        e for e in events
        if (e.get("payload") or {}).get("workflow_event_type") == "dependency_resolved"
        or e.get("event_type") == "dependency_resolved"
    ]
    check("O1e dependency_resolved 事件在场", len(dep_events) >= 1, f"count={len(dep_events)}")

    # fault 收官 → waiting_review（review-gated 包）
    settled = wait_status(t_fault["id"], {"waiting_review", "failed", "completed"}, timeout_s=40)
    check("接力任务落 waiting_review（人签闸在场）", settled.get("status") == "waiting_review", str(settled.get("status")))

    # O3：回波只播一次（状态沿+事件双通道、重复投递/轮询都不得重播）
    page.wait_for_timeout(4500)  # 回波 2×1.8s 播完 + 若有重播必然已发生
    echo_count = page.evaluate("() => window.__echoCount")
    check("O3 接力回波恰播一次", echo_count == 1, f"echoCount={echo_count}")

    # O5：依据 chip amber 未核 + 展开 EvidenceList 全链无绿。红而不崩：tamper
    # 卡死上游（如断依赖后任务永滞 created）时终审面整体缺失，逐条红到汇总。
    # map#46 #56：方案卡可见面新增聚合依据行复用 sa-evidence-chip 类（R-B 提升件），
    # 本组锚的是披露区内 per-member chip——作用域收进 details.route-disclosure 防双中。
    chip = page.locator("details.route-disclosure .sa-evidence-chip")
    try:
        expect(chip).to_be_visible(timeout=10000)
        chip_present = True
    except Exception:
        chip_present = False
    if chip_present:
        chip_text = chip.inner_text()
        check("O5a 依据 chip 计数在场且含未核", ("依据" in chip_text) and ("未核" in chip_text), chip_text)
        check("O5b 含未核整 chip 走 amber 语义类", chip.evaluate("el => el.classList.contains('has-unverified')") is True)
        chip.click()
        expand = page.locator(".sa-evidence-expand")
        expect(expand).to_be_visible(timeout=4000)
        check("O5c 展开后未核徽逐条在场", expand.locator(".ev-unverified").count() >= 1)
        ev_colors = expand.evaluate(
            """el => Array.from(el.querySelectorAll('*')).map(n => getComputedStyle(n).color)"""
        )
        check("O5d 依据区计算色无绿（绿仅 REAL 实测）", not any(is_greenish(c) for c in ev_colors))
    else:
        for probe in ("O5a 依据 chip 计数在场且含未核", "O5b 含未核整 chip 走 amber 语义类",
                      "O5c 展开后未核徽逐条在场", "O5d 依据区计算色无绿（绿仅 REAL 实测）"):
            check(probe, False, "依据 chip 未出现（成员未达终审面）")

    # O7（待签相）：待你签发 amber 段在场 + 仍无收束措辞
    squad_text2 = page.locator(".sa-squad-line").inner_text()
    check("O7c 待签相含「待你签发」", "待你签发" in squad_text2, squad_text2)
    check("O7d 待签相 amber 段在场", page.locator(".sa-squad-line .squad-seg.tone-amber").count() >= 1)
    check("O7e 待签相仍无收束措辞", "收束" not in squad_text2 and "全部完成" not in squad_text2, squad_text2)
    # S1（批 0 切片 1）：待签相可见面长 amber CTA，点击直开速览——不展开披露闭环。
    cta = page.locator(".squad-review-cta")
    try:
        expect(cta).to_be_visible(timeout=8000)
        check("S1d 待签相可见面 amber CTA 上屏", True, cta.inner_text())
        cta.click()
        page.wait_for_selector(".el-drawer", timeout=8000)
        check("S1e CTA 点击直开速览（状态中心抽屉）", True)
        # Esc 层层退出（UI-PARADIGM #7）：速览→中心→关闭。onEsc 挂在 sc-shell
        # （焦点须在内——键盘用户原态），先 focus 再两击必净空，否则抽屉
        # overlay 拦截后续 composer 点击。焦点在抽屉外 Esc 不生效记 retro。
        page.locator(".sc-shell").focus()
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        # 活体实证：el-drawer 关闭后节点留 DOM 隐藏（count 恒 1），detached 永假——等 hidden。
        page.wait_for_selector(".el-drawer", state="hidden", timeout=8000)
        check("S1e′ Esc 层层退出两击净空（速览→中心→关闭）", True)
    except Exception:
        check("S1d 待签相可见面 amber CTA 上屏", False, "可见面 CTA 缺失")
        check("S1e CTA 点击直开速览（状态中心抽屉）", False, "未验证")
        check("S1e′ Esc 层层退出两击净空（速览→中心→关闭）", False, "未验证")
    page.screenshot(path=str(SHOTS / "2_waiting_review_evidence.png"), full_page=True)

    # 批准放行 → O10 completed 中性非绿 + O7 终相收束
    resp = API.post(f"/api/tasks/{t_fault['id']}/review", json={"action": "approve", "comment": "e2e 放行"})
    check("批准放行 API 生效", resp.status_code == 200, f"status={resp.status_code}")
    done = wait_status(t_fault["id"], {"completed"}, timeout_s=15)
    check("放行后任务 completed", done.get("status") == "completed", str(done.get("status")))
    deadline = time.time() + 12
    settled_text = ""
    while time.time() < deadline:
        settled_text = page.locator(".sa-squad-line").inner_text()
        if "收束" in settled_text:
            break
        page.wait_for_timeout(500)
    check("O7f 全终态零待签才渲「协作已收束」", "协作已收束" in settled_text, settled_text)
    sw_colors = page.locator(".agent-status .status-word").evaluate_all(
        "els => els.map(el => getComputedStyle(el).color)"
    )
    check("O10 completed 状态词计算色非绿", len(sw_colors) >= 1 and not any(is_greenish(c) for c in sw_colors), str(sw_colors))
    page.screenshot(path=str(SHOTS / "3_settled.png"), full_page=True)

    # S1f（Codex PR#24 回归针）：同会话第二张方案卡出现后，可见面编队行只挂
    # 最新卡——历史卡不渲染当前活状态/签发 CTA（审批不挂错方案）。
    # 注意：stub 对不含「接力/拒答」的消息回 O8 幻觉编队（非法不渲染卡），
    # 故第二轮需求必须命中「接力」分支拿合法方案。
    page.locator(".composer-input textarea").fill("再来一轮接力编队。")
    page.locator('button.send-btn[aria-label="发送"]').click()
    try:
        expect(page.locator(".plan-card").nth(1)).to_be_visible(timeout=10000)
        page.wait_for_timeout(1200)
        faces = page.locator(".sa-squad-line.sa-squad-face")
        in_last = page.locator(".plan-card").last.locator(".sa-squad-line.sa-squad-face")
        check("S1f 多方案卡可见面编队行只挂最新卡（count==1 且在末卡内）",
              faces.count() == 1 and in_last.count() == 1,
              f"faces={faces.count()} in_last={in_last.count()}")
    except Exception:
        check("S1f 多方案卡可见面编队行只挂最新卡（count==1 且在末卡内）", False, "第二张方案卡未出现")

    # ══ S3（切片 3 方案 B）：工作段分隔+中段折叠+时间戳降噪 ════════════════
    # 边界 1=首次开工的任务创建戳；边界 2=拒答终点（同 agent 二次开工被
    # planHasTasks 拦是产品语义，不硬造）；再补一轮无方案消息开当前段 → 三段齐。
    try:
        before_ai = page.locator(".ai-body").count()
        page.locator(".composer-input textarea").fill("这件事超出已审定范围，请如实处理。")
        page.locator('button.send-btn[aria-label="发送"]').click()
        page.wait_for_function(
            f"document.querySelectorAll('.ai-body').length > {before_ai}", timeout=30000
        )
        before_ai = page.locator(".ai-body").count()
        page.locator(".composer-input textarea").fill("一句话总结今天的讨论。")
        page.locator('button.send-btn[aria-label="发送"]').click()
        page.wait_for_function(
            f"document.querySelectorAll('.ai-body').length > {before_ai}", timeout=30000
        )
        page.wait_for_timeout(800)
        fold = page.locator(".seg-fold")
        mid_bubble = page.locator(".bubble-row.user", has_text="再来一轮接力编队")
        check("S3a 中段默认折（fold 行含轮往来；中段泡在 DOM 不可见）",
              fold.count() == 1 and "轮往来" in fold.inner_text()
              and mid_bubble.count() == 1 and mid_bubble.is_visible() is False,
              fold.inner_text() if fold.count() else "(无 fold 行)")
        fold.click()
        page.wait_for_timeout(400)
        check("S3b 展开后中段可见+分隔线在场（单向展开）",
              mid_bubble.is_visible() is True
              and page.locator(".seg-divider").count() >= 2)
        u1_time = page.locator(".bubble-row.user").first.locator(".bubble-time")
        a1_time = page.locator(".bubble-row.assistant").first.locator(".bubble-time")
        op_u1 = u1_time.evaluate("el => getComputedStyle(el).opacity") if u1_time.count() else "none"
        op_a1 = a1_time.evaluate("el => getComputedStyle(el).opacity") if a1_time.count() else "none"
        check("S3c 段界时间戳常显、非段界 hover-only",
              op_u1 == "1" and op_a1 == "0", f"u1={op_u1} a1={op_a1}")
        check("S3d 首段与当前段豁免折叠",
              page.locator(".bubble-row.user").first.is_visible() is True
              and page.locator(".ai-body").last.is_visible() is True)
    except Exception:
        for probe in ("S3a 中段默认折（fold 行含轮往来；中段泡在 DOM 不可见）",
                      "S3b 展开后中段可见+分隔线在场（单向展开）",
                      "S3c 段界时间戳常显、非段界 hover-only",
                      "S3d 首段与当前段豁免折叠"):
            check(probe, False, "三段结构未成立")

    # ══ 会话二：拒答态（O6）══════════════════════════════════════════════════
    conv2 = open_plan_conv(page, "跑一遍拒答验收")
    expect(page.locator(".open-plan-btn")).to_be_visible(timeout=8000)
    page.locator(".route-disclosure").last.locator("summary").click()
    expect(page.locator(".agent-card").first).to_be_visible(timeout=3000)
    page.locator(".open-plan-btn").click()
    deadline = time.time() + 8
    t_refuse: dict[str, Any] = {}
    while time.time() < deadline:
        ts = conv_tasks(conv2)
        by_agent = {t["agent_id"]: t for t in ts}
        if len(ts) == 2 and "fault_history_agent" in by_agent:
            t_refuse = by_agent["fault_history_agent"]
            break
        time.sleep(0.3)
    check("O6 前置：拒答会话 batch 创建成功", bool(t_refuse))
    settled2 = wait_status(t_refuse["id"], {"waiting_review", "failed"}, timeout_s=30)
    check("O6a 拒答运行落 waiting_review 非 failed", settled2.get("status") == "waiting_review", str(settled2.get("status")))
    API.post(f"/api/tasks/{t_refuse['id']}/review", json={"action": "approve", "comment": "e2e 放行"})
    done2 = wait_status(t_refuse["id"], {"completed"}, timeout_s=15)
    check("O6b 放行后 completed（诚实拒答=履约非失败）", done2.get("status") == "completed", str(done2.get("status")))
    refusal_line = page.locator(".sa-refusal-line")
    expect(refusal_line).to_be_visible(timeout=12000)
    check("O6c 拒答行文案如实计数", "已如实说明" in refusal_line.inner_text(), refusal_line.inner_text())
    line_color = refusal_line.evaluate("el => getComputedStyle(el).color")
    r, g, b = rgb_of(line_color)
    check("O6d 拒答行 amber 非红（g 通道足量）", g > 90 and not is_greenish(line_color), line_color)
    refusal_line.click()
    detail_ul = page.locator(".sa-refusal-detail")
    expect(detail_ul).to_be_visible(timeout=4000)
    check("O6e 展开见拒答理由（未收录型号明说）", "未收录" in detail_ul.inner_text(), detail_ul.inner_text()[:120])
    page.screenshot(path=str(SHOTS / "4_refusal_amber.png"), full_page=True)

    # ══ O4：密级 gate（API 面，单建+batch 双路）══════════════════════════════
    up = API.post(
        "/api/files/upload",
        files={"file": ("sens.txt", b"synthetic sensitive payload", "text/plain")},
        data={"classification": "sensitive"},
    )
    check("O4 前置：sensitive 文件上传成功", up.status_code == 200, f"status={up.status_code}")
    fid = up.json().get("id") if up.status_code == 200 else None
    r1 = API.post("/api/tasks", json={"agent_id": "hello_agent", "inputs": {"name": "x"}, "input_file_ids": [fid]})
    check("O4a 单建路 400 + 中性文案", r1.status_code == 400 and "密级准入上限" in r1.json().get("detail", ""), r1.text[:160])
    before = len(API.get("/api/tasks").json())
    hello_snapshot = API.get("/api/agents/hello_agent").json()
    r2 = API.post("/api/tasks/batch", json={
        "operation_id": "batch_g_clearance_o4",
        "pinned_versions": {"hello_agent": hello_snapshot["version"]},
        "pinned_package_digests": {
            "hello_agent": hello_snapshot["package_snapshot_digest"],
        },
        "items": [
            {"agent_id": "hello_agent", "inputs": {"name": "a"}},
            {"agent_id": "hello_agent", "inputs": {"name": "b"}, "input_file_ids": [fid]},
        ],
    })
    after_cnt = len(API.get("/api/tasks").json())
    check(
        "O4b batch 路 422 批错清单 + 全有全无零写入",
        r2.status_code == 422 and "密级准入上限" in str(r2.json()) and after_cnt == before,
        f"status={r2.status_code} delta={after_cnt - before}",
    )

    # ══ 会话三：O8 含幻觉成员/非法引用的整案 fail-closed ═════════════════════
    page.goto(BASE + "/", wait_until="networkidle")
    page.locator(".composer textarea").fill("跑一遍幻觉引用验收")
    page.get_by_role("button", name="发送").click()
    expect(page.locator(".ai-body").last).to_contain_text(
        "每个必须保留的工作环节、预期结果和衔接关系", timeout=8000
    )
    conv3 = latest_conv_id()
    conv3_data = API.get(f"/api/conversations/{conv3}").json()
    messages = conv3_data.get("messages", [])
    terminal = messages[-1] if messages else {}
    check(
        "O8a 非法编排不持久化 recommendation，也不创建残案任务",
        terminal.get("role") == "assistant"
        and terminal.get("recommendation") is None
        and conv_tasks(conv3) == [],
        json.dumps(terminal, ensure_ascii=False)[:300],
    )
    o8_body = page.locator("body").inner_text()
    check(
        "O8b 只回自然语言澄清与唯一 Composer，零成员卡/字段墙/内部 ghost 泄漏",
        page.locator(".plan-card, .agent-card, .route-summary").count() == 0
        and page.get_by_role("button", name="按方案开始").count() == 0
        and page.locator(".composer textarea").count() == 1
        and page.locator('.composer input[type="file"]').count() == 1
        and "ghost_agent_o8" not in o8_body
        and "/tasks/new" not in page.url,
        o8_body[-360:],
    )

    browser.close()

# ══ O9：装载期 fail-closed（进程内 registry 真扫描）════════════════════════════
from backend.app.runtime.registry import AgentRegistry  # noqa: E402

_AGENT_SCHEMA = REPO / "contracts" / "agent.schema.json"


def _patch_yaml(pkg: Path, **overrides: Any) -> None:
    data = yaml.safe_load((pkg / "agent.yaml").read_text(encoding="utf-8"))
    for dotted, value in overrides.items():
        node = data
        parts = dotted.split(".")
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    (pkg / "agent.yaml").write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")


def _rejected(agents_dir: Path, agent_id: str) -> bool:
    """拒载语义=隔离不注册 + errors 记名（scan 不抛，quarantine 非 crash）。"""
    reg = AgentRegistry(agents_dir, _AGENT_SCHEMA)
    reg.scan()
    return reg.get(agent_id) is None and len(reg.errors) >= 1


o9a_dir = WORK / "o9a"
o9a_dir.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", o9a_dir / "l3_agent")
_patch_yaml(
    o9a_dir / "l3_agent",
    **{
        "id": "l3_agent",
        "expertise.domain": "generic",
        "expertise.specialty": "O9 构造包",
        "expertise.usefulness_level": "L3",
        "expertise.charter": "我是 O9 构造包，用于验证装载期拒载。",
        "workflow.requires_human_review": False,
    },
)
check("O9a L3+job 无人签 → 装载期拒载", _rejected(o9a_dir, "l3_agent") is True)

o9b_dir = WORK / "o9b"
o9b_dir.mkdir()
shutil.copytree(REPO / "agents" / "fta_agent", o9b_dir / "ev_agent")
_patch_yaml(o9b_dir / "ev_agent", **{"id": "ev_agent", "evidence_policy.required": True, "evidence_policy.kinds": ["knowledge_doc"]})
# fta 的 output_schema 顶层无 findings → required=True 必拒载
check("O9b evidence required 无 findings → 装载期拒载", _rejected(o9b_dir, "ev_agent") is True)
# 对照：同包不声明 evidence_policy → 正常装载（证明 O9b 咬的是校验不是包本身坏）
o9c_dir = WORK / "o9c"
o9c_dir.mkdir()
shutil.copytree(REPO / "agents" / "fta_agent", o9c_dir / "ok_agent")
_patch_yaml(o9c_dir / "ok_agent", **{"id": "ok_agent"})
check("O9c 对照包正常装载（校验有判别力非全拒）", _rejected(o9c_dir, "ok_agent") is False)

failed = [x for x in results if x[1] is not True]
print(f"\n{'BATCH-G SQUAD ALL GREEN' if not failed else 'BATCH-G SQUAD FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
