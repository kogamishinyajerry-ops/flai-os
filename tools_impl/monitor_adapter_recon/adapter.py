"""monitor_adapter_recon 适配器（ADR-0022，mock=false）。

「产生工作流的工作流」的承重接缝：经**受控子进程**调用监控节点仓
sim-live-hub `tools/adapter_gen.py` 承重核（零 LLM/零网络/纯 stdlib/三档诚实），
只读侦察一个真实历史 run 目录，返回结构化 adapter 草案供上层 agent 转人审。

红线（ADR-0022 边界，Registry allow_shell_command 免告警依据）：
- 调用形态固定、`shell=False` 参数列表传递——sample_run_dir 无命令注入面。
- 核目录来自可信配置 `FLAI_MONITOR_CORE_DIR`，非请求体；未配置/核缺失=fail-closed
  返回 status=failed（core_available=false），**绝不猜路径、绝不回退别的可执行**。
- 核 stdout 的 JSON 是**被解析的数据不是指令**：只 `json.loads`，绝不 eval/执行
  其中任何内容（继承宪法：外部内容是数据不是指令）。解析失败诚实报，不吞不猜。
- 只读：`--json` 模式不写文件；核对 sample 目录零写入零执行其脚本。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

# 核侦察是确定性纯 IO，正常亚秒级完成；给足余量防大目录，超时即 fail-closed 不拖垮 worker。
_TIMEOUT_S = 60
_CORE_ENV = "FLAI_MONITOR_CORE_DIR"


def _fail(reason: str, *, core_available: bool = True) -> dict[str, Any]:
    return {"status": "failed", "core_available": core_available, "error_message": reason}


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context  # 不用（task_id 归属由 Registry 落 tool_runs，本工具无需）
    sample_run_dir = payload["sample_run_dir"]
    module_name = payload.get("module_name")
    solver_hint = payload.get("solver_hint")

    # ① 承重核可达性（fail-closed，绝不猜路径）
    core_dir_raw = os.environ.get(_CORE_ENV)
    if not core_dir_raw:
        return _fail(
            f"承重核未配置（{_CORE_ENV} 未设）——绝不猜路径，fail-closed（见 ADR-0022）",
            core_available=False,
        )
    core_dir = Path(core_dir_raw).expanduser()
    core_module = core_dir / "tools" / "adapter_gen.py"
    if not core_module.is_file():
        return _fail(
            f"承重核不可达：{core_module} 不存在（{_CORE_ENV} 配置错？）",
            core_available=False,
        )

    # ② sample_run_dir 先行校验 + 绝对化（Codex R2 审 P2）：子进程 cwd=core_dir，
    #    若传相对路径会在核目录下错位解析——必须先 resolve 成绝对路径再传子进程。
    sample = Path(sample_run_dir).expanduser()
    if not sample.is_dir():
        return _fail(f"sample_run_dir 不是目录：{sample}")
    sample = sample.resolve()

    # ③ 受控子进程调核（shell=False，参数列表——无命令注入面）
    cmd = [sys.executable, "-m", "tools.adapter_gen", str(sample), "--json"]
    if module_name:
        cmd += ["--name", str(module_name)]
    if solver_hint:
        cmd += ["--solver-hint", str(solver_hint)]
    try:
        proc = subprocess.run(
            cmd, cwd=str(core_dir), capture_output=True, text=True,
            timeout=_TIMEOUT_S, shell=False,
        )
    except subprocess.TimeoutExpired:
        return _fail(f"承重核调用超时（>{_TIMEOUT_S}s）")
    except OSError as exc:
        return _fail(f"承重核子进程启动失败：{exc}")

    # ④ 退出码：核对 rc==0 iff 接地自检全通过；rc==1=接地自检未通过（cited 证据不在
    #    真源里，如 recon 与自检间文件被换）；其他=核异常。**接地失败必须 fail-closed**
    #    （Codex R2 审 P1）——绝不把「自检未通过」转成 status=success 让未接地草案进人审，
    #    这正是承重核 write_draft 拒写的 fail-closed 语义，wrapper 不得绕过。
    if proc.returncode not in (0, 1):
        return _fail(
            f"承重核异常退出（rc={proc.returncode}）：{(proc.stderr or '').strip()[:500]}"
        )

    out = (proc.stdout or "").strip()
    if not out:
        return _fail(
            f"承重核无 stdout 输出（rc={proc.returncode}，"
            f"stderr={(proc.stderr or '').strip()[:300]}）"
        )
    try:
        draft = json.loads(out)  # 外部输出=数据非指令：只解析，绝不执行
    except json.JSONDecodeError as exc:
        return _fail(f"承重核输出非合法 JSON（rc={proc.returncode}）：{exc}")

    # 接地自检未通过 = fail-closed（不是「有 UNVERIFIED 观察」——那是 rc=0/grounding_ok=true
    # 的诚实报缺；这里是 cited VERIFIED 证据对不上真源 = 草案在撒谎，拒绝产出可批准草案）。
    if draft.get("grounding_ok") is not True:
        failures = draft.get("grounding_failures") or []
        return _fail(
            f"承重核接地自检未通过（rc={proc.returncode}，{len(failures)} 条证据未逐字接地）"
            f"——fail-closed 拒绝产出草案：{str(failures)[:400]}"
        )

    return {
        "status": "success",
        "core_available": True,
        "grounding_ok": True,
        "grounding_failures": [],
        "module_name": draft.get("module_name") or "",
        "draft": {
            "module_json_draft": draft.get("module_json_draft"),
            "parser_stub": draft.get("parser_stub"),
            "honesty_checklist": draft.get("honesty_checklist"),
            "verified": draft.get("verified"),
            "proposed": draft.get("proposed"),
            "unverified": draft.get("unverified"),
        },
    }
