"""T1 异步评测队列 + 配额 验收（GH #2 · governance-API 接缝）。

自起后端（tmp 包副本，绝不碰真实 data/agents）+ 直连 HTTP（httpx，非 UI）。
证治理 API 的**异步契约**与**配额门**端到端成立。

覆盖（断言）：
  ①POST /eval-runs 立即返回 202 + run_id + status='queued'——不阻塞至跑完。
    若仍是同步执行，返回态会是 'completed'；queued 即「未阻塞跑批」的铁证。
  ②并发多 POST 全部 202 queued（非拒绝）——替换原 EvalBusy 409 单飞锁。
  ③配额门（quota=2）：对 3 条 queued 连续 claim 三次 → 前两条翻 running、第三
    次被配额挡回 None（超配额排队非拒），HTTP GET 观测「2 running + 1 queued」。
  ④排队最终执行：跑完两条腾出配额 → 第三条被认领并 completed → 全部 completed。
  ⑤单条 run 状态流转 queued→running→completed 端到端可观测（同一 run 三态铁证）。
  ⑥EvalRunner worker 自主轮询：起 run_forever 线程，POST 一条，轮询至 completed
    （SQLite 轮询 worker 全链，无 Redis/Celery——本仓无二者依赖）。

配额→排队 tamper 咬合（破坏→RED）：把 claim_next_queued_eval_run 的
`running >= quota` 配额判断改为恒 False（或删除该早返），③的「第三次 claim=None」
与「HTTP 2 running 1 queued」断言立即 RED。手工咬合记录进提交报告；原子配额门的
单元级 tamper 另见 backend/tests/test_eval_queue.py。

运行（仓根）：
  cd frontend && npm run build && cd ..
  uv run --no-project --with uvicorn --with fastapi --with jsonschema \
    --with pyyaml --with httpx --with python-multipart --with "pydantic>2" \
    python frontend/e2e/eval_queue_acceptance.py
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
from backend.app.governance.eval_worker import EvalRunner
from backend.app.main import create_app
from backend.app.storage import repos

# ── 自起后端：tmp 包副本（governed 变体：审核门 + 三 case 全绿评测集，照抄 m10）──
WORK = Path(tempfile.mkdtemp(prefix="flai_eval_queue_"))
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

for _ in range(50):
    try:
        if httpx.get(BASE + "/api/health", timeout=1).status_code == 200:
            break
    except Exception:
        time.sleep(0.1)
else:
    sys.exit("诚实失败：后端 5s 内未就绪")

from _auth import login_httpx, seed_user  # noqa: E402

seed_user(WORK / "flai_os.db", "队列工程师")
client = login_httpx(BASE)

AGENT = "governed_agent"
EVAL_URL = f"/api/agents/{AGENT}/eval-runs"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


def post_eval() -> httpx.Response:
    return client.post(EVAL_URL, json={})


def get_run(run_id: str) -> dict:
    r = client.get(f"{EVAL_URL}/{run_id}")
    r.raise_for_status()
    return r.json()


def list_runs() -> list[dict]:
    r = client.get(EVAL_URL)
    r.raise_for_status()
    return r.json()


def state_counts() -> dict[str, int]:
    counts: dict[str, int] = {}
    for run in list_runs():
        counts[run["status"]] = counts.get(run["status"], 0) + 1
    return counts


# 直接执行核（worker 未起时手工驱动 claim/execute，全程无 worker 竞争 → 确定性）
def execute(run_id: str) -> dict:
    return eval_runner.execute_eval_run(
        run_id=run_id,
        conn_factory=app.state.conn_factory,
        agent_registry=app.state.agent_registry,
        runtime=app.state.runtime,
        uploads_dir=app.state.uploads_dir,
        task_runs_dir=app.state.task_runs_dir,
    )


def claim(quota: int) -> dict | None:
    conn = app.state.conn_factory()
    try:
        return repos.claim_next_queued_eval_run(conn, quota=quota)
    finally:
        conn.close()


# ── ① POST 立即返回 202 + queued（非阻塞：同步会是 completed）──
t0 = time.time()
r1 = post_eval()
elapsed = time.time() - t0
body1 = r1.json() if r1.headers.get("content-type", "").startswith("application/json") else {}
check("①POST→202", r1.status_code == 202, f"status={r1.status_code}")
check("①返回 run_id", bool(body1.get("id")), f"body={body1}")
check("①返回 status='queued'（非阻塞跑批）", body1.get("status") == "queued",
      f"status={body1.get('status')} elapsed={elapsed:.3f}s")
run1 = body1.get("id", "")

# ── ② 并发多 POST 全部 202 queued（非拒绝，替换 EvalBusy 409）──
r2 = post_eval()
r3 = post_eval()
b2, b3 = r2.json(), r3.json()
check("②并发第2次 POST→202 queued（非 409 拒绝）",
      r2.status_code == 202 and b2.get("status") == "queued", f"status={r2.status_code}")
check("②并发第3次 POST→202 queued（非 409 拒绝）",
      r3.status_code == 202 and b3.get("status") == "queued", f"status={r3.status_code}")
run2, run3 = b2.get("id", ""), b3.get("id", "")
check("②三条 run 各异且均 queued", len({run1, run2, run3}) == 3 and state_counts().get("queued") == 3,
      f"counts={state_counts()}")

# ── ③ 配额门 quota=2：claim×3 → 2 认领 + 第3次挡回 None（超配额排队非拒）──
c1 = claim(2)
c2 = claim(2)
c3 = claim(2)
check("③claim①认领成功（queued→running）", c1 is not None and c1.get("status") == "running",
      f"c1={c1 and c1.get('status')}")
check("③claim②认领成功（queued→running）", c2 is not None and c2.get("status") == "running",
      f"c2={c2 and c2.get('status')}")
check("③claim③被配额门挡回 None（超配额排队非拒绝）", c3 is None, f"c3={c3}")
counts3 = state_counts()
check("③HTTP GET 观测：2 running + 1 queued",
      counts3.get("running") == 2 and counts3.get("queued") == 1, f"counts={counts3}")
first_claimed = (c1 or {}).get("id", "")

# ── ⑤ 单条 run 三态流转 queued→running→completed 端到端（追踪 first_claimed）──
#    queued：② 已断言全部 queued；running：③ claim 后此刻为 running；completed：④ 执行后。
check("⑤流转态2/3：first_claimed 现为 running", get_run(first_claimed)["status"] == "running",
      f"status={get_run(first_claimed)['status']}")

# ── ④ 排队最终执行：跑完 2 条腾配额 → 第3条被认领并 completed → 全部 completed ──
e1 = execute(c1["id"])
e2 = execute(c2["id"])
check("④已认领两条执行至 completed 且 3/3",
      e1["status"] == "completed" and e1["passed"] == 3 and e1["total"] == 3
      and e2["status"] == "completed", f"e1={e1['status']}/{e1.get('passed')} e2={e2['status']}")
# 配额腾出 → 之前被挡回的第三条现在可认领
c3b = claim(2)
check("④腾出配额后排队的第3条被认领（排队最终执行）",
      c3b is not None and c3b["status"] == "running", f"c3b={c3b and c3b.get('status')}")
e3 = execute(c3b["id"])
check("④第3条执行至 completed 3/3", e3["status"] == "completed" and e3["passed"] == 3,
      f"e3={e3['status']}/{e3.get('passed')}")
counts4 = state_counts()
check("④全部 3 条 completed（队列排空）",
      counts4.get("completed") == 3 and "queued" not in counts4 and "running" not in counts4,
      f"counts={counts4}")

check("⑤流转态3/3：first_claimed 现为 completed", get_run(first_claimed)["status"] == "completed",
      f"status={get_run(first_claimed)['status']}")

# ── ⑥ EvalRunner worker 自主轮询：起 run_forever，POST 一条，轮询至 completed ──
worker = EvalRunner(
    agent_registry=app.state.agent_registry,
    runtime=app.state.runtime,
    conn_factory=app.state.conn_factory,
    uploads_dir=app.state.uploads_dir,
    task_runs_dir=app.state.task_runs_dir,
    quota=2,
    poll_interval=0.05,
)
threading.Thread(target=worker.run_forever, daemon=True).start()
r4 = post_eval()
b4 = r4.json()
check("⑥POST→202 queued（worker 起后仍异步入队）",
      r4.status_code == 202 and b4.get("status") == "queued", f"status={r4.status_code}")
run4 = b4.get("id", "")
deadline = time.time() + 30
final4 = {}
while time.time() < deadline:
    final4 = get_run(run4)
    if final4["status"] not in ("queued", "running"):
        break
    time.sleep(0.1)
check("⑥worker 自主认领并驱动至 completed 3/3（SQLite 轮询 worker 端到端）",
      final4.get("status") == "completed" and final4.get("passed") == 3 and final4.get("total") == 3,
      f"final={final4.get('status')}/{final4.get('passed')}")

# ── 结果收口 ──
client.close()
passed = sum(1 for _, ok, _ in results if ok is True)
total = len(results)
print(f"\n===== eval_queue_acceptance: {passed}/{total} =====")
if passed != total:
    print("FAILED:")
    for name, ok, detail in results:
        if ok is not True:
            print(f"  ✗ {name} | {detail}")
    sys.exit(1)
print("ALL GREEN ✓")
