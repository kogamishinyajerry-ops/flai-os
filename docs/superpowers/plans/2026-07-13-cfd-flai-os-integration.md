# CFD 真接线 FLAi-OS 工作台 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把一次真实圆柱绕流 Re=100 的 OpenFOAM 求解接线成 FLAi-OS 工作台里两阶段（求解+评估）多 agent、可实时监控、人工签发的端到端流程，不重写任何现有系统。

**Architecture:** sim-live-hub 加一个 native adapter（`cfd_openfoam`）只读 agent-cfd-live 的 `case/run` 流式产物 → FLAi-OS 监控浮窗实时显示残差/Cl/Cd；FLAi-OS 加 2 Tool（`cfd_solve_launch` docker exec 发起真求解 / `cfd_result_read` 只读结果）+ 2 Agent（`cfd_solve_agent` fire-and-register / `cfd_evaluate_agent` 确定性算 St 对照 Williamson + LLM 叙事草案 + 人签）。agent-cfd-live 零改动·只读。

**Tech Stack:** Python 3.10+ / FastAPI / SQLite / pytest / jsonschema；OpenFOAM v11（`cfd-openfoam-live` docker 容器，bind-mount case/run）；sim-live-hub 纯 stdlib adapter；真 GLM（glm-5.1，reasoning profile）仅评估叙事。

**Spec:** `docs/superpowers/specs/2026-07-13-cfd-flai-os-integration-design.md`

## Global Constraints

- **安全边界命中即审**：`cfd_solve_launch` 是 `allow_shell_command=true` → 落地前必过 Codex 异源审（`codex review`）。
- **bind-mount 铁律**：清 `case/run` 只清**内容**，绝不 `rm -rf` 目录本体（VirtioFS inode 悬空，实测 P1）。用 `find <dir> -mindepth 1 -delete` 或等价，绝不 `rm -rf <dir>` / `rmdir <dir>`。
- **fail-closed 恒定**：容器未 up / `FLAI_CFD_*` 未配 / mesh 失败 / run_id 不符 → 抛错/返回 failed，**绝不谎报成功、绝不猜路径、绝不编造数字**。
- **shell=False**：所有 `subprocess.run` 用参数列表，容器名/路径来自可信 env config 非请求体，`case` 走白名单枚举，docker 脚本为固定模板零用户串拼。
- **诚实地板**：评估 St/Cd 一律**确定性计算**（纯 Python），LLM 只叙事；草案强制水印「AI 辅助 · 未经工程师确认 · 判定权在人」；未收敛/数据不足如实报缺，**绝不反向拟合逼近 st_ref=0.164**（Goodhart 防御）。
- **agent-cfd-live 神圣**：全程只读其 `case/run` / `case/template`，零写入零改文件。
- **成熟度**：两 agent 均 `status: draft` / `maturity: L0`；L0→L1 晋升是 M10 治理步，本计划不代拍。
- **跑测口径（FLAi-OS）**：`uv run --no-project --with pytest --with jsonschema --with pyyaml --with fastapi --with httpx --with python-multipart --with openpyxl --with jieba --with "pydantic>2" python -m pytest -q`
- **跑测口径（sim-live-hub）**：`.venv/bin/python -m pytest -q`（必须在仓根跑，namespace package 对 cwd 敏感）
- **并发纪律**：两仓可能有其他 lane 在飞——只按显式路径 `git add`，commit 前 `git diff --cached --name-only` 反查零泄漏，Read-before-Edit 取最新态。

---

## 文件结构（改动落点）

**sim-live-hub**（`~/projects/sim-live-hub`）：
- Create `adapters/cfd_openfoam/module.json` — native 模块契约（只读 CFD run）
- Create `adapters/cfd_openfoam/parser.py` — `collect(run_dir, contract)` 读残差+Cl/Cd
- Create `adapters/cfd_openfoam/cfd_log_parser.py` — log.pimpleFoam 残差 + forceCoeffs Cl/Cd 解析（数值行为复刻 agent-cfd-live/server/parsers.py，golden 对账）
- Modify `server/config.json` — 增 `cfd_openfoam.watch_dir`（指向 agent-cfd-live case/run 的宿主绝对路径）
- Create `tests/test_cfd_openfoam_adapter.py` — parser golden + 停滞
- Create `tests/fixtures/cfd_good_run/` — 从 agent-cfd-live good-run 拷入的只读 golden（log.pimpleFoam + forceCoeffs dat）

**FLAi-OS**（`~/projects/aircraft-comac/flai-os`）：
- Create `tools_impl/cfd_result_read/{adapter.py,tool.yaml,__init__.py,tests/test_cfd_result_read.py}` — 只读结果 Tool（P2）
- Create `agents/cfd_evaluate_agent/{agent.yaml,workflow.py,prompt.md,input_schema.json,output_schema.json,eval_cases/}` — 评估 Agent（P2）
- Create `backend/app/cfd/st_oracle.py` — 确定性 St/Cd 计算（纯函数，被评估 workflow 与测试共用）
- Create `tools_impl/cfd_solve_launch/{adapter.py,tool.yaml,__init__.py,tests/test_cfd_solve_launch.py}` — 求解发起 Tool（P3，安全边界）
- Create `agents/cfd_solve_agent/{agent.yaml,workflow.py,input_schema.json,output_schema.json,eval_cases/}` — 求解 Agent（P3）
- Create `frontend/e2e/cfd_flow_acceptance.py` — 回放夹具全链 E2E（P4）
- Modify `scripts/verify_all.sh` — 纳入新 E2E（P4）
- Modify `docs/adr/` — 新 ADR 记两 Tool/Agent + allow_shell_command 边界（P3/P4）

**agent-cfd-live**：零改动。

---

# Phase P1 — sim-live-hub `cfd_openfoam` native adapter

**产出**：hub 能只读 agent-cfd-live 的 CFD run 目录，流式解析残差+Cl/Cd，浮窗可显示。用 good-run golden 验证，不需容器。

### Task P1.1: CFD 日志解析器（残差 + forceCoeffs）

**Files:**
- Create: `~/projects/sim-live-hub/adapters/cfd_openfoam/__init__.py`（空文件）
- Create: `~/projects/sim-live-hub/adapters/cfd_openfoam/cfd_log_parser.py`
- Create: `~/projects/sim-live-hub/tests/fixtures/cfd_good_run/log.pimpleFoam`（从 agent-cfd-live 拷）
- Create: `~/projects/sim-live-hub/tests/fixtures/cfd_good_run/postProcessing/forceCoeffs1/0/forceCoeffs.dat`（从 agent-cfd-live 拷）
- Test: `~/projects/sim-live-hub/tests/test_cfd_log_parser.py`

**Interfaces:**
- Produces:
  - `parse_residuals(text: str) -> list[dict]` — 每步 `{"t": float, "resid": {"Ux": float, "Uy": float, "p": float}, "clock_s": float|None}`
  - `parse_force_coeffs(text: str) -> dict` — `{"t": list[float], "cd": list[float], "cl": list[float]}`

- [ ] **Step 1: 拷入 golden 真源夹具（只读）**

Run:
```bash
mkdir -p ~/projects/sim-live-hub/tests/fixtures/cfd_good_run/postProcessing/forceCoeffs1/0
cp ~/projects/cfd/agent-cfd-live/case/run/log.pimpleFoam \
   ~/projects/sim-live-hub/tests/fixtures/cfd_good_run/log.pimpleFoam
# forceCoeffs.dat 路径（agent-cfd-live config: postProcessing/forceCoeffs1/0/*.dat）
cp ~/projects/cfd/agent-cfd-live/case/run/postProcessing/forceCoeffs1/0/*.dat \
   ~/projects/sim-live-hub/tests/fixtures/cfd_good_run/postProcessing/forceCoeffs1/0/forceCoeffs.dat
```
Expected: 两文件存在且非空。若 agent-cfd-live case/run 当前无有效 run，先按 spec §9 用 replay bundle（`runbook/replay/good-run-01`）取 log.pimpleFoam + forceCoeffs.dat。

- [ ] **Step 2: 写失败测试**

```python
# tests/test_cfd_log_parser.py
from pathlib import Path
from adapters.cfd_openfoam.cfd_log_parser import parse_residuals, parse_force_coeffs

FIX = Path(__file__).parent / "fixtures" / "cfd_good_run"

def test_parse_residuals_extracts_steps():
    text = FIX.joinpath("log.pimpleFoam").read_text(errors="replace")
    steps = parse_residuals(text)
    assert len(steps) > 10, "应解析出多步时间推进"
    s = steps[-1]
    assert "Ux" in s["resid"] and "p" in s["resid"]
    assert all(v >= 0 for v in s["resid"].values())

def test_parse_force_coeffs_cd_cl():
    text = FIX.joinpath("postProcessing/forceCoeffs1/0/forceCoeffs.dat").read_text(errors="replace")
    fc = parse_force_coeffs(text)
    assert len(fc["t"]) == len(fc["cd"]) == len(fc["cl"]) > 20
    # Re=100 圆柱：Cd_mean 量级 ~1.4（Williamson/agent-cfd-live 实测 1.4009）
    cd_tail = fc["cd"][len(fc["cd"])//2:]
    cd_mean = sum(cd_tail) / len(cd_tail)
    assert 1.0 < cd_mean < 1.8, f"Cd_mean 量级异常：{cd_mean}"
```

- [ ] **Step 3: 跑测确认失败**

Run: `cd ~/projects/sim-live-hub && .venv/bin/python -m pytest tests/test_cfd_log_parser.py -q`
Expected: FAIL（`ModuleNotFoundError: adapters.cfd_openfoam.cfd_log_parser`）

- [ ] **Step 4: 实现解析器（复刻 agent-cfd-live/server/parsers.py 数值行为）**

```python
# adapters/cfd_openfoam/cfd_log_parser.py
"""CFD 日志解析：log.pimpleFoam 残差 + forceCoeffs Cl/Cd。
数值行为复刻 agent-cfd-live/server/parsers.py（跨仓不 import，golden 对账）。"""
from __future__ import annotations
import re

_RESID_RE = re.compile(r"Solving for (\w+), Initial residual = ([0-9.eE+-]+)")
_TIME_RE = re.compile(r"^Time = ([0-9.eE+-]+)")
_CLOCK_RE = re.compile(r"^ExecutionTime = [0-9.eE+-]+ s\s+ClockTime = ([0-9.eE+-]+) s")


def parse_residuals(text: str) -> list[dict]:
    steps: list[dict] = []
    cur: dict | None = None
    for line in text.splitlines():
        m = _TIME_RE.match(line)
        if m:
            if cur is not None:
                steps.append(cur)
            cur = {"t": float(m.group(1)), "resid": {}, "clock_s": None}
            continue
        if cur is None:
            continue
        m = _RESID_RE.search(line)
        if m:
            # 每步每变量取「首次」（Initial residual），同名后续（PIMPLE 内循环）不覆盖首值
            cur["resid"].setdefault(m.group(1), float(m.group(2)))
            continue
        m = _CLOCK_RE.match(line)
        if m:
            cur["clock_s"] = float(m.group(1))
    if cur is not None:
        steps.append(cur)
    return steps


def parse_force_coeffs(text: str) -> dict:
    t: list[float] = []
    cd: list[float] = []
    cl: list[float] = []
    cols: dict | None = None
    for line in text.splitlines():
        low = line.lower()
        if line.startswith("#"):
            if "cd" in low and "cl" in low:
                # header 行：建列名→索引映射（去掉开头 '#'）
                names = low.lstrip("#").split()
                cols = {n: i for i, n in enumerate(names)}
            continue
        vals = line.split()
        if len(vals) < 3:
            continue
        i_cd = cols.get("cd", 2) if cols else 2
        i_cl = cols.get("cl", 3) if cols else 3
        if i_cd >= len(vals) or i_cl >= len(vals):
            continue
        try:
            t.append(float(vals[0]))
            cd.append(float(vals[i_cd]))
            cl.append(float(vals[i_cl]))
        except ValueError:
            continue
    return {"t": t, "cd": cd, "cl": cl}
```

- [ ] **Step 5: 跑测确认通过**

Run: `cd ~/projects/sim-live-hub && .venv/bin/python -m pytest tests/test_cfd_log_parser.py -q`
Expected: PASS（2 passed）。若列映射与真实 forceCoeffs.dat header 不符，按夹具实际 header 调 `parse_force_coeffs` 的列名（`cd`/`cl` 可能是 `Cd`/`Cl` 或带下标——以夹具第一行 `#` header 实际字段名为准，测试即真源）。

- [ ] **Step 6: Commit**

```bash
cd ~/projects/sim-live-hub
git add adapters/cfd_openfoam/__init__.py adapters/cfd_openfoam/cfd_log_parser.py \
        tests/test_cfd_log_parser.py tests/fixtures/cfd_good_run
git commit -m "feat(cfd): CFD 日志解析器（残差+forceCoeffs）+ good-run golden 夹具"
```

### Task P1.2: `collect()` + module.json（native adapter）

**Files:**
- Create: `~/projects/sim-live-hub/adapters/cfd_openfoam/parser.py`
- Create: `~/projects/sim-live-hub/adapters/cfd_openfoam/module.json`
- Test: `~/projects/sim-live-hub/tests/test_cfd_openfoam_adapter.py`

**Interfaces:**
- Consumes: `parse_residuals`, `parse_force_coeffs`（P1.1）
- Produces: `collect(run_dir: Path, contract: dict) -> dict`，返回 `{"curves": {...}, "n_steps": int, "terminal": dict|None, "cd_series": [...], "cl_series": [...]}`

- [ ] **Step 1: 写失败测试**

```python
# tests/test_cfd_openfoam_adapter.py
import json
from pathlib import Path
from adapters.cfd_openfoam.parser import collect

FIX = Path(__file__).parent / "fixtures" / "cfd_good_run"
CONTRACT = json.loads((Path(__file__).parent.parent / "adapters/cfd_openfoam/module.json").read_text())

def test_collect_returns_streaming_curves():
    out = collect(FIX, CONTRACT)
    assert out["n_steps"] > 10
    c = out["curves"]
    assert len(c["t"]) == len(c["resid_p"]) > 10
    assert len(out["cl_series"]) > 20  # 供评估 St 用
    assert len(out["cd_series"]) == len(out["cl_series"])

def test_collect_missing_run_dir_is_empty_not_crash(tmp_path):
    out = collect(tmp_path, CONTRACT)  # 空目录（求解未落地）
    assert out["n_steps"] == 0
    assert out["curves"]["t"] == []
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd ~/projects/sim-live-hub && .venv/bin/python -m pytest tests/test_cfd_openfoam_adapter.py -q`
Expected: FAIL（`ModuleNotFoundError` / `FileNotFoundError` on module.json）

- [ ] **Step 3: 写 module.json（clone fea_ccx 结构，CFD 值）**

以 `adapters/fea_ccx/module.json` 为结构模板，写 `adapters/cfd_openfoam/module.json`，字段取以下**确切值**：
```json
{
  "name": "cfd_openfoam",
  "domain": "cfd-openfoam-cylinder-re100",
  "label": "OpenFOAM · 圆柱绕流 Re=100（agent-cfd-live 求解）",
  "kind": "native",
  "watch_dir_config_key": "cfd_openfoam.watch_dir",
  "stages": [
    {"key": "launch", "label": "发起求解"},
    {"key": "mesh", "label": "网格就绪"},
    {"key": "solve", "label": "pimpleFoam 瞬态求解"},
    {"key": "post", "label": "涡街/力系数"},
    {"key": "done", "label": "完成"}
  ],
  "run_discovery": {
    "fixed_dir": true,
    "marker_file": ".hub_run_id",
    "marker_file_note": "固定单目录（agent-cfd-live case/run），run 身份靠 cfd_solve_launch 盖的 .hub_run_id sidecar 而非时间戳子目录名——本模块与 hub 惯例的唯一偏差，见 spec §6"
  },
  "truth_sources": {
    "write_mode": "streaming",
    "write_mode_note": "pimpleFoam(v11 foamRun) 边求解边追加 log.pimpleFoam（每时间步残差）与 postProcessing/forceCoeffs1/0/*.dat（每步 Cl/Cd）——真实流式，非批处理一次性写",
    "residual_log": "log.pimpleFoam",
    "force_dat_glob": "postProcessing/forceCoeffs1/0/*.dat",
    "curves": [
      {"key": "resid_p", "label": "压力残差 p", "scale": "log"},
      {"key": "cl", "label": "升力系数 Cl", "scale": "linear"},
      {"key": "cd", "label": "阻力系数 Cd", "scale": "linear"}
    ],
    "terminal_marker": "log.pimpleFoam",
    "terminal_marker_note": "log 尾含 'End' 标记 = foamRun 正常收尾"
  },
  "D": 1.0,
  "U": 1.0,
  "st_ref": 0.164,
  "stall_timeout_s": 12,
  "reveal_pace_s": 0
}
```

- [ ] **Step 4: 实现 parser.collect()**

```python
# adapters/cfd_openfoam/parser.py
"""cfd_openfoam adapter：只读 agent-cfd-live 的 CFD run 目录（case/run），
流式解析残差 + Cl/Cd。零写入、零执行；求解未落地时返回空态不崩（诚实）。"""
from __future__ import annotations
from pathlib import Path
import glob
from adapters.cfd_openfoam.cfd_log_parser import parse_residuals, parse_force_coeffs

_EMPTY = {
    "curves": {"t": [], "resid_p": [], "cl": [], "cd": []},
    "n_steps": 0, "cl_series": [], "cd_series": [], "terminal": None,
}


def collect(run_dir: Path, contract: dict) -> dict:
    run_dir = Path(run_dir)
    log_path = run_dir / contract["truth_sources"]["residual_log"]
    if not log_path.exists():
        return {k: (v.copy() if isinstance(v, (list, dict)) else v) for k, v in _EMPTY.items()}
    text = log_path.read_text(errors="replace")
    steps = parse_residuals(text)

    # forceCoeffs（glob 取第一个匹配；无则空序列，不崩）
    fc = {"t": [], "cd": [], "cl": []}
    matches = sorted(glob.glob(str(run_dir / contract["truth_sources"]["force_dat_glob"])))
    if matches:
        fc = parse_force_coeffs(Path(matches[0]).read_text(errors="replace"))

    # 曲线按时间步对齐：残差走 log 的时间步，Cl/Cd 走 forceCoeffs 的时间列（各自真源，前端各自画）
    curves = {
        "t": [s["t"] for s in steps],
        "resid_p": [s["resid"].get("p") for s in steps],
        "cl": fc["cl"],
        "cd": fc["cd"],
    }
    terminal = {"ended": True} if "End" in text[-200:] else None
    return {
        "curves": curves,
        "n_steps": len(steps),
        "cl_series": fc["cl"],
        "cd_series": fc["cd"],
        "terminal": terminal,
    }
```

- [ ] **Step 5: 跑测确认通过**

Run: `cd ~/projects/sim-live-hub && .venv/bin/python -m pytest tests/test_cfd_openfoam_adapter.py -q`
Expected: PASS（2 passed）

- [ ] **Step 6: config 增 watch_dir + 全量回归**

Modify `server/config.json`：增顶层键
```json
"cfd_openfoam": {"watch_dir": "/Users/Zhuanz/projects/cfd/agent-cfd-live/case/run"}
```
Run: `cd ~/projects/sim-live-hub && .venv/bin/python -m pytest -q`
Expected: 全绿（既有测试 + 新 4 条）。若 Collector 装配（server/main.py）对 native 模块强制要求时间戳子目录 run_discovery 而拒 `fixed_dir`，**停下**：这是 spec §6/§11 的已知偏差，按 spec 落法二（hub 侧建指向 case/run 的时间戳 symlink）——但 symlink 在 hub 有安全收紧史（frames 符号链接封堵），需先读 `server/main.py` 的 run_discovery 逻辑再定，不硬改。

- [ ] **Step 7: Commit**

```bash
cd ~/projects/sim-live-hub
git add adapters/cfd_openfoam/parser.py adapters/cfd_openfoam/module.json \
        server/config.json tests/test_cfd_openfoam_adapter.py
git commit -m "feat(cfd): cfd_openfoam native adapter（只读 case/run 流式残差+Cl/Cd）"
```

---

# Phase P2 — FLAi-OS 评估侧（`cfd_result_read` Tool + `st_oracle` + `cfd_evaluate_agent`）

**产出**：给一个 run_id，确定性算 St/Cd 对照 Williamson，LLM 叙事水印草案 → waiting_review。用 P1 的 good-run golden 作夹具，**不需容器**跑通全链。

### Task P2.1: St/Cd 确定性 oracle（纯函数）

**Files:**
- Create: `~/projects/aircraft-comac/flai-os/backend/app/cfd/__init__.py`（空）
- Create: `~/projects/aircraft-comac/flai-os/backend/app/cfd/st_oracle.py`
- Test: `~/projects/aircraft-comac/flai-os/backend/tests/test_st_oracle.py`

**Interfaces:**
- Produces:
  - `strouhal_from_cl(t: list[float], cl: list[float], D: float=1.0, U: float=1.0) -> dict` → `{"st": float|None, "n_cycles": int, "converged": bool, "reason": str}`
  - `cd_mean_tail(cd: list[float], frac: float=0.5) -> float|None`

- [ ] **Step 1: 写失败测试（对 good-run golden 校准到 agent-cfd-live 的 St≈0.167）**

```python
# backend/tests/test_st_oracle.py
from pathlib import Path
import sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO.parent / "sim-live-hub"))  # 复用 hub 解析器读 golden
from backend.app.cfd.st_oracle import strouhal_from_cl, cd_mean_tail

GOLDEN = REPO.parent / "sim-live-hub" / "tests" / "fixtures" / "cfd_good_run" \
         / "postProcessing" / "forceCoeffs1" / "0" / "forceCoeffs.dat"

def _load():
    from adapters.cfd_openfoam.cfd_log_parser import parse_force_coeffs
    fc = parse_force_coeffs(GOLDEN.read_text(errors="replace"))
    return fc["t"], fc["cl"], fc["cd"]

def test_strouhal_matches_williamson_band():
    t, cl, cd = _load()
    r = strouhal_from_cl(t, cl, D=1.0, U=1.0)
    assert r["converged"] is True
    assert r["n_cycles"] >= 3
    # agent-cfd-live 实测 0.16734；容差覆盖 zero-crossing 法与 FFT 法的量级差
    assert 0.15 < r["st"] < 0.185, f"St 偏离量级：{r['st']}"

def test_cd_mean_matches_band():
    t, cl, cd = _load()
    assert 1.0 < cd_mean_tail(cd) < 1.8

def test_flat_cl_not_converged_no_fake_st():
    # 未起振（常值 Cl）→ 不得编造 St（Goodhart 防御）
    r = strouhal_from_cl([0.0, 1.0, 2.0, 3.0], [0.5, 0.5, 0.5, 0.5])
    assert r["converged"] is False
    assert r["st"] is None
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest backend/tests/test_st_oracle.py -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 st_oracle（zero-crossing 法）**

```python
# backend/app/cfd/st_oracle.py
"""确定性 Strouhal / Cd 计算——评估 Agent 的 oracle，纯 Python 无 LLM。
St = f·D/U，f 由 Cl(t) 末段稳定振荡的过零点数估计。未起振/数据不足→
converged=False 且 st=None，绝不编造逼近参考值（Goodhart 防御）。"""
from __future__ import annotations


def cd_mean_tail(cd: list[float], frac: float = 0.5) -> float | None:
    if not cd:
        return None
    tail = cd[max(0, int(len(cd) * (1 - frac))):]
    return sum(tail) / len(tail) if tail else None


def strouhal_from_cl(t: list[float], cl: list[float], D: float = 1.0, U: float = 1.0) -> dict:
    n = len(cl)
    if n < 20 or len(t) != n:
        return {"st": None, "n_cycles": 0, "converged": False,
                "reason": "样本不足（<20 点）或 t/cl 长度不符"}
    # 取末 60% 作稳定段；减去段均值找过零点（正向穿越）
    lo = int(n * 0.4)
    seg_t, seg = t[lo:], cl[lo:]
    mean = sum(seg) / len(seg)
    dev = [v - mean for v in seg]
    amp = (max(dev) - min(dev)) / 2.0
    if amp < 1e-3:
        return {"st": None, "n_cycles": 0, "converged": False,
                "reason": f"Cl 振幅过小（{amp:.2e}）——未起振，不出 St"}
    # 正向过零时刻（线性插值）
    crossings: list[float] = []
    for i in range(1, len(dev)):
        if dev[i - 1] <= 0 < dev[i]:
            frac = -dev[i - 1] / (dev[i] - dev[i - 1])
            crossings.append(seg_t[i - 1] + frac * (seg_t[i] - seg_t[i - 1]))
    n_cycles = len(crossings) - 1
    if n_cycles < 3:
        return {"st": None, "n_cycles": max(0, n_cycles), "converged": False,
                "reason": f"稳定周期不足（{max(0, n_cycles)}<3）"}
    period = (crossings[-1] - crossings[0]) / n_cycles
    if period <= 0:
        return {"st": None, "n_cycles": n_cycles, "converged": False,
                "reason": "周期非正，数据异常"}
    f = 1.0 / period
    return {"st": f * D / U, "n_cycles": n_cycles, "converged": True,
            "reason": f"{n_cycles} 个稳定周期，f={f:.4f}"}
```

- [ ] **Step 4: 跑测确认通过**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest backend/tests/test_st_oracle.py -q`
Expected: PASS（3 passed）。若 St 落在带外，检查 golden forceCoeffs 的时间列单位（agent-cfd-live D=1,U=1，St 应 ~0.167）——**调容差或过零策略，绝不调 golden 逼近 0.164**。

- [ ] **Step 5: Commit**

```bash
cd ~/projects/aircraft-comac/flai-os
git add backend/app/cfd/__init__.py backend/app/cfd/st_oracle.py backend/tests/test_st_oracle.py
git commit -m "feat(cfd): 确定性 St/Cd oracle（zero-crossing，未起振不编造 St）"
```

### Task P2.2: `cfd_result_read` 只读 Tool

**Files:**
- Create: `~/projects/aircraft-comac/flai-os/tools_impl/cfd_result_read/{__init__.py,adapter.py,tool.yaml}`
- Test: `~/projects/aircraft-comac/flai-os/tools_impl/cfd_result_read/tests/test_cfd_result_read.py`

**Interfaces:**
- Consumes: `st_oracle`（P2.1，仅原始序列不下判据——判据在 agent workflow）；env `FLAI_CFD_CASE_DIR`
- Produces: `run(payload: dict, context=None) -> dict`，`payload={"run_id": str}`，返回 `{"status":"success"/"failed","run_id","cl_series","cd_series","resid_p_tail","n_steps","ended", "error_message"?}`

- [ ] **Step 1: 写失败测试（golden 夹具 + run_id 对账 fail-closed）**

```python
# tools_impl/cfd_result_read/tests/test_cfd_result_read.py
import os
from pathlib import Path
from tools_impl.cfd_result_read.adapter import run

FIX = Path(__file__).resolve().parents[4] / "sim-live-hub" / "tests" / "fixtures" / "cfd_good_run"

def _seed_run_id(case_dir: Path, rid: str):
    (case_dir / ".hub_run_id").write_text(rid)

def test_reads_good_run(monkeypatch, tmp_path):
    # 拷 golden 到临时 case_dir + 盖 run_id
    import shutil
    case = tmp_path / "run"; shutil.copytree(FIX, case)
    _seed_run_id(case, "20260713-101010")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(case))
    out = run({"run_id": "20260713-101010"})
    assert out["status"] == "success"
    assert len(out["cl_series"]) > 20

def test_run_id_mismatch_fail_closed(monkeypatch, tmp_path):
    import shutil
    case = tmp_path / "run"; shutil.copytree(FIX, case)
    _seed_run_id(case, "AAA")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(case))
    out = run({"run_id": "BBB"})
    assert out["status"] == "failed"  # 防读错 run

def test_missing_env_fail_closed(monkeypatch):
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    out = run({"run_id": "x"})
    assert out["status"] == "failed"
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest tools_impl/cfd_result_read/tests/ -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 adapter（只读，无 shell）**

```python
# tools_impl/cfd_result_read/adapter.py
"""cfd_result_read（mock=false，只读，无 shell）：读 agent-cfd-live case/run 的
CFD 求解产物（log.pimpleFoam + forceCoeffs），返回原始 Cl/Cd/残差序列。
不下判据（判据在 cfd_evaluate_agent workflow）。run_id 与 .hub_run_id sidecar
不符即 fail-closed（防读错 run）。FLAI_CFD_CASE_DIR 未配即 fail-closed。"""
from __future__ import annotations
import glob
import os
from pathlib import Path
from typing import Any

_CASE_ENV = "FLAI_CFD_CASE_DIR"
_LOG = "log.pimpleFoam"
_FORCE_GLOB = "postProcessing/forceCoeffs1/0/*.dat"


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "error_message": msg}


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    run_id = payload["run_id"]
    case_raw = os.environ.get(_CASE_ENV)
    if not case_raw:
        return _fail(f"{_CASE_ENV} 未配置——fail-closed，绝不猜路径")
    case = Path(case_raw).expanduser()
    sidecar = case / ".hub_run_id"
    if not sidecar.is_file():
        return _fail("run 未发起或 .hub_run_id 缺失——无可读结果")
    actual = sidecar.read_text(errors="replace").strip()
    if actual != str(run_id):
        return _fail(f"run_id 不符（请求 {run_id!r} ≠ 当前 {actual!r}）——防读错 run，fail-closed")
    log_path = case / _LOG
    if not log_path.is_file():
        return _fail("log.pimpleFoam 缺失——求解未产数据")

    # 复用 hub 解析器（同一数值行为 SSOT；测试上下文已把 sim-live-hub 加进 sys.path）
    import sys
    hub = case.parents[2] if False else None  # 生产由部署把 sim-live-hub 置于 sys.path/PYTHONPATH
    from adapters.cfd_openfoam.cfd_log_parser import parse_residuals, parse_force_coeffs

    text = log_path.read_text(errors="replace")
    steps = parse_residuals(text)
    fc = {"t": [], "cd": [], "cl": []}
    matches = sorted(glob.glob(str(case / _FORCE_GLOB)))
    if matches:
        fc = parse_force_coeffs(Path(matches[0]).read_text(errors="replace"))
    return {
        "status": "success",
        "run_id": str(run_id),
        "cl_series": fc["cl"],
        "cd_series": fc["cd"],
        "t_series": fc["t"],
        "resid_p_tail": [s["resid"].get("p") for s in steps[-20:]],
        "n_steps": len(steps),
        "ended": "End" in text[-200:],
    }
```

> **实现注记（P2.2 接缝）**：`from adapters.cfd_openfoam...` 依赖 sim-live-hub 在 `sys.path`。生产部署经 `PYTHONPATH` 或把 hub 解析器作可信共享模块；测试里由 test 头 `sys.path.insert`。**若跨仓 import 在生产不可接受**，退化为把 `cfd_log_parser.py` 的两函数（纯 stdlib、~40 行）复制进 `backend/app/cfd/cfd_log_parser.py` 作 FLAi-OS 侧 SSOT，golden 对账两侧一致。plan 执行时二选一并记 ADR。

- [ ] **Step 4: 写 tool.yaml（clone monitor_adapter_recon 结构）**

以 `tools_impl/monitor_adapter_recon/tool.yaml` 为结构模板，取确切值：`id: cfd_result_read`，`version: 0.1.0`，`type: python_adapter`，`mock: false`，`entrypoint: tools_impl.cfd_result_read.adapter:run`，`output_classification: internal`（通用圆柱算例无敏感），`input_schema` required `[run_id]`（string minLength 1），`output_schema` required `[status]`（enum success/failed，其余宽松透传），`safety: {require_workspace_isolation: false, allow_shell_command: false, save_raw_files: false}`，`runtime: {timeout_seconds: 30, max_parallel_jobs: 2, retry: 0}`。

- [ ] **Step 5: 跑测确认通过**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest tools_impl/cfd_result_read/tests/ -q`
Expected: PASS（3 passed）

- [ ] **Step 6: Commit**

```bash
cd ~/projects/aircraft-comac/flai-os
git add tools_impl/cfd_result_read
git commit -m "feat(cfd): cfd_result_read 只读 Tool（run_id 对账 fail-closed）"
```

### Task P2.3: `cfd_evaluate_agent`（五件套 + 确定性判据 + LLM 叙事水印）

**Files:**
- Create: `~/projects/aircraft-comac/flai-os/agents/cfd_evaluate_agent/{agent.yaml,workflow.py,prompt.md,input_schema.json,output_schema.json}`
- Create: `~/projects/aircraft-comac/flai-os/agents/cfd_evaluate_agent/eval_cases/`（≥1 正常 + 1 未收敛路径）
- Test: `~/projects/aircraft-comac/flai-os/backend/tests/test_cfd_evaluate_agent.py`

**Interfaces:**
- Consumes: `cfd_result_read`（tool_registry.call）、`st_oracle`（P2.1）、`model_gateway.chat`（reasoning）
- Produces: workflow `run(context)->{"status":"success","outputs":[...]}`；artifacts `evaluation.json` + `cfd_eval_draft.md`；`requires_human_review=true`→waiting_review

- [ ] **Step 1: 写 agent.yaml（clone fta_agent 结构，CFD 值）**

以 `agents/fta_agent/agent.yaml` 为结构模板，取确切值：`id: cfd_evaluate_agent`，`version: 0.1.0`，`status: draft`，`maturity: L0`，`category: reasoning_assist`，`summary`「读一次真实 CFD 求解的力系数与残差，确定性算出 Strouhal 数与平均阻力系数并对照 Williamson 参考，出带水印的评估草案交工程师签发」，`model.profile: reasoning`，`knowledge.enabled: false`，`tools: [cfd_result_read]`，`input.schema: input_schema.json`，`output.schema: output_schema.json`，`workflow: {entrypoint: workflow.py, mode: job, requires_human_review: true}`。

- [ ] **Step 2: input/output schema + prompt.md**

`input_schema.json`：`{type:object, required:[run_id], properties:{run_id:{type:string,minLength:1,description:"待评估的 CFD 求解 run_id（= cfd_solve_agent 产出/sim_run_ref 的 run 段）"}}, additionalProperties:false}`
`output_schema.json`：required `[status]`，properties 含 `st/cd_mean/st_ref/st_error_pct/converged/verdict`（宽松）。
`prompt.md`：系统提示——「你只对**已给定的确定性数字**（St、Cd_mean、与 Williamson 0.164 的误差、收敛判据）做工程解读与叙事，绝不自行计算或臆测数字；若判据为未收敛/数据不足，如实说明不可给可信结论。」

- [ ] **Step 3: 写失败测试（golden 全链，stub model_gateway，无容器）**

```python
# backend/tests/test_cfd_evaluate_agent.py
from pathlib import Path
import json, sys
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO.parent / "sim-live-hub"))
from agents.cfd_evaluate_agent.workflow import run as eval_run

class _StubGateway:
    def chat(self, profile, messages):
        return {"content": "涡街稳定，St 与 Williamson 一致，建议采信。", "finish_reason": "stop"}

class _StubToolRegistry:
    """直接返回 good-run golden 的 Cl/Cd（复用 hub 解析器）。"""
    def call(self, tool_id, payload):
        assert tool_id == "cfd_result_read"
        from adapters.cfd_openfoam.cfd_log_parser import parse_force_coeffs
        fx = REPO.parent / "sim-live-hub/tests/fixtures/cfd_good_run/postProcessing/forceCoeffs1/0/forceCoeffs.dat"
        fc = parse_force_coeffs(fx.read_text(errors="replace"))
        return {"status": "success", "run_id": payload["run_id"],
                "cl_series": fc["cl"], "cd_series": fc["cd"], "t_series": fc["t"],
                "resid_p_tail": [1e-6]*20, "n_steps": 200, "ended": True}

class _Logger:
    def log(self, *a, **k): pass

def _ctx(tmp_path):
    return {"inputs": {"run_id": "20260713-101010"}, "files": [], "output_dir": str(tmp_path),
            "event_logger": _Logger(), "tool_registry": _StubToolRegistry(),
            "model_gateway": _StubGateway(), "agent_config": {"model": {"profile": "reasoning"}}}

def test_evaluate_produces_deterministic_st_and_watermarked_draft(tmp_path):
    out = eval_run(_ctx(tmp_path))
    assert out["status"] == "success"
    ev = json.loads((tmp_path / "evaluation.json").read_text())
    assert ev["converged"] is True
    assert 0.15 < ev["st"] < 0.185
    assert ev["st_ref"] == 0.164
    draft = (tmp_path / "cfd_eval_draft.md").read_text()
    assert "AI 辅助" in draft and "判定权在人" in draft  # 强制水印
    # LLM 叙事不得覆盖确定性数字：st 出现在产物且来自 oracle
```

- [ ] **Step 4: 跑测确认失败**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest backend/tests/test_cfd_evaluate_agent.py -q`
Expected: FAIL（workflow 不存在）

- [ ] **Step 5: 实现 workflow.py**

```python
# agents/cfd_evaluate_agent/workflow.py
"""cfd_evaluate_agent：读一次 CFD 求解结果 → 确定性算 St/Cd 对照 Williamson →
LLM(reasoning) 仅叙事这些确定性数字（强制水印草案）→ requires_human_review=true
Runtime 转 waiting_review 等人签。未收敛/数据不足如实报缺，绝不编造 St。"""
from __future__ import annotations
import json, os
from typing import Any
from backend.app.cfd.st_oracle import strouhal_from_cl, cd_mean_tail

_WATERMARK = ("> ⚠ 本文为 AI 辅助生成的 CFD 评估草案，其中**结论数字全部来自确定性计算**"
             "（非 LLM 臆测），叙事由模型辅助；未经工程师确认，不得作为设计/适航依据"
             "（宪法铁律六：判定权在人）。\n")


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": msg}


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    tool_registry = context["tool_registry"]
    output_dir = context["output_dir"]
    run_id = inputs.get("run_id")
    if not run_id:
        return _fail("缺 run_id")

    res = tool_registry.call("cfd_result_read", {"run_id": run_id})
    if res.get("status") != "success":
        return _fail(f"读求解结果失败：{res.get('error_message', '未知')}")

    # ── 确定性判据（唯一数字来源，非 LLM）──
    st = strouhal_from_cl(res.get("t_series") or [], res.get("cl_series") or [], D=1.0, U=1.0)
    cd_mean = cd_mean_tail(res.get("cd_series") or [])
    st_ref = 0.164
    st_error_pct = (abs(st["st"] - st_ref) / st_ref * 100.0) if st["converged"] else None
    verdict = ("收敛，St 与 Williamson 参考一致" if st["converged"] and st_error_pct is not None
               and st_error_pct < 10 else
               ("收敛但 St 偏离参考" if st["converged"] else "未达评估条件（未收敛/数据不足）"))
    evaluation = {
        "run_id": run_id, "converged": st["converged"], "st": st["st"],
        "st_ref": st_ref, "st_error_pct": st_error_pct, "n_cycles": st["n_cycles"],
        "cd_mean": cd_mean, "ended": res.get("ended"), "verdict": verdict,
        "oracle_reason": st["reason"], "source": "cfd_result_read → st_oracle(确定性)",
    }
    with open(os.path.join(output_dir, "evaluation.json"), "w", encoding="utf-8") as f:
        json.dump(evaluation, f, ensure_ascii=False, indent=1)

    # ── LLM 只叙事这些确定性数字（失败/无 key 时降级为模板叙事，不阻断）──
    narrative = ""
    try:
        gw = context.get("model_gateway")
        if gw is not None:
            profile = context["agent_config"]["model"]["profile"]
            facts = json.dumps(evaluation, ensure_ascii=False)
            msgs = [
                {"role": "system", "content": (open(os.path.join(os.path.dirname(__file__), "prompt.md"))
                 .read().strip())},
                {"role": "user", "content": f"对以下确定性评估结果做简短工程解读（不得改动或新增数字）：{facts}"},
            ]
            r = gw.chat(profile, msgs)
            narrative = (r.get("content") or "").strip()
    except Exception as exc:  # noqa: BLE001 - 叙事失败不阻断，确定性判据已落
        narrative = f"（LLM 叙事不可用：{exc.__class__.__name__}；以上确定性数字为准）"

    # ── 水印草案 ──
    lines = ["# CFD 评估草案（圆柱绕流 Re=100）", "", _WATERMARK, "",
             "## 确定性判据", "",
             f"- 收敛：{'是' if evaluation['converged'] else '否'}（{evaluation['oracle_reason']}）",
             f"- Strouhal St：{evaluation['st'] if evaluation['st'] is not None else '—（未收敛，不给数）'}",
             f"- 参考 St_ref（Williamson）：{st_ref}",
             f"- 相对误差：{f'{st_error_pct:.2f}%' if st_error_pct is not None else '—'}",
             f"- 平均阻力系数 Cd_mean：{cd_mean if cd_mean is not None else '—'}",
             f"- 判定：{verdict}", "",
             "## 工程解读（AI 叙事，数字以上为准）", "", narrative or "（无）", ""]
    with open(os.path.join(output_dir, "cfd_eval_draft.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return {"status": "success", "outputs": [{
        "run_id": run_id, "st": evaluation["st"], "cd_mean": cd_mean,
        "converged": evaluation["converged"], "verdict": verdict,
        "artifacts": ["evaluation.json", "cfd_eval_draft.md"],
    }]}
```

- [ ] **Step 6: 跑测 + eval_cases + 契约 parity**

写 `eval_cases/`：case_001（正常 good-run→收敛 St≈0.167）+ case_002（未收敛路径→verdict「未达评估条件」，防假绿）。
Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest --with jsonschema --with pyyaml python -m pytest backend/tests/test_cfd_evaluate_agent.py backend/tests/test_contract_parity.py -q`
Expected: PASS（评估测试 + 契约 parity 认新 agent）

- [ ] **Step 7: Commit**

```bash
cd ~/projects/aircraft-comac/flai-os
git add agents/cfd_evaluate_agent backend/tests/test_cfd_evaluate_agent.py
git commit -m "feat(cfd): cfd_evaluate_agent（确定性 St/Cd + LLM 叙事水印 + 人签）"
```

---

# Phase P3 — FLAi-OS 求解侧（`cfd_solve_launch` Tool + `cfd_solve_agent`）· 安全边界

**产出**：真发起 OpenFOAM 求解（docker exec，fire-and-register），设 sim_run_ref。`cfd_solve_launch` = allow_shell_command → **落地前 Codex 异源审阻塞**。

### Task P3.1: `cfd_solve_launch` Tool（安全边界，docker exec）

**Files:**
- Create: `~/projects/aircraft-comac/flai-os/tools_impl/cfd_solve_launch/{__init__.py,adapter.py,tool.yaml}`
- Test: `~/projects/aircraft-comac/flai-os/tools_impl/cfd_solve_launch/tests/test_cfd_solve_launch.py`

**Interfaces:**
- Consumes: env `FLAI_CFD_CONTAINER`/`FLAI_CFD_CASE_DIR`/`FLAI_CFD_TEMPLATE_DIR`
- Produces: `run(payload, context=None) -> {"status","run_id","run_dir","container","checkmesh_ok","launched_at","error_message"?}`；`payload={"case":"cylinder_re100","end_time"?:float}`

- [ ] **Step 1: 写失败测试（mock subprocess/docker，验安全属性 + fail-closed + bind-mount 铁律）**

```python
# tools_impl/cfd_solve_launch/tests/test_cfd_solve_launch.py
from tools_impl.cfd_solve_launch.adapter import run, _build_reset_argv

def test_config_missing_fail_closed(monkeypatch):
    monkeypatch.delenv("FLAI_CFD_CONTAINER", raising=False)
    out = run({"case": "cylinder_re100"})
    assert out["status"] == "failed"

def test_case_whitelist_only(monkeypatch, tmp_path):
    monkeypatch.setenv("FLAI_CFD_CONTAINER", "cfd-openfoam-live")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))
    monkeypatch.setenv("FLAI_CFD_TEMPLATE_DIR", str(tmp_path))
    out = run({"case": "'; rm -rf /"})  # 注入尝试
    assert out["status"] == "failed"  # 白名单外拒绝

def test_reset_never_deletes_dir_itself():
    # bind-mount 铁律：清内容不删目录本体（VirtioFS inode）
    argv = _build_reset_argv("cfd-openfoam-live", "/home/openfoam/run")
    joined = " ".join(argv)
    assert "-mindepth 1" in joined  # 只清内容
    assert "rm -rf /home/openfoam/run" not in joined
    assert "rmdir" not in joined

def test_shell_false_argv_no_string_concat(monkeypatch, tmp_path):
    # 容器名来自 config；docker 调用是参数列表非 shell 串拼
    import tools_impl.cfd_solve_launch.adapter as mod
    calls = []
    def fake_run(argv, **kw):
        calls.append((argv, kw))
        class R: returncode=0; stdout="ok"; stderr=""
        return R()
    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    monkeypatch.setenv("FLAI_CFD_CONTAINER", "cfd-openfoam-live")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(tmp_path))
    monkeypatch.setenv("FLAI_CFD_TEMPLATE_DIR", str(tmp_path))
    out = run({"case": "cylinder_re100"})
    for argv, kw in calls:
        assert isinstance(argv, list) and argv[0] == "docker"
        assert kw.get("shell", False) is False
    assert out["status"] in ("success", "failed")  # mock 下不真跑，结构成立
```

- [ ] **Step 2: 跑测确认失败**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest tools_impl/cfd_solve_launch/tests/ -q`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 实现 adapter（固定脚本模板，shell=False，fail-closed，铁律守卫）**

```python
# tools_impl/cfd_solve_launch/adapter.py
"""cfd_solve_launch（allow_shell_command=true，安全边界，ADR-0022 同款纪律）：
docker exec 在 cfd-openfoam-live 容器里发起真实 pimpleFoam 求解（fire-and-register，
不阻塞求解 ~200s），盖 run_id sidecar。

红线：① shell=False 参数列表，docker 命令为固定脚本模板零用户串拼；② 容器名/路径
来自可信 env config 非请求体；③ case 白名单枚举；④ 容器未 up / config 缺失 /
mesh 失败 fail-closed，绝不谎报已发起；⑤ bind-mount 铁律：清 run 只清内容绝不删
目录本体（VirtioFS inode 悬空实测 P1）。"""
from __future__ import annotations
import os, subprocess
from typing import Any

_CASE_WHITELIST = {"cylinder_re100"}
_CONTAINER_ENV, _CASE_ENV, _TEMPLATE_ENV = "FLAI_CFD_CONTAINER", "FLAI_CFD_CASE_DIR", "FLAI_CFD_TEMPLATE_DIR"
_CONTAINER_RUN = "/home/openfoam/run"
_OF = "source /opt/openfoam11/etc/bashrc"
_STEP_TIMEOUT = 120  # mesh/check 步；求解本身 nohup & 不等


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "error_message": msg}


def _build_reset_argv(container: str, cdir: str) -> list[str]:
    # bind-mount 铁律：清内容不删目录本体
    return ["docker", "exec", "-w", cdir, container, "bash", "-lc",
            f"find {cdir} -mindepth 1 -delete"]


def _dexec(container: str, cwd: str, script: str) -> subprocess.CompletedProcess:
    return subprocess.run(["docker", "exec", "-w", cwd, container, "bash", "-lc", script],
                          capture_output=True, text=True, timeout=_STEP_TIMEOUT, shell=False)


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    case = payload.get("case")
    if case not in _CASE_WHITELIST:
        return _fail(f"case 非白名单：{case!r}（仅 {_CASE_WHITELIST}）")
    container = os.environ.get(_CONTAINER_ENV)
    case_dir = os.environ.get(_CASE_ENV)
    template_dir = os.environ.get(_TEMPLATE_ENV)
    if not (container and case_dir and template_dir):
        return _fail(f"config 缺失（{_CONTAINER_ENV}/{_CASE_ENV}/{_TEMPLATE_ENV}）——fail-closed")

    # ① 容器可达性
    ping = subprocess.run(["docker", "exec", container, "true"],
                          capture_output=True, text=True, timeout=15, shell=False)
    if ping.returncode != 0:
        return _fail(f"容器 {container} 未就绪：{(ping.stderr or '').strip()[:200]}——绝不谎报已发起")

    # ② 重置（铁律：清内容不删本体）
    r = subprocess.run(_build_reset_argv(container, _CONTAINER_RUN),
                       capture_output=True, text=True, timeout=_STEP_TIMEOUT, shell=False)
    if r.returncode != 0:
        return _fail(f"重置 run 失败：{(r.stderr or '').strip()[:200]}")

    # ③ 铺算例（固定脚本模板；template 内容由部署置于容器可见路径，路径来自 config 非请求体）
    lay = _dexec(container, _CONTAINER_RUN,
                 f"cp -r {template_dir}/. {_CONTAINER_RUN}/ && ls {_CONTAINER_RUN}/cyl2d.msh")
    if lay.returncode != 0:
        return _fail(f"铺算例失败：{(lay.stderr or '').strip()[:200]}")

    # ④ 网格 + 检查（固定序列）
    mesh = _dexec(container, _CONTAINER_RUN,
                  f"{_OF} && gmshToFoam cyl2d.msh && "
                  f"foamDictionary constant/polyMesh/boundary -entry entry0/frontAndBack/type -set empty && "
                  f"checkMesh | tee checkMesh.log")
    checkmesh_ok = mesh.returncode == 0 and "Failed" not in (mesh.stdout or "")
    if not checkmesh_ok:
        return _fail(f"网格/检查失败：{(mesh.stderr or mesh.stdout or '').strip()[-300:]}")

    # ⑤ 可选 end_time（数值型才注入，非法忽略）
    et = payload.get("end_time")
    if isinstance(et, (int, float)) and et > 0:
        _dexec(container, _CONTAINER_RUN, f"{_OF} && foamDictionary system/controlDict -entry endTime -set {float(et)}")

    # ⑥ 发起求解（fire：nohup & 立即返回）+ 盖 run_id sidecar
    #    run_id 由调用侧（agent workflow）传入或此处生成——为避免 Date.now 类不确定性，
    #    run_id 从 payload 取（agent 生成），此处只负责盖 sidecar。
    run_id = str(payload["run_id"])
    launch = _dexec(container, _CONTAINER_RUN,
                    f"{_OF} && nohup pimpleFoam > log.pimpleFoam 2>&1 & "
                    f"echo {run_id} > .hub_run_id")
    if launch.returncode != 0:
        return _fail(f"发起求解失败：{(launch.stderr or '').strip()[:200]}")

    return {"status": "success", "run_id": run_id, "run_dir": case_dir,
            "container": container, "checkmesh_ok": True, "launched_at": run_id}
```

> **run_id 由 agent 传入**（见 P3.2）：Tool 不用 `Date.now`（保测试确定性），agent workflow 生成时间戳 run_id 传进 payload。测试里显式传 `run_id`。

- [ ] **Step 4: 补测试 run_id 传入 + 跑测通过**

在 test 的 mock 调用里给 `payload` 加 `"run_id": "20260713-101010"`；跑测。
Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest python -m pytest tools_impl/cfd_solve_launch/tests/ -q`
Expected: PASS

- [ ] **Step 5: tool.yaml（allow_shell_command=true）**

clone `monitor_adapter_recon/tool.yaml`，确切值：`id: cfd_solve_launch`，`version: 0.1.0`，`mock: false`，`entrypoint: tools_impl.cfd_solve_launch.adapter:run`，`output_classification: internal`，`input_schema` required `[case, run_id]`（case enum `["cylinder_re100"]`；run_id string；end_time number 可选），`output_schema` required `[status]`，`safety: {allow_shell_command: true, require_workspace_isolation: false, save_raw_files: false}`，`runtime: {timeout_seconds: 180, max_parallel_jobs: 1, retry: 0}`。

- [ ] **Step 6: tamper 咬合测试（必红）**

加变异测试：把 `_build_reset_argv` 改成 `rm -rf {cdir}` → `test_reset_never_deletes_dir_itself` 必 RED；把 config 检查改成恒真 → `test_config_missing_fail_closed` 必 RED。记录 tamper witness（存 docs/reviews）。

- [ ] **Step 7: Commit + Codex 异源审（阻塞）**

```bash
cd ~/projects/aircraft-comac/flai-os
git add tools_impl/cfd_solve_launch
git commit -m "feat(cfd): cfd_solve_launch Tool（docker exec 发起真求解，安全边界，铁律守卫）"
codex review --commit HEAD   # allow_shell_command 命中即审，阻塞落地；CHANGES_REQUIRED→修新 commit 再审
```

### Task P3.2: `cfd_solve_agent`（fire-and-register + sim_run_ref）

**Files:**
- Create: `~/projects/aircraft-comac/flai-os/agents/cfd_solve_agent/{agent.yaml,workflow.py,input_schema.json,output_schema.json,eval_cases/}`
- Test: `~/projects/aircraft-comac/flai-os/backend/tests/test_cfd_solve_agent.py`

**Interfaces:**
- Consumes: `cfd_solve_launch`（tool_registry.call）；sim_run_ref 写入机制（见下 Step 决策）
- Produces: workflow `run(context)->{"status":"success","outputs":[{"run_id","sim_run_ref",...}]}`

- [ ] **Step 1: 定位 sim_run_ref 写入接缝（spec §4.3 挂账项）**

Run: `grep -rn "set_task_sim_run_ref\|sim_run_ref\|sim-run-ref" ~/projects/aircraft-comac/flai-os/backend/app/`
判定 workflow 执行上下文是否可写 sim_run_ref：
- 若 context 暴露 repos/task_id 且 runtime 允许 workflow 回写 metadata → workflow 内调 setter。
- 否则 → workflow 只在 output 返回 `sim_run_ref`，由 Runtime/JobRunner 在 agent 完成后回填 task metadata（改动落在 runtime 回填逻辑，需最小 patch + 测试）。
记 ADR，**三条路都不破「人是唯一签发者」**（关联=metadata 标注非状态迁移）。

- [ ] **Step 2: 写失败测试（stub tool_registry，验 run_id 生成 + sim_run_ref 输出）**

```python
# backend/tests/test_cfd_solve_agent.py
from agents.cfd_solve_agent.workflow import run as solve_run

class _StubReg:
    def __init__(self): self.calls = []
    def call(self, tool_id, payload):
        self.calls.append((tool_id, payload))
        assert tool_id == "cfd_solve_launch"
        assert "run_id" in payload and payload["case"] == "cylinder_re100"
        return {"status": "success", "run_id": payload["run_id"], "run_dir": "/x",
                "container": "cfd-openfoam-live", "checkmesh_ok": True, "launched_at": payload["run_id"]}

class _Logger:
    def log(self, *a, **k): pass

def test_solve_fire_and_register(tmp_path):
    reg = _StubReg()
    out = solve_run({"inputs": {"case": "cylinder_re100"}, "files": [],
                     "output_dir": str(tmp_path), "event_logger": _Logger(),
                     "tool_registry": reg, "run_id_seed": "20260713-101010"})
    assert out["status"] == "success"
    o = out["outputs"][0]
    assert o["sim_run_ref"] == "cfd_openfoam@20260713-101010"
    assert "实时监控" in o.get("note", "")

def test_launch_failure_propagates(tmp_path):
    class Bad(_StubReg):
        def call(self, t, p): return {"status": "failed", "error_message": "容器未就绪"}
    out = solve_run({"inputs": {"case": "cylinder_re100"}, "files": [], "output_dir": str(tmp_path),
                     "event_logger": _Logger(), "tool_registry": Bad(), "run_id_seed": "x"})
    assert out["status"] == "failed"
```

- [ ] **Step 3: 跑测确认失败 → 实现 workflow.py**

```python
# agents/cfd_solve_agent/workflow.py
"""cfd_solve_agent（category=tool_automation，零 LLM，fire-and-register）：
经 cfd_solve_launch 发起真实 CFD 求解并登记 run_id → 设 sim_run_ref 让工作台监控
浮窗看活的 → 任务即 completed（求解在容器后台真跑 ~200s，不阻塞）。人看到收敛后
再建 cfd_evaluate_agent 任务（run_id 承接）。requires_human_review=false（发起
动作本身=人建任务的动作；审在评估阶段）。"""
from __future__ import annotations
from typing import Any

_MODULE = "cfd_openfoam"


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "outputs": [], "error_message": msg}


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs") or {}
    reg = context["tool_registry"]
    logger = context.get("event_logger")
    case = inputs.get("case", "cylinder_re100")
    # run_id：确定性来源——测试传 run_id_seed；生产由 Runtime 注入时间戳（不用 Date.now 于纯函数层）
    run_id = context.get("run_id_seed") or context.get("task_id") or "unknown"
    if logger: logger.log("cfd_launch_started", {"case": case, "run_id": run_id})

    res = reg.call("cfd_solve_launch", {"case": case, "run_id": run_id})
    if res.get("status") != "success":
        return _fail(f"发起求解失败：{res.get('error_message', '未知')}")

    sim_run_ref = f"{_MODULE}@{run_id}"
    if logger: logger.log("cfd_launched", {"run_id": run_id, "sim_run_ref": sim_run_ref})
    return {"status": "success", "outputs": [{
        "run_id": run_id, "sim_run_ref": sim_run_ref, "container": res.get("container"),
        "note": "已发起真实 CFD 求解（约200s）——实时监控见工作台监控浮窗/该任务「查看仿真监控↗」深链；"
                "收敛后请创建『CFD 评估』任务（run_id 承接）交工程师签发。",
        "artifacts": [],
    }]}
```

- [ ] **Step 4: agent.yaml + schemas + sim_run_ref 回填接线**

agent.yaml（clone performance_disk_agent 结构）：`id: cfd_solve_agent`，`category: tool_automation`，`model.profile: none`，`tools: [cfd_solve_launch]`，`workflow: {mode: job, requires_human_review: false}`，`status: draft`，`maturity: L0`。
input_schema：`{required:[case], properties:{case:{enum:["cylinder_re100"]}, end_time:{type:number}}}`。
按 Step 1 判定接线 sim_run_ref 回填（workflow 内 setter 或 Runtime 回填），补对应测试。

- [ ] **Step 5: 跑测 + 契约 parity + Commit**

```bash
cd ~/projects/aircraft-comac/flai-os
uv run --no-project --with pytest --with jsonschema --with pyyaml python -m pytest \
  backend/tests/test_cfd_solve_agent.py backend/tests/test_contract_parity.py -q
git add agents/cfd_solve_agent backend/tests/test_cfd_solve_agent.py
git commit -m "feat(cfd): cfd_solve_agent（fire-and-register + sim_run_ref）"
```

---

# Phase P4 — 编排官联调 + E2E + 监控深链

**产出**：编排官能召集两 agent；回放夹具全链 E2E 绿入 verify_all；真求解手动验证；监控浮窗深链可达。

### Task P4.1: 编排官召集两 agent（真 GLM 冒烟）

- [ ] **Step 1: 起服（GLM 映射）** — 见 spec；`export FLAI_LLM_*=$GLM_*`，`FLAI_CFD_CONTAINER/CASE_DIR/TEMPLATE_DIR` 配好，起后端+worker。
- [ ] **Step 2: 编排官冒烟** — 对导引发「跑一个圆柱绕流 CFD 并评估结果」，核实 recommendation 召集 `cfd_solve_agent` + `cfd_evaluate_agent`（真 GLM，可能多轮澄清）。**如实记录**是否一轮出计划。
- [ ] **Step 3: 若 GLM 不召集** — 检查候选面渲染（两 agent status=draft 非 disabled 非 interactive 应在候选）；prompt 无需改（候选由 Registry 生成）。

### Task P4.2: 回放夹具全链 E2E（无容器，入 verify_all）

**Files:**
- Create: `~/projects/aircraft-comac/flai-os/frontend/e2e/cfd_flow_acceptance.py`
- Modify: `~/projects/aircraft-comac/flai-os/scripts/verify_all.sh`

- [ ] **Step 1: 写 E2E（自起后端 + stub gateway + good-run 夹具喂 cfd_result_read）**

clone `frontend/e2e/m9_guide_loop_acceptance.py` 结构（自起后端 + `_auth` 真登录 + DB 夹具）。断言链：
  1. 建协作会话（agent_id=guide_agent）。
  2. 创建 `cfd_evaluate_agent` 任务（inputs.run_id 指向 good-run 夹具；`FLAI_CFD_CASE_DIR` 指夹具，盖 `.hub_run_id`）。
  3. 任务跑 → waiting_review（requires_human_review）。
  4. 产物 `evaluation.json` 含确定性 St（0.15~0.185）+ 水印草案。
  5. `POST /api/tasks/{id}/review {action:approve}` → completed。
> 求解侧（cfd_solve_launch docker exec）E2E 不在 CI 跑（需容器）——用 mock，真求解走 Task P4.3 手动验证。

- [ ] **Step 2: 跑 E2E**

Run: `cd ~/projects/aircraft-comac/flai-os && uv run --no-project --with pytest --with playwright ... python frontend/e2e/cfd_flow_acceptance.py`
Expected: 全链绿。

- [ ] **Step 3: 纳入 verify_all + Commit**

Modify `scripts/verify_all.sh` 加 `cfd_flow_acceptance.py`；Run `bash scripts/verify_all.sh`；Expected 全步绿。
```bash
git add frontend/e2e/cfd_flow_acceptance.py scripts/verify_all.sh
git commit -m "test(cfd): 回放夹具全链 E2E（评估→人签）入 verify_all"
```

### Task P4.3: 真求解端到端手动验证 + 监控深链 + ADR

- [ ] **Step 1: 真求解验证** — 起 sim-live-hub（:8791，config 已配 cfd_openfoam.watch_dir）+ 起容器；经工作台建&提交 `cfd_solve_agent` 任务 → 浮窗 `#/cfd_openfoam@<run_id>` 深链看**实时**残差/Cl/Cd 流式；收敛后建 `cfd_evaluate_agent`（run_id 承接）→ 确定性 St≈0.167 → 人签 → completed。**截图存证**。
- [ ] **Step 2: 诚实核对** — 监控 UI 无「回放」字样（真实时）；评估草案有水印；未收敛路径如实报缺（可 `--kill-after` 中断求解验证停滞报警 + 评估「数据不足」）。
- [ ] **Step 3: ADR + 记录** — 写 `docs/adr/ADR-00XX-cfd-integration.md`（两 Tool/Agent + allow_shell_command 边界 + hub adapter run_dir 偏差落法 + taint=internal）；tamper witness + Codex 审记录存 `docs/reviews/`。Commit。

---

## Self-Review（plan vs spec）

**Spec 覆盖**：§3 三接缝→P1（hub adapter）/P2（评估+read Tool）/P3（求解 Tool+agent）✓；§4 组件契约→各 Task 逐一 ✓；§5 数据流→P4 联调 ✓；§6 run_id/sim_run_ref/hub 偏差→P1.2 Step6 + P3.2 Step1 显式挂 ✓；§7 安全→P3 Codex 审 + 铁律守卫测试 ✓；§8 fail-closed→各 Tool fail-closed 测试 ✓；§9 测试→单元/E2E/tamper 全覆盖 ✓；§10 诚实→水印 + St 不编造测试 ✓。

**Placeholder 扫描**：两处显式「plan 阶段决策」——P1.2 Step6（hub run_discovery `fixed_dir` 兼容）+ P2.2 Step3/P3.2 Step1（跨仓 import / sim_run_ref 回填接缝）——均给了判定路径与退化方案，非空占位。

**类型一致**：`collect(run_dir, contract)`、`run(payload, context)`、`run(context)`、`strouhal_from_cl`/`cd_mean_tail`、`sim_run_ref="cfd_openfoam@<run_id>"`、`.hub_run_id` sidecar 全计划一致。

**风险复述**（spec §11）：hub run_dir 偏差先钉后写；真求解慢走手动验证；St oracle 先测后写、绝不逼近 0.164；跨仓路径全 config 驱动。
