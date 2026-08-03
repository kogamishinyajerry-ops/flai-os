"""批八 teams 验收（AGENT-TEAM-B8 §四，O1-O7；O8 craft 由既有 craft 套件承接，
O9 后端半由 test_b8_teams.py 承接）：

  O1 团队蓝本保真：Guide 始终不暴露「存为团队模板」；测试用认证
     API 夹具从 orchestrate 方案生成蓝本，回读成员/seq/after/版本快照；
  O2 对账 fail-closed（G2 disable）：整单 422 + 席位清单 + 零任务写入 + 门户
     预览置灰；
  O2b G1（卸载）/G3（翻 interactive）/G5（席位不对齐）逐条专属证明；
  O3 主对话唯一「按方案开工」成功链：after→depends_on 真 task_id、上游 queued、
     下游滞留 created → resolver 接力 completed；
  O3b 乱序提交（API 逆 seq 序）→ 依赖边仍正确（seq 升序重排契约，auditor F3）；
  O4 版本漂移：0.x-minor 拒 + 清单指名；patch 放行 + warnings 列名；
  O5 密级不稀释：sensitive 材料席位 → 整单 422（batch gate 第四路复用实证）；
  O6 withheld 诚实（GuidePage 被动面）：sensitive JSON 产物 → 遮蔽标记在场 +
     零 /download 请求（网络计数）+ 无编造「依据 N 条」；
  O7 工程师入口纪律：无方案、有方案、归档后均没有手工存团队/
     逐席填参/手工召集；门户只读展示蓝本。

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
import re
import shutil
import socket
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

import yaml

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
from backend.app.runtime.registry import AgentRegistry
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


from _auth import E2E_USERNAME, login_context, login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "王工")
API = login_httpx(BASE)

def publish_agent_manifest(
    agent_id: str,
    mutate: Callable[[dict[str, Any]], None],
) -> dict[str, Any]:
    """Publish a new immutable Registry generation for a test-only manifest change."""
    shadow_root = WORK / f"{agent_id}-shadow-{uuid.uuid4().hex}"
    shadow_root.mkdir()
    with app.state.agent_registry.snapshot_view() as registry_view:
        current_agents = registry_view.list()
        expected_ids = {current["id"] for current in current_agents}
        for current in current_agents:
            current_id = current["id"]
            snapshot = registry_view.package_snapshot(current_id)
            assert snapshot is not None
            with snapshot.materialized(parent=WORK) as frozen_dir:
                shutil.copytree(frozen_dir, shadow_root / current_id)
    package_dir = shadow_root / agent_id
    assert package_dir.is_dir()
    yaml_path = package_dir / "agent.yaml"
    manifest = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    mutate(manifest)
    yaml_path.write_text(
        yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )
    shadow = AgentRegistry(shadow_root, app.state.agent_registry.schema_path)
    shadow.scan()
    assert shadow.errors == []
    assert {current["id"] for current in shadow.list()} == expected_ids
    app.state.agent_registry.adopt(shadow)
    published = app.state.agent_registry.get(agent_id)
    assert published is not None
    return published


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
    check(
        "O7a 无方案时只有文字+附件 Composer，无手工存团队入口",
        page.locator(".composer textarea").count() == 1
        and page.locator('.composer input[type="file"]').count() == 1
        and page.locator(".save-team-btn, .summon-dialog, .schema-form").count() == 0,
    )

    # ── O1：对话生方案 → 界面无手工存模板 → API 夹具回读保真 ────────────────────
    page.locator(".composer textarea, textarea").first.fill("给我组一套接力团队")
    page.keyboard.press("Enter")
    plan_card = page.locator(".plan-card").last
    expect(plan_card).to_be_visible(timeout=15000)
    start_btn = plan_card.get_by_role("button", name="按方案开工", exact=True)
    expect(start_btn).to_be_visible(timeout=8000)
    check(
        "O1a 有方案仍无手工存团队入口（唯一主 CTA=按方案开工）",
        page.locator(".save-team-btn").count() == 0
        and start_btn.count() == 1,
    )
    conv_id = page.url.split("c=")[-1] if "c=" in page.url else ""
    saved = API.post(
        "/api/teams",
        json={"name": "接力验收团队", "conversation_id": conv_id},
    )
    check(
        "O1b 认证 API 夹具已从对话方案生成团队蓝本",
        saved.status_code == 200,
        saved.text[:200],
    )
    saved_team = saved.json() if saved.status_code == 200 else {}
    team_id = saved_team.get("id", "")
    team_read = API.get(f"/api/teams/{team_id}") if team_id else None
    team = team_read.json() if team_read is not None and team_read.status_code == 200 else {}
    check(
        "O1c 按 POST 返回 id 精确回读同一团队蓝本",
        bool(team_id) and team.get("id") == team_id and team.get("name") == "接力验收团队",
        json.dumps(team, ensure_ascii=False)[:200],
    )
    m = team.get("members", [])
    check("O1d 成员/seq/after 保真", len(m) == 2 and m[0]["seq"] == 0 and m[1]["after"] == [0],
          json.dumps(m, ensure_ascii=False)[:200])
    check("O1e 版本快照锁定", all(x.get("agent_version_at_save") == "0.1.0" for x in m))
    page.screenshot(path=str(SHOTS / "1_plan_blueprint_readonly.png"))

    # ── O2：G2 disable → 门户预览置灰 + API 整单 422 零写入 ────────────────
    original_status = (app.state.agent_registry.get("hello_agent") or {}).get("status")
    assert isinstance(original_status, str)
    publish_agent_manifest("hello_agent", lambda manifest: manifest.__setitem__("status", "disabled"))
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
            team_card = page.locator(".team-card").filter(has_text="接力验收团队").first
            expect(team_card).to_be_visible(timeout=4000)
            unready = team_card.locator(".team-unready")
            expect(unready).to_be_visible(timeout=4000)
            team_controls = team_card.locator(
                "button, input, textarea, select, form, [contenteditable]"
            ).count()
            check(
                "O2d 门户只读预览（下线提示+零手工召集/填参控件）",
                "成员已下线" in unready.inner_text()
                and team_controls == 0
                and page.locator(".summon-dialog").count() == 0,
                unready.inner_text(),
            )
        except Exception as exc:  # 红而不崩（批七㊲教训：面缺失时达 FAILED 汇总）
            check("O2d 门户只读预览（下线提示+零手工召集/填参控件）", False, f"面缺失：{exc}")
        page.screenshot(path=str(SHOTS / "2_disabled_preview.png"))
    finally:
        publish_agent_manifest(
            "hello_agent",
            lambda manifest: manifest.__setitem__("status", original_status),
        )

    # ── O2b：G1 卸载 / G3 翻 interactive / G5 席位不对齐 ───────────────────
    app.state.agent_registry.deregister("hello_agent", "b8 e2e G1")
    r = summon(team_id, _TWO)
    check("O2e G1 卸载→422 指名不在注册表", r.status_code == 422 and "不在注册表" in r.text, r.text[:160])
    app.state.agent_registry.scan()

    def make_valid_interactive(manifest: dict[str, Any]) -> None:
        manifest["workflow"]["mode"] = "interactive"
        manifest["tools"] = []

    publish_agent_manifest(
        "hello_agent",
        make_valid_interactive,
    )
    r = summon(team_id, _TWO)
    check("O2f G3 翻 interactive→422", r.status_code == 422 and "interactive" in r.text, r.text[:160])
    app.state.agent_registry.scan()

    r = summon(team_id, [{"seq": 0, "inputs": {"name": "只来一半"}}])
    check("O2g G5 缺席位→422", r.status_code == 422 and "缺席位" in r.text, r.text[:160])

    # ── O4：版本漂移 ────────────────────────────────────────────────────────
    publish_agent_manifest("hello_agent", lambda manifest: manifest.__setitem__("version", "0.2.0"))
    r = summon(team_id, _TWO)
    check("O4a 0.x-minor 漂移→422 指名", r.status_code == 422 and "版本漂移" in r.text, r.text[:200])
    publish_agent_manifest("hello_agent", lambda manifest: manifest.__setitem__("version", "0.1.0"))

    # ── O5：密级不稀释（batch gate 第四路复用）──────────────────────────────
    secret_path = WORK / "uploads" / "secret.txt"
    secret_path.parent.mkdir(parents=True, exist_ok=True)
    secret_path.write_bytes(b"secret")
    conn = app.state.conn_factory()
    try:
        repos.create_file(
            conn, file_id="f_sens_b8", task_id=None, kind="input",
            filename="secret.txt", path=str(secret_path), size_bytes=6,
            sha256=hashlib.sha256(b"secret").hexdigest(), classification="sensitive",
            owner_username=E2E_USERNAME,
        )
    finally:
        conn.close()
    before = task_count()
    r = summon(team_id, [
        {"seq": 0, "inputs": {"name": "a"}, "input_file_ids": ["f_sens_b8"]},
        {"seq": 1, "inputs": {"problem_description": FAULT_PROBLEM}},
    ])
    check("O5a sensitive 材料→整单 422", r.status_code == 422 and "密级准入上限" in r.text, r.text[:200])
    check("O5b 零任务写入", task_count() == before)

    # ── O3b：乱序提交（API 逆 seq 序）→ 依赖边仍正确 + patch warnings ──────
    publish_agent_manifest(  # 顺路验 O4b patch 放行 + warnings
        "hello_agent",
        lambda manifest: manifest.__setitem__("version", "0.1.1"),
    )
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
    publish_agent_manifest("hello_agent", lambda manifest: manifest.__setitem__("version", "0.1.0"))

    # ── O3：治理扰动后新对话的唯一主按钮开工（供 O6 复用）───────────────
    # 旧方案的 Package Snapshot 因 O2/O4 故意发生过漂移，必须 fail-closed；
    # 因此用新用户轮验证当前权威快照下的真实主路，绝不复活旧方案。
    page.goto(BASE + "/")
    expect(page.locator(".guide-page")).to_be_visible(timeout=8000)
    page.locator(".composer textarea").fill("按当前能力继续这套接力任务")
    page.keyboard.press("Enter")
    plan_card = page.locator(".plan-card").last
    expect(plan_card).to_be_visible(timeout=15000)
    start_btn = plan_card.get_by_role("button", name="按方案开工", exact=True)
    expect(start_btn).to_be_visible(timeout=8000)
    run_conv_id = page.url.split("c=")[-1] if "c=" in page.url else ""
    before_conv_tasks = API.get(f"/api/conversations/{run_conv_id}/tasks").json()
    check(
        "O3a 开工前会话零任务，方案卡零填参字段且只有唯一主 CTA",
        before_conv_tasks == []
        and plan_card.locator("input, textarea, select, form, [contenteditable]").count() == 0
        and start_btn.count() == 1,
        json.dumps(before_conv_tasks, ensure_ascii=False)[:200],
    )
    start_btn.click()
    deadline = time.time() + 8
    summoned_tasks: list[dict[str, Any]] = []
    while time.time() < deadline:
        summoned_tasks = API.get(f"/api/conversations/{run_conv_id}/tasks").json()
        if len(summoned_tasks) == 2:
            break
        time.sleep(0.2)
    page.screenshot(path=str(SHOTS / "3_started_from_primary_cta.png"))
    ui_up = next(
        (t for t in summoned_tasks if t.get("agent_id") == "hello_agent"),
        None,
    )
    # ui_down 带 default：tamper 面（b8-after-cut 砍依赖边）下匹配为空须红而不崩，
    # 套件必须到达 FAILED 汇总（干净咬合三条件之三）。
    ui_down = next(
        (t for t in summoned_tasks
         if ui_up is not None
         and t.get("agent_id") == "fault_history_agent"
         and (t.get("depends_on") or []) == [ui_up["id"]]),
        None,
    )
    runner_started.set()
    if ui_up is None or ui_down is None:
        check("O3d 主 CTA 自动编排的两任务与依赖边正确", False, "未找到 hello→fault_history 真实任务链")
        check("O3e resolver 接力至下游 waiting_review（rhr 人签闸）", False, "前置缺失：ui_down 无依赖边")
    else:
        check(
            "O3d 主 CTA 自动编排的两任务、输入与真实依赖边正确",
            len(summoned_tasks) == 2
            and (ui_up.get("inputs") or {}) == {"name": "上游"}
            and (ui_down.get("inputs") or {}) == {"problem_description": FAULT_PROBLEM}
            and ui_up.get("status") == "queued"
            and ui_down.get("status") == "created"
            and ui_down.get("depends_on") == [ui_up["id"]],
            json.dumps(summoned_tasks, ensure_ascii=False)[:400],
        )
        # fault_history rhr=True：接力执行后落 waiting_review（待人签）即为本链收官相
        done = wait_status(ui_down["id"], {"waiting_review", "completed", "failed", "cancelled"}, timeout_s=60.0)
        check("O3e resolver 接力至下游 waiting_review（rhr 人签闸）", done.get("status") == "waiting_review",
              json.dumps({"status": done.get("status"), "err": done.get("error_message")}, ensure_ascii=False)[:250])

    # ── O6：withheld 被动面（GuidePage）——零下载 + 遮蔽标记 + 无编造计数 ──
    # 对 O3 主 CTA 自动编排的上游任务注入 sensitive JSON 产物。
    sens_path = WORK / "task_runs" / ui_up["id"] / "output" / "ev.json"
    sens_path.parent.mkdir(parents=True, exist_ok=True)
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
    # 被动面选 TaskConsole 列表（不拉产物）；TaskDetail 的主动拉取是
    # 用户意图面，不计入被动零下载口径。
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
    page.goto(BASE + f"/tasks/{ui_up['id']}")
    try:
        expect(page.locator(".evidence-withheld")).to_be_visible(timeout=8000)
        check("O6c 依据段遮蔽标记在场", True)
    except Exception as exc:
        check("O6c 依据段遮蔽标记在场", False, str(exc)[:160])
    body_text = page.locator("body").inner_text()
    check("O6d 无编造「依据 N 条」计数", re.search(r"依据\s*\d+\s*条", body_text) is None)
    page.screenshot(path=str(SHOTS / "4_withheld.png"))

    # ── O7 归档后入口消失 ───────────────────────────────────────────────────
    if conv_id:
        API.post(f"/api/conversations/{conv_id}/conclude")
        page.goto(BASE + f"/?c={conv_id}")
        archived_plan = page.locator(".plan-card").last
        expect(archived_plan).to_be_visible(timeout=8000)
        check(
            "O7b 会话归档后无开工、手工存团队/召集或字段控件",
            archived_plan.get_by_role("button", name="按方案开工", exact=True).count() == 0
            and page.locator(".save-team-btn, .summon-dialog, .seat-block, .schema-form").count() == 0
            and archived_plan.locator("input, textarea, select, form, [contenteditable]").count() == 0,
        )
    else:
        check("O7b 会话归档后入口不在场", False, "conv_id 缺失")

    browser.close()

failed = [x for x in results if x[1] is not True]
print(f"\n{'BATCH-H TEAMS ALL GREEN' if not failed else 'BATCH-H TEAMS FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
