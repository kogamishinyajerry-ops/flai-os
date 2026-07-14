#!/usr/bin/env python3
"""GLM 生长烟测 R1 · 全链判卷探针（判分人工具，非被试产物）。

验证 spec 合格产出 #4：起服 → 真实登录 → 上传两 CSV → 创建任务 →
worker 执行 → waiting_review → 产物数值对 oracle → 人签 approve → completed。
被试（GLM）只给了验收步骤没真跑全链；本探针替"提需求的同事"走完它。

判分 oracle（gen_data.py 落盘字节重算）：
  CH1 over=0 under=0 / CH2 over=7 / CH3 over=0 / CH4 under=4
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SANDBOX = Path(os.environ.get("SMOKE_SANDBOX", str(Path.home() / "projects/aircraft-comac/_glm_smoke_sandbox/flai-os")))
REC = Path(__file__).resolve().parent
PORT = int(os.environ.get("SMOKE_PORT", "8641"))
BASE = f"http://127.0.0.1:{PORT}"
ORACLE_OVER = {"CH1": 0, "CH2": 7, "CH3": 0, "CH4": 4}  # over+under 合并计超限次数

sys.path.insert(0, str(SANDBOX))
import httpx  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    line = f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else "")
    print(line, flush=True)
    if not ok:
        FAILURES.append(line)


def wait_health(timeout_s: float = 60.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            r = httpx.get(f"{BASE}/api/health", timeout=2)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="glm_smoke_chain_")
    env = dict(os.environ)
    env["FLAI_DB_PATH"] = str(Path(tmp) / "flai_smoke.db")
    env["FLAI_BACKEND_PORT"] = str(PORT)
    env.pop("FLAI_LLM_API_KEY", None)  # profile:none 全链不需要 LLM——顺带证明零 LLM 依赖
    env.pop("FLAI_LLM_BASE_URL", None)

    uv_base = [
        "uv", "run", "--no-project",
        "--with", "fastapi", "--with", "uvicorn", "--with", "jsonschema",
        "--with", "pyyaml", "--with", "python-multipart", "--with", "httpx",
        "--with", "openpyxl", "--with", "jieba", "--with", "pydantic>2",
    ]
    backend = subprocess.Popen(
        uv_base + ["python", "-m", "uvicorn", "backend.app.main:app",
                   "--host", "127.0.0.1", "--port", str(PORT)],
        cwd=SANDBOX, env=env,
        stdout=(REC / "r1_chain_backend.log").open("w"),
        stderr=subprocess.STDOUT,
    )
    worker = None
    try:
        check("后端起服 /api/health", wait_health(), f"port={PORT} db={env['FLAI_DB_PATH']}")
        if FAILURES:
            return 1

        # 种账户（平台 e2e 同款 F6 纪律：种账户后走真实登录）
        seed = subprocess.run(
            uv_base + ["python", "-c",
                       "import sys; sys.path.insert(0,'.');"
                       "from frontend.e2e._auth import seed_user;"
                       f"seed_user(r'{env['FLAI_DB_PATH']}', '判卷工程师')"],
            cwd=SANDBOX, env=env, capture_output=True, text=True, timeout=120,
        )
        check("种判卷账户", seed.returncode == 0, seed.stderr.strip()[-200:] if seed.returncode else "")

        worker = subprocess.Popen(
            uv_base + ["python", "-m", "backend.app.jobs.runner"],
            cwd=SANDBOX, env=env,
            stdout=(REC / "r1_chain_worker.log").open("w"),
            stderr=subprocess.STDOUT,
        )

        client = httpx.Client(base_url=BASE, timeout=15)
        r = client.post("/api/auth/login", json={"username": "e2e_engineer", "password": "e2e-pass-flai"})
        check("真实登录", r.status_code == 200, f"{r.status_code}")

        # Agent 注册可见（GET /api/agents 经登录会话）
        r = client.get("/api/agents")
        agents = {a.get("id"): a for a in r.json()} if r.status_code == 200 else {}
        check("bench_summary_agent 注册可见", "bench_summary_agent" in agents,
              f"agents={sorted(agents)[:8]}")
        meta = agents.get("bench_summary_agent", {})
        check("draft/L0 起点如实", meta.get("status") == "draft" and meta.get("maturity") == "L0",
              f"status={meta.get('status')} maturity={meta.get('maturity')}")

        # 上传两份 CSV
        fids = []
        for name in ("bench_points.csv", "bench_limits.csv"):
            p = SANDBOX / "incoming" / name
            r = client.post("/api/files/upload", files={"file": (name, p.read_bytes(), "text/csv")})
            ok = r.status_code == 200
            fid = None
            if ok:
                body = r.json()
                fid = body.get("id") or body.get("file_id")
            check(f"上传 {name}", ok and bool(fid), f"{r.status_code} id={fid}")
            fids.append(fid)
        if FAILURES:
            return 1

        # 创建任务（inputs 走 GLM 定的抬头契约）
        r = client.post("/api/tasks", json={
            "agent_id": "bench_summary_agent",
            "name": "R1 全链判卷",
            "inputs": {"test_title": "R1 烟测台架样例", "engineer": "判卷工程师",
                       "test_date": "2026-07-13", "test_stage": "合成基线"},
            "input_file_ids": fids,
        })
        ok = r.status_code == 200
        task_id = r.json().get("id") or r.json().get("task_id") if ok else None
        check("创建任务", ok and bool(task_id), f"{r.status_code} {r.text[:160] if not ok else task_id}")
        if FAILURES:
            return 1

        # 轮询到 waiting_review（worker 真执行）
        status = None
        deadline = time.time() + 120
        while time.time() < deadline:
            r = client.get(f"/api/tasks/{task_id}")
            status = r.json().get("status") if r.status_code == 200 else None
            if status in ("waiting_review", "failed", "completed", "validation_failed"):
                break
            time.sleep(1.0)
        check("执行后停 waiting_review（人签闸）", status == "waiting_review", f"status={status}")
        (REC / "r1_chain_task_detail.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2), encoding="utf-8")
        if status != "waiting_review":
            return 1

        # 产物：磁盘 glob（Runtime output_dir 落沙箱 data/ 下）+ 数值对 oracle
        drafts = sorted(SANDBOX.rglob("summary_draft.md"), key=lambda p: p.stat().st_mtime)
        stats_csvs = sorted(SANDBOX.rglob("channel_stats.csv"), key=lambda p: p.stat().st_mtime)
        check("产物落盘 summary_draft.md + channel_stats.csv",
              bool(drafts) and bool(stats_csvs),
              f"draft={drafts[-1] if drafts else None}")
        if drafts and stats_csvs:
            import csv as _csv
            with stats_csvs[-1].open() as f:
                rows = {row["channel"]: row for row in _csv.DictReader(f)}
            all_ok = True
            for ch, want in ORACLE_OVER.items():
                got_raw = rows.get(ch, {}).get("out_of_limit_count", "")
                got = int(got_raw) if str(got_raw).strip().isdigit() else None
                if got != want:
                    all_ok = False
                    check(f"oracle {ch} 超限次数", False, f"want={want} got={got_raw!r}")
            check("产物数值对 oracle（4 通道超限次数全中）", all_ok)
            draft_text = drafts[-1].read_text(encoding="utf-8")
            check("草稿含草稿声明+人签語义", "草稿声明" in draft_text and "签发" in draft_text)
            check("草稿抬头吃进 inputs", "R1 烟测台架样例" in draft_text)

        # 人签 approve → completed（宪法闭环）
        r = client.post(f"/api/tasks/{task_id}/review",
                        json={"action": "approve", "comment": "R1 判卷：产物数值对 oracle 全中，准予通过"})
        check("人工签发 approve", r.status_code == 200, f"{r.status_code} {r.text[:120] if r.status_code != 200 else ''}")
        r = client.get(f"/api/tasks/{task_id}")
        check("终态 completed", r.status_code == 200 and r.json().get("status") == "completed",
              f"status={r.json().get('status')}")
        reviewer = (r.json().get("reviewer") or r.json().get("reviewed_by") or "")
        check("签发记名=会话身份（服务端派生）", "判卷工程师" in str(r.json()) or bool(reviewer),
              f"reviewer={reviewer!r}")
        return 0 if not FAILURES else 1
    finally:
        for proc, name in ((worker, "worker"), (backend, "backend")):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print(f"[cleanup] backend/worker 已停（仅本探针拉起的进程）；临时库={tmp}", flush=True)


if __name__ == "__main__":
    rc = main()
    print(f"CHAIN_PROBE_RESULT={'ALL_GREEN' if rc == 0 else 'FAILED'} failures={len(FAILURES)}")
    sys.exit(rc)
