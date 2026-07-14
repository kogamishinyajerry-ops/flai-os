"""T2 不可变快照执行验收（#5 · governance-API 接缝）。

自起后端 + 直连 HTTP（httpx）。证「评的就是晋升的那版」由冻结快照保证而非检测篡改：
enqueue 冻结快照后**删光活磁盘的 eval_cases**，该 run 仍从冻结快照执行出原 3/3——
若读活磁盘会是 0/0（无 case）。

覆盖：
  ①POST eval-run → 202 + queued + 绑定内容派生 snapshot_handle。
  ②GET /eval-runs/{id}/snapshot → 元数据（handle/版本/digest/冻结文件集含 workflow.py
    + agent.yaml + eval_cases/*）。
  ③enqueue 后删光活磁盘 eval_cases（篡改活包）。
  ④手动认领 + 执行该 run → completed 且 total=3/passed=3——读冻结快照非活磁盘
    （活磁盘已无 case，若读活磁盘必 0/0）。
  ⑤同活包二次 enqueue → 同 handle（内容派生去重）；删 case 后再 enqueue → 不同 handle。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with uvicorn --with fastapi --with jsonschema \
    --with pyyaml --with httpx --with python-multipart --with "pydantic>2" \
    python frontend/e2e/eval_snapshot_acceptance.py
"""
from __future__ import annotations

import json
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
if not (DIST / "index.html").is_file():
    sys.exit("诚实失败：frontend/dist 未构建。先执行  cd frontend && npm run build")

import httpx
import uvicorn

from backend.app.governance import eval_runner
from backend.app.main import create_app
from backend.app.storage import repos

WORK = Path(tempfile.mkdtemp(prefix="flai_eval_snap_acc_"))
AGENTS_DIR = WORK / "agents"
AGENTS_DIR.mkdir()
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
                       "inputs": {}, "checks": [{"kind": "status_is", "value": "failed"}]}),
    ("case_003.json", {"case_id": "case_003", "description": "非法类型失败路",
                       "inputs": {"name": 1}, "checks": [{"kind": "status_is", "value": "failed"}]}),
):
    (GOV_CASES / name).write_text(json.dumps(case, ensure_ascii=False, indent=2), encoding="utf-8")

_sock = socket.socket()
_sock.bind(("127.0.0.1", 0))
PORT = _sock.getsockname()[1]
_sock.close()
BASE = f"http://127.0.0.1:{PORT}"

app = create_app(
    agents_dir=AGENTS_DIR, tools_dir=REPO / "tools_impl", contracts_dir=REPO / "contracts",
    db_path=WORK / "flai_os.db", uploads_dir=WORK / "uploads", task_runs_dir=WORK / "task_runs",
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

from _auth import login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "快照工程师")
client = login_httpx(BASE)
AGENT = "governed_agent"
EVAL_URL = f"/api/agents/{AGENT}/eval-runs"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def execute(run_id: str) -> dict:
    return eval_runner.execute_eval_run(
        run_id=run_id, conn_factory=app.state.conn_factory, agent_registry=app.state.agent_registry,
        runtime=app.state.runtime, uploads_dir=app.state.uploads_dir, task_runs_dir=app.state.task_runs_dir,
    )


def claim() -> dict | None:
    conn = app.state.conn_factory()
    try:
        return repos.claim_next_queued_eval_run(conn, quota=2)
    finally:
        conn.close()


# ── ① POST → 202 + queued + snapshot_handle ──
r1 = client.post(EVAL_URL, json={})
b1 = r1.json()
check("①POST→202 queued", r1.status_code == 202 and b1.get("status") == "queued", f"status={r1.status_code}")
run_id = b1.get("id", "")
check("①run 绑定内容派生 snapshot_handle", str(b1.get("snapshot_handle") or "").startswith("snap_"),
      f"handle={b1.get('snapshot_handle')}")

# ── ② GET 快照句柄元数据 ──
rs = client.get(f"{EVAL_URL}/{run_id}/snapshot")
meta = rs.json() if rs.status_code == 200 else {}
frozen = set(meta.get("frozen_files", []))
check("②GET 快照元数据 200", rs.status_code == 200, f"status={rs.status_code}")
check("②冻结文件集含 workflow.py + agent.yaml + eval_cases/*",
      "workflow.py" in frozen and "agent.yaml" in frozen
      and any(f.startswith("eval_cases/") for f in frozen), f"frozen={sorted(frozen)}")
check("②元数据含版本/handle/digest", bool(meta.get("agent_version")) and bool(meta.get("handle"))
      and "eval_cases_digest" in meta, f"meta keys={sorted(meta)}")

# ── ③ enqueue 后删光活磁盘 eval_cases（篡改活包）──
for f in GOV_CASES.glob("*.json"):
    f.unlink()
live_remaining = list(GOV_CASES.glob("*.json"))
check("③活磁盘 eval_cases 已删光", len(live_remaining) == 0, f"remaining={live_remaining}")

# ── ④ 认领 + 执行 → 读冻结快照，仍 3/3（活磁盘已无 case，读活磁盘必 0/0）──
claimed = claim()
check("④认领成功（queued→running）", claimed is not None and claimed["id"] == run_id, f"claimed={claimed and claimed.get('id')}")
run = execute(run_id)
check("④执行读冻结快照 → completed 且 3/3（非活磁盘 0/0）",
      run["status"] == "completed" and run["total"] == 3 and run["passed"] == 3,
      f"status={run['status']} total={run.get('total')} passed={run.get('passed')}")

# ── ⑤ 内容派生：同活包二次 enqueue 同 handle；删 case 后 enqueue 不同 handle ──
conn = app.state.conn_factory()
try:
    # 活包现已删光 case → 冻结出不同内容的快照，handle 必与 ① 不同
    h_after = eval_runner.freeze_eval_snapshot(conn, agent_registry=app.state.agent_registry, agent_id=AGENT)
finally:
    conn.close()
check("⑤删 case 后再冻结 → 不同 handle（内容派生）", h_after != b1.get("snapshot_handle"),
      f"before={b1.get('snapshot_handle')} after={h_after}")

client.close()
passed = sum(1 for _, ok, _ in results if ok is True)
total = len(results)
print(f"\n===== eval_snapshot_acceptance: {passed}/{total} =====")
if passed != total:
    print("FAILED:")
    for name, ok, detail in results:
        if ok is not True:
            print(f"  ✗ {name} | {detail}")
    sys.exit(1)
print("ALL GREEN ✓")
