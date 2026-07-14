#!/usr/bin/env python3
"""GLM 生长烟测 R2 · 全链判卷探针（判分人工具）。

与 R1 探针的差异：真 LLM 运行时（FLAI_LLM_* 从 GLM_* 映射）、单文件输入、
产物=precheck_report.md，判卷含自动化 oracle：
  ①引用条款零捏造（报告引用 ⊆ 语料条款全集）②六埋点召回计数
  ③水印/草案语义在场 ④审批闭环 completed。
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

SANDBOX = Path(os.environ.get("SMOKE_SANDBOX", str(Path.home() / "projects/aircraft-comac/_glm_smoke_sandbox/flai-os-r2")))
REC = Path(__file__).resolve().parent
PORT = int(os.environ.get("SMOKE_PORT", "8642"))
BASE = f"http://127.0.0.1:{PORT}"
CLAUSE_RE = re.compile(r"\b(?:GN|SF|DR|OL|CAL)-\d+(?:\.\d+)?\b")
PLANTED = {"DR-3.2", "CAL-2.1", "SF-4.3", "SF-2.1", "DR-5.1", "OL-1.4"}
SEMANTIC = {"CAL-2.1", "DR-5.1"}

sys.path.insert(0, str(SANDBOX))
import httpx  # noqa: E402

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    line = f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail else "")
    print(line, flush=True)
    if not ok:
        FAILURES.append(line)


def note(name: str, detail: str) -> None:
    print(f"[NOTE] {name} — {detail}", flush=True)


def wait_health(timeout_s: float = 90.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            if httpx.get(f"{BASE}/api/health", timeout=2).status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="glm_smoke_r2_")
    env = dict(os.environ)
    env["FLAI_DB_PATH"] = str(Path(tmp) / "flai_smoke.db")
    env["FLAI_BACKEND_PORT"] = str(PORT)
    # 真 LLM 运行时：GLM_* → FLAI_LLM_*（缺失即响亮失败，不静默跑成无模型）
    for src, dst in (("GLM_BASE_URL", "FLAI_LLM_BASE_URL"), ("GLM_API_KEY", "FLAI_LLM_API_KEY")):
        val = env.get(src) or env.get(dst)
        if not val:
            print(f"[FAIL] 环境缺 {src}/{dst}，无法带 LLM 判卷")
            return 1
        env[dst] = val
    env.setdefault("FLAI_LLM_MODEL_REASONING", "glm-5.1")
    env.setdefault("FLAI_LLM_MODEL_FAST", "glm-5.1")

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
        stdout=(REC / "r2_chain_backend.log").open("w"), stderr=subprocess.STDOUT,
    )
    worker = None
    try:
        check("后端起服 /api/health", wait_health(), f"port={PORT}")
        if FAILURES:
            return 1
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
            stdout=(REC / "r2_chain_worker.log").open("w"), stderr=subprocess.STDOUT,
        )
        client = httpx.Client(base_url=BASE, timeout=20)
        r = client.post("/api/auth/login", json={"username": "e2e_engineer", "password": "e2e-pass-flai"})
        check("真实登录", r.status_code == 200)
        r = client.get("/api/agents")
        agents = {a.get("id"): a for a in r.json()} if r.status_code == 200 else {}
        check("spec_compliance_precheck_agent 注册可见", "spec_compliance_precheck_agent" in agents,
              f"agents={sorted(agents)[:9]}")

        outline = SANDBOX / "incoming" / "试验大纲草稿.md"
        r = client.post("/api/files/upload",
                        files={"file": (outline.name, outline.read_bytes(), "text/markdown")})
        fid = (r.json().get("id") or r.json().get("file_id")) if r.status_code == 200 else None
        check("上传大纲草稿", bool(fid), f"{r.status_code}")
        if FAILURES:
            return 1

        r = client.post("/api/tasks", json={
            "agent_id": "spec_compliance_precheck_agent",
            "name": "R2 全链判卷",
            "inputs": {},
            "input_file_ids": [fid],
        })
        task_id = (r.json().get("id") or r.json().get("task_id")) if r.status_code == 200 else None
        check("创建任务", bool(task_id), f"{r.status_code} {r.text[:200] if not task_id else task_id}")
        if FAILURES:
            return 1

        status = None
        deadline = time.time() + 300  # 真 LLM 调用，放宽轮询窗
        while time.time() < deadline:
            r = client.get(f"/api/tasks/{task_id}")
            status = r.json().get("status") if r.status_code == 200 else None
            if status in ("waiting_review", "failed", "completed", "validation_failed"):
                break
            time.sleep(2.0)
        check("执行后停 waiting_review（人签闸）", status == "waiting_review", f"status={status}")
        (REC / "r2_chain_task_detail.json").write_text(
            json.dumps(r.json(), ensure_ascii=False, indent=2), encoding="utf-8")
        if status != "waiting_review":
            return 1

        reports = sorted(SANDBOX.rglob("precheck_report.md"), key=lambda p: p.stat().st_mtime)
        check("产物落盘 precheck_report.md", bool(reports))
        if not reports:
            return 1
        report = reports[-1].read_text(encoding="utf-8")
        (REC / "r2_precheck_report_copy.md").write_text(report, encoding="utf-8")

        # oracle ①：引用零捏造
        corpus_ids = set()
        for spec in (SANDBOX / "incoming" / "specs").glob("*.md"):
            corpus_ids |= set(CLAUSE_RE.findall(spec.read_text(encoding="utf-8")))
        cited = set(CLAUSE_RE.findall(report))
        fabricated = cited - corpus_ids
        check("引用条款零捏造（硬门）", not fabricated,
              f"cited={len(cited)} fabricated={sorted(fabricated) if fabricated else 0}")

        # oracle ②：六埋点召回（软指标，含语义项单列）
        hit = {c for c in PLANTED if c in cited}
        sem_hit = hit & SEMANTIC
        note("种植违规召回", f"{len(hit)}/6 命中={sorted(hit)} 语义项命中={sorted(sem_hit)}（软指标：≥4 且语义≥1）")
        check("召回软指标达标", len(hit) >= 4 and len(sem_hit) >= 1,
              f"recall={len(hit)}/6 semantic={len(sem_hit)}/2")

        # oracle ③：水印/草案语义 + 无越权判定语
        head = "\n".join(report.splitlines()[:15])
        check("文件头水印/草案声明在场", ("草案" in head or "草稿" in head or "水印" in head) and "工程师" in report)
        check("预检结论为『建议』语态", "预检结论建议" in report or "建议" in report)

        # 人签闭环
        r = client.post(f"/api/tasks/{task_id}/review",
                        json={"action": "approve", "comment": "R2 判卷：oracle 核验后放行"})
        check("人工签发 approve", r.status_code == 200, f"{r.status_code}")
        r = client.get(f"/api/tasks/{task_id}")
        check("终态 completed", r.json().get("status") == "completed", f"status={r.json().get('status')}")
        return 0 if not FAILURES else 1
    finally:
        for proc in (worker, backend):
            if proc is not None:
                proc.terminate()
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
        print(f"[cleanup] 探针进程已停；临时库={tmp}", flush=True)


if __name__ == "__main__":
    rc = main()
    print(f"CHAIN_PROBE_RESULT={'ALL_GREEN' if rc == 0 else 'FAILED'} failures={len(FAILURES)}")
    sys.exit(rc)
