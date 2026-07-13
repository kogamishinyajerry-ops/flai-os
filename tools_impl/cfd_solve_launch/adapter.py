"""cfd_solve_launch（allow_shell_command=true，安全边界，ADR-0022 同款纪律）：
在 case/run/<run_id>/ 时间戳子目录里发起真实 pimpleFoam 求解（fire-and-register，
不阻塞求解 ~200s）。host 侧铺算例 + 产 mesh（同 agent-cfd-live staging-v2 host
直出方式），docker exec 只跑 OpenFOAM 命令（bind-mount 使子目录两侧可见，
2026-07-13 探针实测：host case/run → 容器 /home/openfoam/run）。

红线：① shell=False 参数列表，docker/gmsh 命令为固定模板零用户串拼；② 容器名/
路径来自可信 env config 非请求体；③ case 白名单枚举 + run_id fullmatch [0-9]
白名单（先于任何路径拼接；Codex R0-P2-2：re.match+$ 会放行尾换行）；④ config
缺失 / 容器未 up / mesh 失败 / checkMesh 无 Mesh OK. / 求解进程未起 一律
fail-closed，绝不谎报已发起（sidecar 最后盖——失败残留子目录无 sidecar，hub
不认作 run）；⑤ bind-mount 铁律强化版：每 run 新建子目录，本工具**零删除操作**
——case/run 本体与旧 run 谁都不碰，同名 run 已存在即拒。

Codex R0 修复（2026-07-13）：
- P1-1 mesh 两条腿：template/cyl2d.msh 在则拷（自备模板）；否则 host gmsh 从
  template/geo/domain_parametric.geo 生成进 run 子目录（canonical 兜底路线，
  rehearse.sh:94 逐字参数）——真实 case/template 不含 msh。两腿全断 fail。
- P1-2 fire 后 pgrep 验证求解进程真在（`… && nohup x &` 整体后台化恒返 0，
  bashrc 缺失/pimpleFoam 不存在也「成功」）；进程不在 → fail 不盖 sidecar。
- P1-3 checkMesh 经 tee 管道吞退出码（无 pipefail）→ 固定脚本加 set -o
  pipefail 且正向断言 stdout 含 Mesh OK.（真实成功 marker，checkMesh.log 实测）。
- P1-4 timeout 预算闭合（见 _T_* 常量注释），worst-case 总和 < tool.yaml
  timeout_seconds=360，杜绝 Registry 已记 failed 而 adapter 线程稍后盖 marker。
- P2-1 end_time 的 foamDictionary 失败即 fail，绝不带错误 endTime 静默开跑。

R1 修复（2026-07-13，真跑取证 + CRS 复审）：
- 真跑 P1（主控取证）：OF11 `pimpleFoam` 是 POSIX sh wrapper，实际求解进程
  comm=**foamRun**（`foamRun -solver incompressibleFluid`，容器实测）——
  `pgrep pimpleFoam` 按 comm 匹配永远扑空 → alive 假阴性：任务误报 failed
  且无 sidecar，求解器却真在跑（孤儿 run 20260713-092338 实证）。修：pgrep
  `-x 'foamRun|pimpleFoam'`（-x 精确全串，容器实测命中 foamRun 且**排除**
  启动壳 bash——其 cmdline 含 pimpleFoam 且 cwd=run 目录，-f 会假阳性）。
- CRS-P2：小 end_time 求解可在探测窗口内正常跑完（非启动失败）→ pgrep 扑空
  后读 log 末行，OpenFOAM 正常收尾 marker `End` 在场即判「已完成」照常盖
  sidecar；无 End 才是启动失败 fail-closed。
- CRS-P2 单并发契约：agent 声明「同一时刻一次求解」但 Registry 不强制
  max_parallel_jobs → 发起前扫容器内活跃求解（同款 pgrep+cwd 对账，cwd 在
  run 根下即算），命中即拒，fail-closed。
- Codex R1-P1-4：end_time 上界 ≤600（canonical controlDict endTime=150 的 4×）
  ——detached 进程无 PID 取消路径，无界 endTime=无界烧 CPU。
- Codex R1-P2-2：run_id 语义校验（strptime 真日期 + 不超前 now+24h）——纯宽度
  pattern 会放行 hour-30/远未来 ID，被 hub newest_by_name 字典序钉死后遮蔽
  后续真 run。单 chokepoint：校验集中本 Tool（公开可调面），workflow 生成的
  时间戳天然合法。
- Codex R1-P1-2（运维红线，代码不可修）：agent-cfd-live scripts/rehearse.sh:78
  会 `rm -rf case/run/*`——与 managed runs 共享该目录（bind-mount 固定，他仓
  零改动铁律）。红线=managed 求解期间勿跑 rehearse.sh；残余风险与缓解记
  ADR-0027 与 cfd_solve_agent/README。
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

_CASE_WHITELIST = {"cylinder_re100"}
_RUN_ID_RE = re.compile(r"[0-9]{8}-[0-9]{6}")  # 用 fullmatch；[0-9] 拒非 ASCII 数字
_CONTAINER_ENV = "FLAI_CFD_CONTAINER"
_CASE_ENV = "FLAI_CFD_CASE_DIR"
_TEMPLATE_ENV = "FLAI_CFD_TEMPLATE_DIR"
_CONTAINER_RUN_ROOT = "/home/openfoam/run"  # bind-mount 容器侧根（= host 的 case/run，inspect 实测）
_OF = "set -o pipefail; source /opt/openfoam11/etc/bashrc"  # 容器实测路径；pipefail 保 tee 不吞退出码
_GEO_REL = "geo/domain_parametric.geo"  # canonical 参数化兜底 geo（rehearse.sh:94）
# OF11 的 pimpleFoam 是 sh wrapper，真进程 comm=foamRun（R1 真跑取证）；-x 精确
# 全串匹配（容器实测：命中 foamRun、排除 cmdline 含 pimpleFoam 的启动壳 bash）。
_SOLVER_PGREP = "foamRun|pimpleFoam"
_END_MARKER = "End"  # OpenFOAM 正常收尾时 log 末行（区分「跑完了」与「没起来」）

# timeout 预算（Codex R0-P1-4）：worst-case 累计 = 15(ping) + 10(busy 扫，R1)
# + 120(gmsh) + 90(mesh) + 20(endTime) + 20(launch) + 3×(10+1)(pgrep 重试)
# ≈ 308s + copytree 秒级 < tool.yaml timeout_seconds=360（含余量）。
# 改任一常量须同步复核该预算。
_T_PING = 15
_T_GMSH = 120
_T_MESH = 90
_T_DICT = 20
_T_LAUNCH = 20
_T_PGREP = 10
_PGREP_TRIES = 3

_MESH_OK_MARKER = "Mesh OK."  # checkMesh 成功正向 marker（agent-cfd-live checkMesh.log 实测）
_MAX_END_TIME = 600.0  # R1-P1-4：canonical endTime=150 的 4×；detached 无取消路径，必须有界
_RUN_ID_MAX_AHEAD = timedelta(hours=24)  # R1-P2-2：拒远未来 ID 钉死 hub newest_by_name


def _run_id_semantic_ok(run_id: str) -> bool:
    """fullmatch 之后的语义校验：真日期（strptime 拒 hour-30/99999999）且不超前
    当前 UTC 24h（拒远未来 pinning）。过去的 ID 不设限——重放/补录合法。"""
    try:
        ts = datetime.strptime(run_id, "%Y%m%d-%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return False
    return ts <= datetime.now(timezone.utc) + _RUN_ID_MAX_AHEAD


def _fail(msg: str) -> dict[str, Any]:
    return {"status": "failed", "error_message": msg}


def _dexec(container: str, cwd: str, script: str, timeout: int) -> subprocess.CompletedProcess:
    # 固定脚本模板经参数列表传入（shell=False）：唯一进 script 的变量是白名单校验过的
    # run_id（拼 cwd）与数值校验过的 end_time，零用户自由文本。
    return subprocess.run(["docker", "exec", "-w", cwd, container, "bash", "-lc", script],
                          capture_output=True, text=True, timeout=timeout, shell=False)


def run(payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    del context
    case = payload.get("case")
    if case not in _CASE_WHITELIST:
        return _fail(f"case 非白名单：{case!r}（仅 {sorted(_CASE_WHITELIST)}）")
    run_id = str(payload.get("run_id", ""))
    if not _RUN_ID_RE.fullmatch(run_id):
        return _fail(f"run_id 非法（须 YYYYMMDD-HHMMSS）：{run_id!r}——拒绝拼路径，fail-closed")
    if not _run_id_semantic_ok(run_id):
        return _fail(f"run_id 语义非法（须真实日期且不超前当前 UTC 24h）：{run_id!r}——"
                     "假日期/远未来 ID 会钉死 hub newest_by_name 遮蔽后续 run，fail-closed")
    et = payload.get("end_time")
    if et is not None:
        if not isinstance(et, (int, float)) or isinstance(et, bool) or not (0 < et <= _MAX_END_TIME):
            return _fail(f"end_time 非法（须 0<t≤{_MAX_END_TIME:g}）：{et!r}——detached 求解无"
                         "取消路径，无界时长=无界烧 CPU，fail-closed")
    container = os.environ.get(_CONTAINER_ENV)
    case_root_raw = os.environ.get(_CASE_ENV)
    template_raw = os.environ.get(_TEMPLATE_ENV)
    if not (container and case_root_raw and template_raw):
        return _fail(f"config 缺失（{_CONTAINER_ENV}/{_CASE_ENV}/{_TEMPLATE_ENV}）——fail-closed，绝不猜路径")
    case_root = Path(case_root_raw).expanduser()
    template = Path(template_raw).expanduser()
    if not case_root.is_dir():
        return _fail(f"case 根不存在：{case_root}")
    template_msh = template / "cyl2d.msh"
    template_geo = template / _GEO_REL
    if not template_msh.is_file() and not template_geo.is_file():
        return _fail(f"template 无 mesh 来源（既无 cyl2d.msh 也无 {_GEO_REL}）：{template}——fail-closed")

    # ① 建 run 子目录（host 侧；零删除——已存在即拒，防覆写在跑的 run）
    run_dir = case_root / run_id
    if run_dir.exists():
        return _fail(f"run 子目录已存在：{run_dir}——拒绝覆写，换 run_id")
    ctr_cwd = f"{_CONTAINER_RUN_ROOT}/{run_id}"

    # ② 铺算例（host 侧拷 template：0/ constant/ system/ [geo/ cyl2d.msh]）
    try:
        shutil.copytree(template, run_dir)
    except OSError as exc:
        return _fail(f"铺算例失败：{exc}")

    # ②b mesh（Codex R0-P1-1 两条腿）：自备 msh 已随 copytree 就位；否则 host gmsh
    # 从 geo 生成（canonical 兜底路线，host 直出免 docker cp）。
    if not (run_dir / "cyl2d.msh").is_file():
        try:
            gm = subprocess.run(
                ["gmsh", str(run_dir / _GEO_REL), "-3", "-format", "msh2",
                 "-o", str(run_dir / "cyl2d.msh")],
                capture_output=True, text=True, timeout=_T_GMSH, shell=False)
        except FileNotFoundError:
            return _fail("host gmsh 不在位且 template 无自备 cyl2d.msh——fail-closed")
        except subprocess.TimeoutExpired:
            return _fail(f"gmsh 生成网格超时（>{_T_GMSH}s）")
        if gm.returncode != 0 or not (run_dir / "cyl2d.msh").is_file():
            return _fail(f"gmsh 生成网格失败：{(gm.stderr or gm.stdout or '').strip()[-300:]}")

    # ③ 容器可达性（fire 前最后一道；先铺后 ping 使失败残留可诊断，子目录无 sidecar
    #    不会被 hub marker 认作 run）
    ping = subprocess.run(["docker", "exec", container, "true"],
                          capture_output=True, text=True, timeout=_T_PING, shell=False)
    if ping.returncode != 0:
        return _fail(f"容器 {container} 未就绪：{(ping.stderr or '').strip()[:200]}——绝不谎报已发起")

    # ③b 单并发契约（R1 CRS-P2）：agent 声明「同一时刻一次求解」，Registry 不
    # 强制 max_parallel_jobs → 工具侧兜底。同款 pgrep+cwd 对账，cwd 落在 run
    # 根下（任意子目录）即算活跃求解，命中即拒——fail-closed，绝不并发开跑。
    _busy_script = (f"for p in $(pgrep -x '{_SOLVER_PGREP}'); do readlink /proc/$p/cwd; done"
                    f" | grep -q '^{_CONTAINER_RUN_ROOT}/'")
    try:
        busy = subprocess.run(["docker", "exec", container, "bash", "-c", _busy_script],
                              capture_output=True, text=True, timeout=_T_PGREP, shell=False)
    except subprocess.TimeoutExpired:
        return _fail("单并发探测超时——无法确认容器内无活跃求解，fail-closed 不发起")
    if busy.returncode == 0:
        return _fail("容器内已有活跃求解（单并发契约：同一时刻一次求解）——等其完成后重试，绝不并发开跑")
    if busy.returncode != 1:
        # Codex R2-P1：rc=1 是 grep 的「确认无匹配」；其他码（docker exec 125/126、
        # bash 127 等）= 探测本身失败——不可与 idle 混同，fail-closed。
        return _fail(f"单并发探测失败（rc={busy.returncode}）：{(busy.stderr or '').strip()[:200]}"
                     "——无法确认 idle，fail-closed 不发起")

    # ④ 网格转换 + 检查（固定脚本模板，cwd=子目录；pipefail + Mesh OK. 正向断言，
    #    Codex R0-P1-3——tee 会吞 checkMesh 退出码）
    mesh = _dexec(container, ctr_cwd,
                  f"{_OF} && gmshToFoam cyl2d.msh && "
                  f"foamDictionary constant/polyMesh/boundary -entry entry0/frontAndBack/type -set empty && "
                  f"checkMesh | tee checkMesh.log", _T_MESH)
    if mesh.returncode != 0 or _MESH_OK_MARKER not in (mesh.stdout or ""):
        return _fail("网格/检查失败（无 Mesh OK. 正向 marker）："
                     f"{(mesh.stderr or mesh.stdout or '').strip()[-300:]}")

    # ⑤ 可选 end_time（入口处已校验 0<t≤_MAX_END_TIME，R1-P1-4——此处只注入数值，
    #    零自由文本进脚本；Codex R0-P2-1：foamDictionary 失败即 fail，绝不带错
    #    endTime 开跑）
    if et is not None:
        dic = _dexec(container, ctr_cwd,
                     f"{_OF} && foamDictionary system/controlDict -entry endTime -set {float(et)}",
                     _T_DICT)
        if dic.returncode != 0:
            return _fail(f"endTime 写入失败：{(dic.stderr or dic.stdout or '').strip()[-200:]}——不发起求解")

    # ⑥ 发起求解（fire：nohup & 立即返回，不等 ~200s）。`echo $!` 输出被后台化
    #    AND-list 子壳的 PID（Codex R2-P1 PID 握手）：子壳前台等 pimpleFoam
    #    wrapper→foamRun，求解期间恒活、跑完即退——为 ⑥b 提供与进程名/启动
    #    时序无关的存活凭据。
    launch = _dexec(container, ctr_cwd,
                    f"{_OF} && nohup pimpleFoam > log.pimpleFoam 2>&1 & echo $!",
                    _T_LAUNCH)
    if launch.returncode != 0:
        return _fail(f"发起求解失败：{(launch.stderr or '').strip()[:200]}")
    launch_pid = (launch.stdout or "").strip().splitlines()[-1] if (launch.stdout or "").strip() else ""
    if not launch_pid.isdigit():
        return _fail(f"发起后未取得求解 PID（stdout={launch.stdout!r}）——无法验证存活，fail-closed")

    # ⑥b 验证求解真起来了（Codex R0-P1-2 + R2-P1 换 PID 握手）：按 ⑥ 捕获的
    # PID 查 /proc/<pid>/cwd 与本 run 子目录精确对账——不依赖进程名（OF11
    # wrapper comm=foamRun 教训）也不受慢启动竞态影响（子壳从 fire 起即在）。
    # bashrc 缺失/pimpleFoam 不可执行 → 子壳秒退 → PID 已死且 log 无 End →
    # fail-closed。固定脚本，PID 已 isdigit 校验、ctr_cwd 白名单派生。
    _alive_script = f"[ \"$(readlink /proc/{launch_pid}/cwd 2>/dev/null)\" = '{ctr_cwd}' ]"
    alive = False
    probe_error = None
    for i in range(_PGREP_TRIES):
        if i:
            time.sleep(1)
        try:
            pg = subprocess.run(["docker", "exec", container, "bash", "-c", _alive_script],
                                capture_output=True, text=True, timeout=_T_PGREP, shell=False)
        except subprocess.TimeoutExpired:
            probe_error = "探测超时"
            continue
        if pg.returncode == 0:
            alive = True
            break
    if not alive:
        tail = ""
        log_path = run_dir / "log.pimpleFoam"
        if log_path.is_file():
            tail = log_path.read_text(errors="replace")[-300:]
        # R1 CRS-P2：小 end_time 求解可在探测窗口内**正常跑完**——OpenFOAM 正常
        # 收尾 log 末行是 "End"（与 cfd_result_read 的 ended 门同判据：末非空行
        # 全等，防 log 中段偶现 End 子串冒充）。这是已完成的真 run，照常盖
        # sidecar；只有既无活进程又无 End 才是启动失败。
        last_line = next((ln for ln in reversed(tail.splitlines()) if ln.strip()), "")
        if last_line.strip() == _END_MARKER:
            (run_dir / ".hub_run_id").write_text(run_id, encoding="utf-8")
            return {"status": "success", "run_id": run_id, "run_dir": str(run_dir),
                    "container": container, "checkmesh_ok": True, "launched_at": run_id,
                    "note": "求解在探测窗口内已正常跑完（log 以 End 收尾）"}
        return _fail(f"求解未确认存活（PID {launch_pid} 探测未命中"
                     f"{'，' + probe_error if probe_error else ''}，重试 {_PGREP_TRIES} 次）且 log"
                     f"无正常收尾 End——不盖 sidecar，绝不谎报已发起。残留子目录无 sidecar 不会被"
                     f"平台/hub 认作 run（若求解稍后仍起来即为孤儿 run，诊断后人工处置）。log 尾：{tail.strip()}")

    # ⑦ 盖 sidecar（host 侧，最后一步=hub marker：sidecar 在场即「这是一个已发起的 run」）
    (run_dir / ".hub_run_id").write_text(run_id, encoding="utf-8")

    return {"status": "success", "run_id": run_id, "run_dir": str(run_dir),
            "container": container, "checkmesh_ok": True, "launched_at": run_id}
