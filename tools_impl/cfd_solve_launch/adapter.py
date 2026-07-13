"""cfd_solve_launch（allow_shell_command=true，安全边界，ADR-0022 同款纪律）：
在 case/run/<run_id>/ 时间戳子目录里发起真实 pimpleFoam 求解（fire-and-register，
不阻塞求解 ~200s）。host 侧铺算例（同 agent-cfd-live staging 方式），docker exec
只跑 OpenFOAM 命令（bind-mount 使子目录两侧可见，2026-07-13 探针实测：
host case/run → 容器 /home/openfoam/run）。

红线：① shell=False 参数列表，docker 命令为固定脚本模板零用户串拼；② 容器名/路径
来自可信 env config 非请求体；③ case 白名单枚举 + run_id 正则白名单（先于任何
路径拼接）；④ 容器未 up / config 缺失 / mesh 失败 fail-closed，绝不谎报已发起
（sidecar 最后盖——失败残留子目录无 sidecar，hub 不认作 run）；⑤ bind-mount
铁律强化版：每 run 新建子目录，本工具**零删除操作**——case/run 本体与旧 run
谁都不碰，同名 run 已存在即拒（防覆写在跑的 run）。
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

_CASE_WHITELIST = {"cylinder_re100"}
_RUN_ID_RE = re.compile(r"^\d{8}-\d{6}$")
_CONTAINER_ENV = "FLAI_CFD_CONTAINER"
_CASE_ENV = "FLAI_CFD_CASE_DIR"
_TEMPLATE_ENV = "FLAI_CFD_TEMPLATE_DIR"
_CONTAINER_RUN_ROOT = "/home/openfoam/run"  # bind-mount 容器侧根（= host 的 case/run，inspect 实测）
_OF = "source /opt/openfoam11/etc/bashrc"  # 容器实测路径；未 source 时 OpenFOAM 命令不在 PATH
_STEP_TIMEOUT = 120  # mesh/check 步；求解本身 nohup & 不等


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "error_message": msg}


def _dexec(container: str, cwd: str, script: str) -> subprocess.CompletedProcess:
    # 固定脚本模板经参数列表传入（shell=False）：唯一进 script 的变量是白名单校验过的
    # run_id（拼 cwd）与数值校验过的 end_time，零用户自由文本。
    return subprocess.run(["docker", "exec", "-w", cwd, container, "bash", "-lc", script],
                          capture_output=True, text=True, timeout=_STEP_TIMEOUT, shell=False)


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    case = payload.get("case")
    if case not in _CASE_WHITELIST:
        return _fail(f"case 非白名单：{case!r}（仅 {sorted(_CASE_WHITELIST)}）")
    run_id = str(payload.get("run_id", ""))
    if not _RUN_ID_RE.match(run_id):
        return _fail(f"run_id 非法（须 YYYYMMDD-HHMMSS）：{run_id!r}——拒绝拼路径，fail-closed")
    container = os.environ.get(_CONTAINER_ENV)
    case_root_raw = os.environ.get(_CASE_ENV)
    template_raw = os.environ.get(_TEMPLATE_ENV)
    if not (container and case_root_raw and template_raw):
        return _fail(f"config 缺失（{_CONTAINER_ENV}/{_CASE_ENV}/{_TEMPLATE_ENV}）——fail-closed，绝不猜路径")
    case_root = Path(case_root_raw).expanduser()
    template = Path(template_raw).expanduser()
    if not case_root.is_dir():
        return _fail(f"case 根不存在：{case_root}")
    if not (template / "cyl2d.msh").is_file():
        return _fail(f"template 缺 cyl2d.msh：{template}")

    # ① 建 run 子目录（host 侧；零删除——已存在即拒，防覆写在跑的 run）
    run_dir = case_root / run_id
    if run_dir.exists():
        return _fail(f"run 子目录已存在：{run_dir}——拒绝覆写，换 run_id")
    ctr_cwd = f"{_CONTAINER_RUN_ROOT}/{run_id}"

    # ② 铺算例（host 侧拷 template：0/ constant/ system/ cyl2d.msh）
    try:
        shutil.copytree(template, run_dir)
    except OSError as exc:
        return _fail(f"铺算例失败：{exc}")

    # ③ 容器可达性（fire 前最后一道；先铺后 ping 使失败残留可诊断，子目录无 sidecar
    #    不会被 hub marker 认作 run）
    ping = subprocess.run(["docker", "exec", container, "true"],
                          capture_output=True, text=True, timeout=15, shell=False)
    if ping.returncode != 0:
        return _fail(f"容器 {container} 未就绪：{(ping.stderr or '').strip()[:200]}——绝不谎报已发起")

    # ④ 网格 + 检查（固定脚本模板，cwd=子目录）
    mesh = _dexec(container, ctr_cwd,
                  f"{_OF} && gmshToFoam cyl2d.msh && "
                  f"foamDictionary constant/polyMesh/boundary -entry entry0/frontAndBack/type -set empty && "
                  f"checkMesh | tee checkMesh.log")
    if mesh.returncode != 0 or "Failed" in (mesh.stdout or ""):
        return _fail(f"网格/检查失败：{(mesh.stderr or mesh.stdout or '').strip()[-300:]}")

    # ⑤ 可选 end_time（数值型才注入，非法忽略——零自由文本进脚本）
    et = payload.get("end_time")
    if isinstance(et, (int, float)) and not isinstance(et, bool) and et > 0:
        _dexec(container, ctr_cwd,
               f"{_OF} && foamDictionary system/controlDict -entry endTime -set {float(et)}")

    # ⑥ 发起求解（fire：nohup & 立即返回，不等 ~200s）
    launch = _dexec(container, ctr_cwd, f"{_OF} && nohup pimpleFoam > log.pimpleFoam 2>&1 &")
    if launch.returncode != 0:
        return _fail(f"发起求解失败：{(launch.stderr or '').strip()[:200]}")

    # ⑦ 盖 sidecar（host 侧，最后一步=hub marker：sidecar 在场即「这是一个已发起的 run」）
    (run_dir / ".hub_run_id").write_text(run_id, encoding="utf-8")

    return {"status": "success", "run_id": run_id, "run_dir": str(run_dir),
            "container": container, "checkmesh_ok": True, "launched_at": run_id}
