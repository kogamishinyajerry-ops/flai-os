"""M10 治理闭环验收（ADR-0018）：样本→评测→晋升全链 UI 走查。

自包含：脚本自起后端（tmp 目录注入，绝不碰真实 data/ 与真实 agents/——
晋升会真改 agent.yaml、固化会真写 case 文件，全部发生在 tmp 包副本上）
+ 自跑 Job Runner + 真 chromium 走 UI。

覆盖：
  ⓪Issue #4 sample 级认可：actor 只取会话 username，draft 同源计数且幂等
  ①治理面板可开（gov-entry→gov-dialog，尚未跑过评测）
  ②跑评测→全绿摘要 3/3（真实 runtime 全链，同步等待）
  ③fail-closed UI 见证：不勾人工确认直接晋升→逐条拒绝原因可见
  ④勾选确认→晋升成功→maturity 徽章 L1
  ④'磁盘铁证：tmp 包 agent.yaml 的 maturity 行真实变 L1
  ④''晋升区随 L1 消失（transition_supported 只认 L0→L1）
  ⑤晋升记录 L0→L1 可见
  ⑥用户任务→waiting_review→状态坞 peek 批准放行
  ⑦固化入口出现→固化→case_file 回显
  ⑦'磁盘铁证：case_*_from_sample.json 落盘且 curation=draft
  ⑧固化后再跑评测：draft 不计数仍 3/3，待策展一节可见
  ⑨eval 任务隔离：任务历史页不出现 eval:case 任务

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with playwright --with uvicorn --with fastapi \
    --with jsonschema --with pyyaml --with httpx --with python-multipart \
    --with "pydantic>2" python frontend/e2e/m10_governance_acceptance.py
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

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

DIST = REPO / "frontend" / "dist"
SHOTS = REPO / "docs" / "reviews" / "m10-acceptance-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import uvicorn

from backend.app.governance.eval_worker import EvalRunner
from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app

# ── 自起后端：tmp 包副本（hello + governed 变体：审核门+落样+三 case 评测集）──
WORK = Path(tempfile.mkdtemp(prefix="flai_m10_acceptance_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
shutil.copytree(REPO / "agents" / "hello_agent", AGENTS_DIR / "hello_agent")
HELLO_CASES = AGENTS_DIR / "hello_agent" / "eval_cases"
for f in HELLO_CASES.glob("*.json"):
    f.unlink()
GOV_DIR = AGENTS_DIR / "governed_agent"
shutil.copytree(REPO / "agents" / "hello_agent", GOV_DIR)
_yaml = GOV_DIR / "agent.yaml"
_text = _yaml.read_text(encoding="utf-8")
assert "id: hello_agent" in _text and "requires_human_review: false" in _text
_yaml.write_text(
    _text.replace("id: hello_agent", "id: governed_agent")
    .replace("requires_human_review: false", "requires_human_review: true"),
    encoding="utf-8",
)
GOV_CASES = GOV_DIR / "eval_cases"
for f in GOV_CASES.glob("*.json"):
    f.unlink()
for name, case in (
    ("case_001.json", {"case_id": "case_001", "description": "正常路停审",
                       "inputs": {"name": "世界"},
                       "checks": [{"kind": "status_is", "value": "waiting_review"}]}),
    ("case_002.json", {"case_id": "case_002", "description": "缺字段失败路",
                       "inputs": {},
                       "checks": [{"kind": "status_is", "value": "failed"}]}),
    ("case_003.json", {"case_id": "case_003", "description": "非法类型失败路",
                       "inputs": {"name": 1},
                       "checks": [{"kind": "status_is", "value": "failed"}]}),
):
    (GOV_CASES / name).write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

app = create_app(
    agents_dir=AGENTS_DIR,
    tools_dir=REPO / "tools_impl",
    contracts_dir=REPO / "contracts",
    db_path=WORK / "flai_os.db",
    uploads_dir=WORK / "uploads",
    task_runs_dir=WORK / "task_runs",
    frontend_dist_dir=DIST,
)
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="error"))
threading.Thread(target=server.run, daemon=True).start()

import httpx

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

# T1 异步评测队列（GH #2）：POST /eval-runs 现只入队 status='queued'，靠 EvalRunner
# 在配额门内认领并驱动到终态；UI「跑评测」按钮轮询才等得到 3/3。缺此 worker → run
# 永远 queued → 前端轮询超时。与 JobRunner 同进程单实例，配额门原子性在 storage 层。
eval_worker = EvalRunner(
    agent_registry=app.state.agent_registry,
    runtime=app.state.runtime,
    conn_factory=app.state.conn_factory,
    uploads_dir=app.state.uploads_dir,
    task_runs_dir=app.state.task_runs_dir,
    quota=2,
    poll_interval=0.1,
)
threading.Thread(target=eval_worker.run_forever, daemon=True).start()

SHOTS.mkdir(parents=True, exist_ok=True)
results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))



from _auth import E2E_USERNAME, login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "验收工程师")
API = login_httpx(BASE)

# ── ⓪ Issue #4：requires_review=false 的完成样本按 sample id 认可 ──
created = API.post(
    "/api/tasks",
    json={"agent_id": "hello_agent", "inputs": {"name": "逐样本认可"}},
)
created.raise_for_status()
ack_task_id = created.json()["id"]
deadline = time.time() + 30
ack_task = {}
while time.time() < deadline:
    response = API.get(f"/api/tasks/{ack_task_id}")
    response.raise_for_status()
    ack_task = response.json()
    if ack_task.get("status") in ("completed", "failed", "cancelled"):
        break
    time.sleep(0.2)
ack_samples = API.get(f"/api/tasks/{ack_task_id}/samples").json()
check(
    "⓪完成任务沉淀一条待认可 sample",
    ack_task.get("status") == "completed"
    and len(ack_samples) == 1
    and ack_samples[0].get("accepted_by_engineer") is None,
    f"task={ack_task.get('status')} samples={ack_samples}",
)
ack_sample_id = ack_samples[0]["id"] if ack_samples else -1
anonymous = httpx.post(
    f"{BASE}/api/samples/{ack_sample_id}/acknowledge",
    json={},
    timeout=5,
)
forged = API.post(
    f"/api/samples/{ack_sample_id}/acknowledge",
    json={"actor": "mallory"},
)
first_ack = API.post(f"/api/samples/{ack_sample_id}/acknowledge", json={})
replayed_ack = API.post(f"/api/samples/{ack_sample_id}/acknowledge", json={})
ack_body = first_ack.json() if first_ack.status_code == 200 else {}
check(
    "⓪人签边界与幂等资源",
    anonymous.status_code == 401
    and forged.status_code == 422
    and first_ack.status_code == 200
    and replayed_ack.status_code == 200
    and replayed_ack.json() == ack_body
    and ack_body.get("acknowledged_by_username") == E2E_USERNAME,
    (
        f"anonymous={anonymous.status_code} forged={forged.status_code} "
        f"first={first_ack.status_code} replay={replayed_ack.status_code}"
    ),
)
counter = API.get("/api/agents/hello_agent/curated_cases_count")
fixed_hello = sorted(HELLO_CASES.glob("case_*_from_sample.json"))
fixed_hello_doc = (
    json.loads(fixed_hello[0].read_text(encoding="utf-8"))
    if len(fixed_hello) == 1
    else {}
)
check(
    "⓪同源 curation 计数只增加 draft",
    counter.status_code == 200
    and counter.json()
    == {
        "agent_id": "hello_agent",
        "count": 1,
        "approved": 0,
        "draft": 1,
        "broken": 0,
    }
    and len(fixed_hello) == 1
    and fixed_hello_doc.get("curation") == "draft",
    f"counter={counter.text} files={[path.name for path in fixed_hello]}",
)

with sync_playwright() as p:
    browser = p.chromium.launch()
    # pin 亮色：theme.js 默认跟随系统，颜色/文案断言不许随 CI 环境漂移
    page = browser.new_page(viewport={"width": 1440, "height": 900}, color_scheme="light")
    login_context(page.context, BASE)  # ADR-0019：真实登录换会话 cookie

    # ── ① 治理面板可开 ──
    page.goto(BASE + "/portal", wait_until="networkidle")
    gov_card = page.locator(".agent-card", has_text="governed_agent")
    gov_card.locator(".gov-entry").click()
    expect(page.locator(".gov-dialog")).to_be_visible(timeout=5000)
    dialog_text = page.locator(".gov-dialog").inner_text()
    check("①治理面板可开且显示空历史", "尚未跑过评测" in dialog_text, dialog_text[:200])
    page.screenshot(path=str(SHOTS / "1_gov_dialog.png"), full_page=True)
    page.keyboard.press("Escape")

    # ── ⑥ L0 用户任务 → waiting_review → 状态坞批准放行 ──
    created = API.post(
        "/api/tasks",
        json={"agent_id": "governed_agent", "inputs": {"name": "治理链样本"}},
    )
    created_body = created.json() if created.status_code in (200, 201) else {}
    task_id = created_body.get("id", "")
    created_ok = (
        created.status_code in (200, 201)
        and re.fullmatch(r"task_[0-9a-f]{32}", task_id) is not None
    )
    check(
        "⑥前置：认证 API 创建治理样本任务成功",
        created_ok,
        f"status={created.status_code} body={created.text[:200]}",
    )
    if created_ok is not True:
        raise RuntimeError(
            f"M10 前置任务创建失败 {created.status_code}: {created.text[:200]}"
        )
    page.goto(BASE + f"/tasks/{task_id}", wait_until="networkidle")
    deadline = time.time() + 30
    while time.time() < deadline:
        if "等待人工审核" in page.locator("body").inner_text():
            break
        time.sleep(1)
    page.locator(".status-dock").click()
    sc_item = page.locator(".sc-item", has_text="governed_agent")
    expect(sc_item.first).to_be_visible(timeout=5000)
    sc_item.first.click()
    expect(page.locator(".peek-approve")).to_be_visible(timeout=8000)
    quick_review = page.locator(".peek-review-card")
    quick_approve_box = quick_review.get_by_role("button", name="批准放行").bounding_box()
    quick_reject_box = quick_review.get_by_role("button", name="驳回").bounding_box()
    check(
        "⑥状态坞批准/驳回触控高度均≥44px",
        quick_approve_box is not None
        and quick_reject_box is not None
        and quick_approve_box["height"] >= 44
        and quick_reject_box["height"] >= 44,
        f"approve={quick_approve_box} reject={quick_reject_box}",
    )
    assert "验收工程师" in quick_review.inner_text()
    # ── R-D+W1（map46 #56）：peek 签发入口同页 VerificationCard（整卡复用）──
    # 选择器严格 scope 进 .sc-shell：底层详情页（/tasks/<id>）同样渲染
    # .verify-card，全局定位会双命中（strict 违例/重影假证）；抽屉 destroy-on-close
    # 保证关闭后零 DOM，但在场期间必须作用域区分。
    sc_shell = page.locator(".sc-shell")
    peek_vcard = sc_shell.locator(".verify-card")
    expect(peek_vcard).to_be_visible(timeout=8000)
    check(
        "⑥R-D+W1 peek 同页核验卡在场（抽屉作用域内唯一，防详情页重影）",
        peek_vcard.count() == 1,
        f"drawer_scoped_count={peek_vcard.count()}",
    )
    peek_vcard_text = peek_vcard.inner_text()
    check(
        "⑥R-D+W1 诚实地板句逐字在场（通识解释仅供参考…以确定性工具与人签为准）",
        "通识解释仅供参考；工程结论以确定性工具与人签为准" in peek_vcard_text,
        peek_vcard_text[-120:],
    )
    check(
        "⑥R-D+W1 签发卡仍在场（核验卡不挤压签发动作区）",
        sc_shell.locator(".peek-review-card").count() == 1
        and sc_shell.locator(".peek-approve").is_visible(),
        "",
    )
    page.locator(".peek-approve").click()
    page.get_by_role("button", name="确认批准放行").click()
    deadline = time.time() + 15
    approved = False
    while time.time() < deadline:
        shell_text = (
            page.locator(".sc-shell").inner_text()
            if page.locator(".sc-shell").count()
            else ""
        )
        if "已完成" in shell_text or page.locator(".sc-fix-row").count() > 0:
            approved = True
            break
        time.sleep(0.5)
    check("⑥状态坞批准放行成功", approved, shell_text[:300])

    # ── ⑦ live package 仍为 L0 时固化；输出只能是 draft ──
    expect(page.locator(".sc-fix-row")).to_be_visible(timeout=8000)
    page.locator(".sc-fix-sample-btn").click()
    deadline = time.time() + 15
    fix_text = ""
    while time.time() < deadline:
        if page.locator(".sc-fix-result").count() > 0:
            fix_text = page.locator(".sc-fix-result").inner_text()
            if "case_" in fix_text:
                break
        time.sleep(0.5)
    check("⑦L0 固化成功且 case_file 回显", "case_" in fix_text, fix_text[:200])
    fixed = sorted(GOV_CASES.glob("case_*_from_sample.json"))
    fixed_doc = (
        json.loads(fixed[0].read_text(encoding="utf-8"))
        if len(fixed) == 1
        else {}
    )
    check(
        "⑦'固化 case 落盘且 curation=draft、provenance 对账",
        len(fixed) == 1
        and fixed_doc.get("curation") == "draft"
        and (fixed_doc.get("provenance") or {}).get("task_id") == task_id,
        f"files={[path.name for path in fixed]}",
    )
    page.screenshot(path=str(SHOTS / "5_fix_sample.png"), full_page=True)
    page.keyboard.press("Escape")

    # ── ② 带 draft 跑评测 → 全绿仍 3/3（draft 不进入 approved 覆盖）──
    page.goto(BASE + "/portal", wait_until="networkidle")
    page.locator(".agent-card", has_text="governed_agent").locator(".gov-entry").click()
    expect(page.locator(".gov-dialog")).to_be_visible(timeout=5000)
    page.locator(".gov-run-btn").click()
    deadline = time.time() + 60
    summary = ""
    while time.time() < deadline:
        if page.locator(".gov-run-summary").count() > 0:
            summary = page.locator(".gov-run-summary").inner_text()
            if "3/3" in summary:
                break
        time.sleep(1)
    check("②跑评测→全绿摘要 3/3", "3/3" in summary, summary[:200])
    check(
        "⑧draft 不计数且待策展可见",
        "待策展" in page.locator(".gov-dialog").inner_text(),
        page.locator(".gov-dialog").inner_text()[:400],
    )
    page.screenshot(path=str(SHOTS / "2_eval_green.png"), full_page=True)

    # ── ③ fail-closed UI 见证：不勾确认直接晋升 → 逐条拒绝可见 ──
    page.locator(".gov-promote-submit").click()
    page.wait_for_timeout(1500)
    errors_visible = page.locator(".gov-promote-errors").count() > 0
    err_text = page.locator(".gov-promote-errors").inner_text() if errors_visible else ""
    # 必须锁到 manual_confirmation 那条拒绝文案（「布尔」/「记名」来自后端逐条判定），
    # 不许「出现任意错误框」平凡通过（异源审 P3-17）
    check("③不勾人工确认晋升被拒且原因可见",
          errors_visible is True and ("布尔" in err_text or "记名" in err_text),
          err_text[:200])
    page.screenshot(path=str(SHOTS / "3_promote_rejected.png"), full_page=True)

    # ── ④ 勾选确认 → 晋升成功 → L1 ──
    page.locator(".gov-promote-confirm").click()
    page.locator(".gov-promote-submit").click()
    deadline = time.time() + 15
    promoted = False
    while time.time() < deadline:
        # 真成功信号（2026-07-15 竞态修复）：晋升块随 governanceAgent.maturity 刷成 L1
        # 而消失——这只可能发生在 promote API 已响应（服务端 yaml 已写盘）之后。
        # 旧判据 `"L1" in gov-dialog 文本` 平凡可满足（梯注「仅 L0→L1 机器化把关」/
        # 按钮「申请晋升 L1」恒含该串），首轮 poll 即真 → ④' 磁盘读跑在后端写盘前，
        # 机器负载高时竞态必咬（IndexError 实录见 verify_all_final.log 2026-07-15）。
        if (page.locator(".gov-dialog").count() > 0
                and page.locator(".gov-promote-submit").count() == 0):
            promoted = True
            break
        time.sleep(0.5)
    check("④勾选确认→晋升成功→面板见 L1",
          promoted and "L1" in page.locator(".gov-dialog").inner_text(),
          page.locator(".gov-dialog").inner_text()[:300])

    # ④' 磁盘铁证：tmp 包 yaml 真实改写（detail 用 next+哨兵，缺行时如实显示而非 IndexError 炸检查器）
    yaml_after = _yaml.read_text(encoding="utf-8")
    check("④'agent.yaml maturity 行真实变 L1",
          re.search(r"^maturity: L1$", yaml_after, flags=re.MULTILINE) is not None,
          next((l for l in yaml_after.splitlines() if l.startswith("maturity")),
               "【无 maturity 行】"))

    # ④'' 晋升区随 L1 消失（本批只支持 L0→L1）
    page.wait_for_timeout(1000)
    check("④''晋升提交按钮随 L1 消失", page.locator(".gov-promote-submit").count() == 0,
          f"count={page.locator('.gov-promote-submit').count()}")

    # ── ⑤ 晋升记录可见 ──
    dialog_text = page.locator(".gov-dialog").inner_text()
    check("⑤晋升记录 L0→L1 可见", "L0" in dialog_text and "L1" in dialog_text and "验收工程师" in dialog_text,
          dialog_text[-300:])
    page.screenshot(path=str(SHOTS / "4_promoted.png"), full_page=True)
    page.keyboard.press("Escape")

    # ── ⑧ 晋升后 live package 不可再写，既有 draft 字节保持不变 ──
    fixed_before_l1_retry = {
        path.name: path.read_bytes()
        for path in GOV_CASES.glob("*.json")
    }
    l1_fix = API.post(
        "/api/agents/governed_agent/eval-cases",
        json={
            "sample_id": (fixed_doc.get("provenance") or {}).get(
                "sample_id",
                -1,
            )
        },
    )
    l1_detail = l1_fix.json().get("detail", "")
    check(
        "⑧L1 后固化触盘前拒绝且 live package 字节不变",
        l1_fix.status_code == 409
        and ("不可写" in l1_detail or "L0" in l1_detail)
        and {
            path.name: path.read_bytes()
            for path in GOV_CASES.glob("*.json")
        }
        == fixed_before_l1_retry,
        f"status={l1_fix.status_code} detail={l1_detail}",
    )
    page.screenshot(path=str(SHOTS / "6_draft_not_counted.png"), full_page=True)
    page.keyboard.press("Escape")

    # ── ⑨ eval 任务隔离：任务历史页不出现 eval:case 任务 ──
    page.goto(BASE + "/tasks", wait_until="networkidle")
    hist = page.locator("body").inner_text()
    # eval 任务名恒为 eval:case_NNN.json——它们缺席即隔离 witness；
    # 用户任务（governed_agent）必须在场作对照（防「页面全空也算隔离」的平凡绿）。
    # 票 #62 B9 锚随迁：副行不再裸显 agent_id（人话名上主视觉），id 收 .cl-sub title
    # 悬浮——互审 F2 处置：断言**可见**副行承载该 id（行真渲染+id 披露双证，
    # 不是只查 DOM 属性存在的弱化锚）。
    gov_sub = page.locator(".cl-sub[title='governed_agent']")
    check("⑨任务历史默认视图不含 eval 任务",
          "eval:case" not in hist and gov_sub.count() == 1 and gov_sub.first.is_visible(),
          hist[:400])
    page.screenshot(path=str(SHOTS / "7_history_isolated.png"), full_page=True)

    # ── ⑩ 批次六 B6-1a：入队后首轮询失败→防重复入队闭环（B5 Codex R1 #5
    #    修复的活体锁）。路由只断状态轮询 GET（/eval-runs/* 带尾段），POST
    #    /eval-runs 与列表 GET 不受影响——正好夹住「POST 成功、首轮询失败」
    #    的重复入队窗口：错误行+行内重试上屏，「跑评测」被 latestRunInFlight
    #    压住（loading 已解除，禁用只能来自在跑判定）。──────────────────
    page.goto(BASE + "/portal", wait_until="networkidle")
    gov_card2 = page.locator(".agent-card", has_text="governed_agent")
    gov_card2.locator(".gov-entry").click()
    expect(page.locator(".gov-dialog")).to_be_visible(timeout=5000)
    page.route("**/eval-runs/*", lambda r: r.abort())
    page.locator(".gov-run-btn").click()
    try:
        page.wait_for_selector(".gov-resume-error", timeout=12000)
        err_txt = page.locator(".gov-resume-error").inner_text()
        page.wait_for_timeout(300)  # finally 解除 loading 后再验按钮禁用来源
        btn_disabled = page.locator(".gov-run-btn").is_disabled()
        retry_present = page.locator(".gov-resume-retry").count() == 1
    except Exception:
        err_txt, btn_disabled, retry_present = "(无错误行)", False, False
    check("⑩入队后首轮询失败→错误行+行内重试在场+「跑评测」压住（绝不诱导重复入队）",
          ("评测状态刷新失败" in err_txt) is True and btn_disabled is True and retry_present is True,
          f"err={err_txt[:60]} disabled={btn_disabled} retry={retry_present}")
    # 重试=同一恢复车道真闭环：恢复轮询→run 终态→错误行清除+按钮解锁
    page.unroute("**/eval-runs/*")
    page.locator(".gov-resume-retry").click()
    try:
        page.wait_for_selector(".gov-resume-error", state="detached", timeout=60000)
        deadline = time.time() + 30
        btn_enabled = False
        while time.time() < deadline:
            if page.locator(".gov-run-btn").is_enabled():
                btn_enabled = True
                break
            time.sleep(0.5)
    except Exception:
        btn_enabled = False
    check("⑩'行内重试恢复轮询到终态（错误行清除+「跑评测」解锁）",
          btn_enabled is True)
    page.keyboard.press("Escape")

    browser.close()

failed = [r for r in results if r[1] is not True]
print(f"\n{'M10 ACCEPTANCE ALL GREEN' if not failed else 'M10 ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
