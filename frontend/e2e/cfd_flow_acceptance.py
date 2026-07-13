"""P4.2 CFD 回放夹具全链 E2E（无容器、无真 LLM）：评估→人签。

链路：POST 创建 cfd_evaluate_agent 任务（inputs.run_id 指向 good-run 夹具）→
Job Runner 驱动 workflow 经 cfd_result_read 只读夹具 → 确定性 oracle
（backend.app.cfd.st_oracle）算 St/Cd → requires_human_review=true 落
waiting_review → evaluation.json/cfd_eval_draft.md 落盘（数字来源=oracle，
非 LLM）→ POST /api/tasks/{id}/review {action:approve} → completed。

结构裁决（与原 P4.2 brief 的两处出入，供复核）：
1. brief 步骤①「建协作会话（agent_id=guide_agent）」不落地——create_task 的
   conversation_id 只是可选分组归属（backend/app/api/tasks.py 校验逻辑），
   非任务执行前置；cfd_evaluate_agent 是 workflow.mode=job 的独立评估
   Agent，不经导引协作编排。核心断言链（②-⑤）不依赖会话，故省略，保持
   外科最小。
2. m9_guide_loop_acceptance.py 实际存在（先前误判不存在），但其内容是
   M9 范式 2a 对话轴闭环（guide_agent 多 Agent 协作 UI），与本测试域完全
   不同，不可复用为结构模板。本文件改走 m2_acceptance.py 的非浏览器骨架
   （自起后端 + JobRunner + login_httpx 直连 API）+ m8 的 waiting_review→
   review approve 落点：cfd_evaluate_agent 的输入契约只有 run_id 一个字段，
   断言链条全部是任务生命周期（创建→跑→评审→完成），无需真浏览器/无需
   frontend/dist 构建，更贴合断言意图也更不脆（不依赖未验证的前端选择器）。

自包含：自起后端（tmp DB + tmp task_runs）+ 真实登录（ADR-0019）+ 真实
JobRunner worker 线程 + 回放夹具（backend/tests/fixtures/cfd_good_run/）。
不起 docker 容器、不打真 LLM（stub gateway 顶 app.state.runtime.model_gateway，
workflow 的确定性判据落盘不依赖它——即便不 stub，profile env 未配置时
ModelGateway 也会 fail-fast，workflow 照样把 LLM 叙事失败降级为占位，
不阻断；此处显式 stub 是为了让水印草案里叙事段落非占位文本，覆盖更真实）。

运行（仓根）：
  uv run --no-project --with pytest --with jsonschema --with pyyaml \
    --with fastapi --with httpx --with python-multipart --with openpyxl \
    --with jieba --with "pydantic>2" python frontend/e2e/cfd_flow_acceptance.py
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
from typing import Any

REPO = Path(__file__).resolve().parents[2]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

FIXTURE = REPO / "backend" / "tests" / "fixtures" / "cfd_good_run"
if not (FIXTURE / "log.pimpleFoam").is_file():
    sys.exit(f"诚实失败：回放夹具缺失：{FIXTURE}")

RUN_ID = "20260713-101010"  # 与 tools_impl/cfd_result_read/tests 同款 golden run_id
ST_LO, ST_HI = 0.15, 0.185  # good-run 实测 St≈0.167292（14 周期，见 backend/app/cfd/st_oracle.py 头注）

WORK = Path(tempfile.mkdtemp(prefix="flai_cfd_flow_"))
CASE_ROOT = WORK / "cfd_case"
RUN_DIR = CASE_ROOT / RUN_ID
shutil.copytree(FIXTURE, RUN_DIR)
(RUN_DIR / ".hub_run_id").write_text(RUN_ID, encoding="utf-8")

import os

os.environ["FLAI_CFD_CASE_DIR"] = str(CASE_ROOT)

import httpx
import uvicorn

from backend.app.jobs.runner import JobRunner
from backend.app.main import create_app


class _StubGateway:
    """顶 app.state.runtime.model_gateway：workflow 只拿它做「叙事」，
    数字判据全在 workflow 里的确定性 oracle，与本 stub 无关（宪法铁律六）。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        del profile, messages, kwargs
        return {
            "content": "确定性判据显示收敛，St 与 Williamson 参考基本一致，交工程师复核。",
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
    frontend_dist_dir=WORK / "no_dist",  # 无 index.html：不挂静态路由，纯 API 测试
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

from _auth import login_httpx, seed_user  # noqa: E402（须在后端就绪后种账户）

seed_user(WORK / "flai_os.db", "P4.2验收工程师")
API = login_httpx(BASE)  # 直连 API 的已登录 httpx.Client（ADR-0019 真登录）

app.state.runtime.model_gateway = _StubGateway()

runner = JobRunner(app.state.runtime, app.state.conn_factory, poll_interval=0.2)
threading.Thread(target=runner.run_forever, daemon=True).start()

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    assert ok is True or ok is False, f"gate 断言必须是显式 bool，收到 {ok!r}（{name}）"
    results.append((name, ok, detail))
    print(("PASS" if ok is True else "FAIL"), name, ("| " + detail if detail and ok is not True else ""))


# ── ①创建 cfd_evaluate_agent 任务（inputs.run_id 指向 good-run 夹具）──
resp = API.post("/api/tasks", json={"agent_id": "cfd_evaluate_agent", "inputs": {"run_id": RUN_ID}})
create_ok = resp.status_code == 200
task = resp.json() if create_ok else {}
task_id = task.get("id", "")
check(
    "①创建 cfd_evaluate_agent 任务 → queued",
    create_ok and task.get("status") == "queued" and bool(task_id),
    f"status_code={resp.status_code} body={resp.text[:300]}",
)
if not task_id:
    sys.exit("诚实失败：任务未创建成功，后续断言无意义，直接退出")

# ── ②任务跑 → waiting_review（requires_human_review）──
status = ""
deadline = time.time() + 30
while time.time() < deadline:
    status = API.get(f"/api/tasks/{task_id}").json()["status"]
    if status in ("waiting_review", "failed", "completed"):
        break
    time.sleep(0.3)
check("②任务跑 → waiting_review（requires_human_review）", status == "waiting_review", f"status={status}")

# ── ③产物 evaluation.json 含确定性 St（0.15~0.185）+ converged ──
output_dir = WORK / "task_runs" / task_id / "output"
eval_path = output_dir / "evaluation.json"
eval_ok = eval_path.is_file()
evaluation: dict[str, Any] = json.loads(eval_path.read_text(encoding="utf-8")) if eval_ok else {}
st = evaluation.get("st")
st_in_range = isinstance(st, (int, float)) and (ST_LO < st < ST_HI)
converged_ok = evaluation.get("converged") is True
check(
    "③evaluation.json 落盘 + converged=True + St∈(0.15,0.185)",
    eval_ok and converged_ok and st_in_range,
    f"eval_ok={eval_ok} converged={evaluation.get('converged')} st={st} verdict={evaluation.get('verdict')}",
)

# ── ④水印草案 cfd_eval_draft.md ──
draft_path = output_dir / "cfd_eval_draft.md"
draft_text = draft_path.read_text(encoding="utf-8") if draft_path.is_file() else ""
watermark_ok = "AI 辅助生成的 CFD 评估草案" in draft_text and "判定权在人" in draft_text
check(
    "④cfd_eval_draft.md 落盘 + 强制水印",
    draft_path.is_file() and watermark_ok,
    draft_text[:200],
)

# ── ⑤产物已登记 files 表（output_file_ids 长度=2：evaluation.json + cfd_eval_draft.md）──
task_row = API.get(f"/api/tasks/{task_id}").json()
output_file_ids = task_row.get("output_file_ids")
files_ok = isinstance(output_file_ids, list) and len(output_file_ids) == 2
check("⑤产物已登记 files 表（output_file_ids=2）", files_ok, f"output_file_ids={output_file_ids}")

# ── ⑥POST /api/tasks/{id}/review {action:approve} → completed ──
resp = API.post(f"/api/tasks/{task_id}/review", json={"action": "approve", "comment": "P4.2 E2E 验收：数字核对无误"})
approve_ok = resp.status_code == 200 and resp.json().get("status") == "completed"
check("⑥POST /review approve → completed", approve_ok, f"status_code={resp.status_code} body={resp.text[:300]}")

# ── ⑦事件时间轴含关键节点（无事件=没发生）──
events = API.get(f"/api/tasks/{task_id}/events").json()
event_types = [e.get("event_type") for e in events]
events_ok = all(t in event_types for t in ("task_created", "tool_started", "tool_finished", "review_approved"))
check(
    "⑦事件时间轴含 task_created/tool_started/tool_finished/review_approved",
    events_ok,
    f"event_types={event_types}",
)

failed = [r for r in results if r[1] is not True]
print(f"\n{'CFD FLOW ACCEPTANCE ALL GREEN' if not failed else 'CFD FLOW ACCEPTANCE FAILED'} ({len(results) - len(failed)}/{len(results)})")
sys.exit(0 if not failed else 1)
