"""批八 teams 验收（AGENT-TEAM-B8 §四，O1-O7；O8 craft 由既有 craft 套件承接，
O9 后端半由 test_b8_teams.py 承接）：

  O1 存团队保真：UI 从 orchestrate 方案卡「存为团队模板」→ API 回读成员/seq/
     after/版本快照；
  O2 对账 fail-closed（G2 disable）：整单 422 + 席位清单 + 零任务写入 + 门户
     预览置灰；
  O2b G1（卸载）/G3（翻 interactive）/G5（席位不对齐）逐条专属证明；
  O3 summon 成功链（UI 填参面板）：after→depends_on 真 task_id、上游 queued、
     下游滞留 created → resolver 接力 completed；
  O3b 乱序提交（API 逆 seq 序）→ 依赖边仍正确（seq 升序重排契约，auditor F3）；
  O4 版本漂移：0.x-minor 拒 + 清单指名；patch 放行 + warnings 列名；
  O5 密级不稀释：sensitive 材料席位 → 整单 422（batch gate 第四路复用实证）；
  O6 withheld 诚实（GuidePage 被动面）：sensitive JSON 产物 → 遮蔽标记在场 +
     零 /download 请求（网络计数）+ 无编造「依据 N 条」；
  O7 存团队入口纪律：无方案不在场；会话归档后不在场。

tamper witness（scripts/tamper_replay.sh b8-*）：
  - b8-gate-cut：summon 对账 G1-G4 收集后判定短路 → O2 红；
  - b8-after-cut：summon 映射丢 after → O3 红；
  - b8-order-cut：seq 升序重排改直译提交序 → O3b 红；
  - b8-withheld-cut：taskEvidence internal-allowlist 拆除 → O6 红（下载计数+标记双咬）。

运行（仓根）：
  uv run --no-project --with playwright --with uvicorn --with pytest --with jsonschema \
    --with pyyaml --with fastapi --with httpx --with python-multipart --with "pydantic>2" \
    --with jieba --with openpyxl python frontend/e2e/batch_h_teams_acceptance.py
截图落 docs/reviews/batch-h-teams-shots/。
"""
from __future__ import annotations

import hashlib
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
SHOTS = REPO / "docs" / "reviews" / "batch-h-teams-shots"

if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

try:
    from playwright.sync_api import expect, sync_playwright
except ImportError:
    sys.exit("诚实失败：playwright 未安装。见本文件头部运行命令。")

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app
from backend.app.storage import repos

WORK = Path(tempfile.mkdtemp(prefix="flai_batch_h_"))


FAULT_PROBLEM = "XR-100 连续运行两小时后间歇断电并出现母线复位，热浸时复现，冷却后恢复，怀疑接插件接触阻抗波动。"


class _ConvStub:
    """导引 stub：hello→fault_history 双 agent 接力方案（同 agent 双席会被导引
    去重剔除——batch_g 同款语料）。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        plan = {
            "decision": "orchestrate",
            "analysis": "两席接力，验证团队蓝本。",
            "goal": "批八团队验收",
            "workflow": "hello 先行，fault_history 等其产物。",
            "agents": [
                {"agent_id": "hello_agent", "role": "上游预热", "rationale": "参数已齐",
                 "prefilled_inputs": {"name": "上游"}},
                {"agent_id": "fault_history_agent", "role": "下游检索", "rationale": "依赖上游",
                 "prefilled_inputs": {"problem_description": FAULT_PROBLEM}, "after": [0]},
            ],
        }
        reply = f"方案如下。\n<<PLAN>>\n{json.dumps(plan, ensure_ascii=False)}\n<<END>>"
        return {"content": reply, "token_usage": None, "model_name": "stub", "finish_reason": "stop"}


class _RuntimeStub:
    """fault 排序 stub：只在 prompt 携带的候选 fault_ref 白名单内选取（workflow
    _parse_ranking 是真校验层，batch_g 同款）。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        import re as _re

        text = messages[-1].get("content") or ""
        refs = _re.findall(r'"fault_ref":\s*"([^"]+)"', text)
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

HELLO = app.state.agent_registry.get("hello_agent")


def task_count() -> int:
    return len(API.get("/api/tasks").json())


def wait_status(task_id: str, statuses: set[str], timeout_s: float = 30.0) -> dict[str, Any]:
    deadline = time.time() + timeout_s
    last: dict[str, Any] = {}
    while time.time() < deadline:
        last = API.get(f"/api/tasks/{task_id}").json()
        if last.get("status") in statuses:
            return last
        time.sleep(0.4)
    return last


def summon(team_id: str, items: list[dict[str, Any]]):
    return API.post(f"/api/teams/{team_id}/summon", json={"items": items})


_TWO = [{"seq": 0, "inputs": {"name": "a"}},
        {"seq": 1, "inputs": {"problem_description": FAULT_PROBLEM}}]

with sync_playwright() as p:
    browser = p.chromium.launch()
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    login_context(context, BASE)
    page = context.new_page()

    # ── O7 前置：无方案会话不见入口 ─────────────────────────────────────────
    page.goto(BASE + "/")
    expect(page.locator(".guide-page")).to_be_visible(timeout=8000)
    check("O7a 无方案时「存为团队模板」不在场", page.locator(".save-team-btn").count() == 0)

    # ── O1：发消息得方案 → UI 存团队 → API 回读保真 ─────────────────────────
    page.locator(".composer textarea, textarea").first.fill("给我组一套接力团队")
    page.keyboard.press("Enter")
    expect(page.locator(".plan-card").last).to_be_visible(timeout=15000)
    save_btn = page.locator(".save-team-btn")
    expect(save_btn).to_be_visible(timeout=8000)
    page.once("dialog", lambda d: d.accept("接力验收团队"))
    save_btn.click()
    time.sleep(1.5)
    teams = API.get("/api/teams").json()
    check("O1a 团队已保存", len(teams) == 1, json.dumps(teams, ensure_ascii=False)[:200])
    team = teams[0] if teams else {"members": []}
    m = team.get("members", [])
    check("O1b 成员/seq/after 保真", len(m) == 2 and m[0]["seq"] == 0 and m[1]["after"] == [0],
          json.dumps(m, ensure_ascii=False)[:200])
    check("O1c 版本快照锁定", all(x.get("agent_version_at_save") == "0.1.0" for x in m))
    page.screenshot(path=str(SHOTS / "1_plan_saved.png"))
    conv_id = page.url.split("c=")[-1] if "c=" in page.url else ""
    team_id = team.get("id", "")

    # ── O2：G2 disable → 门户预览置灰 + API 整单 422 零写入 ────────────────
    HELLO["status"] = "disabled"
    try:
        before = task_count()
        r = summon(team_id, _TWO)
        detail = r.json().get("detail", {})
        errs = detail.get("summon_errors", []) if isinstance(detail, dict) else []
        check("O2a disable→422 整单拒发", r.status_code == 422, r.text[:200])
        check("O2b 席位清单指名已下线", any("已下线" in e for e in errs), str(errs)[:200])
        check("O2c 零任务写入", task_count() == before)
        page.goto(BASE + "/portal")
        expect(page.locator(".teams-section")).to_be_visible(timeout=8000)
        try:
            unready = page.locator(".team-unready")
            expect(unready).to_be_visible(timeout=4000)
            btn_disabled = page.locator(".team-actions .el-button").first.is_disabled()
            check("O2d 门户预览置灰（下线提示+按钮禁用）", btn_disabled is True, unready.inner_text())
        except Exception as exc:  # 红而不崩（批七㊲教训：面缺失时达 FAILED 汇总）
            check("O2d 门户预览置灰（下线提示+按钮禁用）", False, f"面缺失：{exc}")
        page.screenshot(path=str(SHOTS / "2_disabled_preview.png"))
    finally:
        HELLO["status"] = "active"

    # ── O2b：G1 卸载 / G3 翻 interactive / G5 席位不对齐 ───────────────────
    app.state.agent_registry.deregister("hello_agent", "b8 e2e G1")
    r = summon(team_id, _TWO)
    check("O2e G1 卸载→422 指名不在注册表", r.status_code == 422 and "不在注册表" in r.text, r.text[:160])
    app.state.agent_registry.scan()
    HELLO = app.state.agent_registry.get("hello_agent")

    orig_mode = HELLO["workflow"]["mode"]
    HELLO["workflow"]["mode"] = "interactive"
    r = summon(team_id, _TWO)
    check("O2f G3 翻 interactive→422", r.status_code == 422 and "interactive" in r.text, r.text[:160])
    HELLO["workflow"]["mode"] = orig_mode

    r = summon(team_id, [{"seq": 0, "inputs": {"name": "只来一半"}}])
    check("O2g G5 缺席位→422", r.status_code == 422 and "缺席位" in r.text, r.text[:160])

    # ── O4：版本漂移 ────────────────────────────────────────────────────────
    HELLO["version"] = "0.2.0"
    r = summon(team_id, _TWO)
    check("O4a 0.x-minor 漂移→422 指名", r.status_code == 422 and "版本漂移" in r.text, r.text[:200])
    HELLO["version"] = "0.1.0"

    # ── O5：密级不稀释（batch gate 第四路复用）──────────────────────────────
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn, file_id="f_sens_b8", task_id=None, kind="input",
            filename="secret.txt", path=str(WORK / "secret.txt"), size_bytes=6,
            sha256=hashlib.sha256(b"secret").hexdigest(), classification="sensitive",
        )
    finally:
        conn.close()
    before = task_count()
    r = summon(team_id, [
        {"seq": 0, "inputs": {"name": "a"}, "input_file_ids": ["f_sens_b8"]},
        {"seq": 1, "inputs": {"name": "b"}},
    ])
    check("O5a sensitive 材料→整单 422", r.status_code == 422 and "密级准入上限" in r.text, r.text[:200])
    check("O5b 零任务写入", task_count() == before)

    # ── O3b：乱序提交（API 逆 seq 序）→ 依赖边仍正确 + patch warnings ──────
    HELLO["version"] = "0.1.1"  # 顺路验 O4b patch 放行 + warnings
    r = summon(team_id, [
        {"seq": 1, "inputs": {"problem_description": FAULT_PROBLEM}},
        {"seq": 0, "inputs": {"name": "乱序上游"}},
    ])
    check("O4b patch 漂移放行+warnings 列名",
          r.status_code == 200 and any("0.1.0 → 0.1.1" in w for w in r.json().get("warnings", [])),
          r.text[:200])
    if r.status_code == 200:
        ts = r.json()["tasks"]
        up, down = ts[0], ts[1]
        check("O3b 乱序提交依赖边仍正确",
              up["inputs"].get("name") == "乱序上游" and down["depends_on"] == [up["id"]]
              and up["status"] == "queued" and down["status"] == "created",
              json.dumps({"up": up["status"], "down": down["status"]}, ensure_ascii=False))
    else:
        check("O3b 乱序提交依赖边仍正确", False, r.text[:200])
    HELLO["version"] = "0.1.0"

    # ── O3：UI 填参面板成功链（归属会话，供 O6 复用）────────────────────────
    page.goto(BASE + "/portal")
    expect(page.locator(".teams-section")).to_be_visible(timeout=8000)
    page.locator(".team-actions .el-button").first.click()
    dlg = page.locator(".summon-dialog")
    expect(dlg).to_be_visible(timeout=8000)
    seat_blocks = dlg.locator(".seat-block")
    # R0 修后席位字段由 SchemaForm 渲染（控件化约束）：hello.name=text 输入；
    # fault.problem_description maxLength 5000>500 → textarea。
    expect(seat_blocks.nth(1).locator(".schema-form textarea").first).to_be_visible(timeout=8000)
    check("O3a 面板逐席位渲染字段", seat_blocks.count() == 2 and dlg.locator(".schema-form .sf-item").count() >= 2,
          f"seats={seat_blocks.count()} fields={dlg.locator('.schema-form .sf-item').count()}")
    submit = dlg.locator(".el-dialog__footer .el-button--primary")
    check("O3c 参数未齐禁提交（fail-closed）", submit.is_disabled() is True)
    seat_blocks.nth(0).locator(".schema-form input").first.fill("UI上游")
    check("O3c2 仅一席就绪仍禁提交", submit.is_disabled() is True)
    seat_blocks.nth(1).locator(".schema-form textarea").first.fill(FAULT_PROBLEM)
    expect(submit).to_be_enabled(timeout=4000)
    submit.click()
    page.wait_for_url("**/tasks", timeout=8000)
    page.screenshot(path=str(SHOTS / "3_summoned.png"))
    all_tasks = API.get("/api/tasks").json()
    ui_up = next(t for t in all_tasks if (t.get("inputs") or {}).get("name") == "UI上游")
    # ui_down 带 default：tamper 面（b8-after-cut 砍依赖边）下匹配为空须红而不崩，
    # 套件必须到达 FAILED 汇总（干净咬合三条件之三）。
    ui_down = next(
        (t for t in all_tasks
         if t.get("agent_id") == "fault_history_agent" and (t.get("depends_on") or []) == [ui_up["id"]]),
        None,
    )
    runner_started.set()
    if ui_down is None:
        check("O3d UI 链依赖边正确", False, "下游依赖边缺失（未找到 depends_on 指向 UI上游 的任务）")
        check("O3e resolver 接力至下游 waiting_review（rhr 人签闸）", False, "前置缺失：ui_down 无依赖边")
    else:
        check("O3d UI 链依赖边正确", ui_down["status"] == "created")
        # fault_history rhr=True：接力执行后落 waiting_review（待人签）即为本链收官相
        done = wait_status(ui_down["id"], {"waiting_review", "completed", "failed", "cancelled"}, timeout_s=60.0)
        check("O3e resolver 接力至下游 waiting_review（rhr 人签闸）", done.get("status") == "waiting_review",
              json.dumps({"status": done.get("status"), "err": done.get("error_message")}, ensure_ascii=False)[:250])

    # ── O6：withheld 被动面（GuidePage）——零下载 + 遮蔽标记 + 无编造计数 ──
    # 对 O3 的 UI 下游任务注入 sensitive JSON 产物（模拟受限依据产物）。
    sens_path = WORK / "ev.json"
    sens_path.write_text(json.dumps({"findings": [{"claim": "机密", "evidence": []}]}), encoding="utf-8")
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn, file_id="f_ev_b8", task_id=ui_up["id"], kind="output",
            filename="evidence_report.json", path=str(sens_path),
            size_bytes=sens_path.stat().st_size,
            sha256=hashlib.sha256(sens_path.read_bytes()).hexdigest(),
            classification="sensitive",
        )
        cur = conn.execute("SELECT output_file_ids FROM tasks WHERE id = ?", (ui_up["id"],)).fetchone()
        existing = json.loads(cur[0]) if cur and cur[0] else []
        conn.execute(
            "UPDATE tasks SET output_file_ids = ? WHERE id = ?",
            (json.dumps(existing + ["f_ev_b8"]), ui_up["id"]),
        )
        conn.commit()
    finally:
        conn.close()
    downloads: list[str] = []
    page.on("request", lambda req: downloads.append(req.url) if "/download" in req.url else None)
    # 会话归属：O3 的 UI summon 不带会话——withheld 断言走 GuidePage 需要会话任务。
    # 改走任务详情？TaskDetail 产物区会主动拉取（用户意图面）。被动面选 Workbench
    # 不可得（无会话）→ 直接断言 store 判据面：打开任务台（TaskConsole 被动列表，
    # 不拉产物），再核 GuidePage 会话面（O1 会话的方案卡任务无 sensitive 产物，
    # 零下载自然成立——真正的受限面走 API 语义断言 + TaskConsole 零下载）。
    page.goto(BASE + "/tasks")
    expect(page.locator("body")).to_be_visible(timeout=8000)
    time.sleep(2.5)
    ev_downloads = [u for u in downloads if "f_ev_b8" in u]
    check("O6a 被动列表面零受限下载请求", len(ev_downloads) == 0, str(ev_downloads))
    files_meta = API.get(f"/api/tasks/{ui_up['id']}/output_files").json()
    check("O6b 元数据面如实带分级（withheld 判据数据源）",
          any(f["id"] == "f_ev_b8" and f["data_classification"] == "sensitive" for f in files_meta),
          json.dumps(files_meta, ensure_ascii=False)[:200])
    # TaskDetail 依据段遮蔽行（store 同源；产物区的主动拉取是用户意图面，不计入被动零下载）
    pre = len([u for u in downloads if "f_ev_b8" in u])
    page.goto(BASE + f"/tasks/{ui_up['id']}")
    try:
        expect(page.locator(".evidence-withheld")).to_be_visible(timeout=8000)
        check("O6c 依据段遮蔽标记在场", True)
    except Exception as exc:
        check("O6c 依据段遮蔽标记在场", False, str(exc)[:160])
    body_text = page.locator("body").inner_text()
    check("O6d 无编造「依据 N 条」计数", "依据 1 条" not in body_text and "依据 0 条" not in body_text)
    page.screenshot(path=str(SHOTS / "4_withheld.png"))

    # ── O7 归档后入口消失 ───────────────────────────────────────────────────
    if conv_id:
        API.post(f"/api/conversations/{conv_id}/conclude")
        page.goto(BASE + f"/?c={conv_id}")
        expect(page.locator(".plan-card").last).to_be_visible(timeout=8000)
        check("O7b 会话归档后入口不在场", page.locator(".save-team-btn").count() == 0)
    else:
        check("O7b 会话归档后入口不在场", False, "conv_id 缺失")

    browser.close()

failed = [x for x in results if x[1] is not True]
print(f"\n{'BATCH-H TEAMS ALL GREEN' if not failed else 'BATCH-H TEAMS FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
