"""cfd_solve_launch 安全属性测试（mock subprocess/docker，无容器）：
case 白名单 / run_id fullmatch 白名单先于拼路径 / config fail-closed /
shell=False 参数列表 / bind-mount 铁律强化版（零删除）/ mesh 双腿
（template 自备 msh 或 host gmsh 从 geo 生成，Codex R0-P1-1）/ checkMesh
正向断言 Mesh OK.（R0-P1-3）/ 求解进程 pgrep 验证后才盖 sidecar（R0-P1-2）/
end_time 失败即 fail（R0-P2-1）/ R1：alive 匹配 OF11 真进程 comm=foamRun
（wrapper 假阴性回归）/ 探测窗口内正常跑完（log End 收尾）算成功 /
单并发契约（容器内已有活跃求解即拒）。
"""
from pathlib import Path

from tools_impl.cfd_solve_launch.adapter import run

RID = "20260713-101010"


def _env(monkeypatch, tmp_path, *, with_msh: bool = False):
    case_root = tmp_path / "run"
    case_root.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    # 真实布局（agent-cfd-live case/template 实测）：0/ constant/ system/ geo/，
    # **无 cyl2d.msh**——mesh 由 host gmsh 从 geo/domain_parametric.geo 生成
    # （canonical 兜底路线，rehearse.sh:94）。with_msh=True 覆盖「自备模板」路径。
    for d in ("0", "constant", "system", "geo"):
        (template / d).mkdir()
    (template / "geo" / "domain_parametric.geo").write_text("// param geo\n")
    if with_msh:
        (template / "cyl2d.msh").write_text("$MeshFormat\n")
    monkeypatch.setenv("FLAI_CFD_CONTAINER", "cfd-openfoam-live")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(case_root))
    monkeypatch.setenv("FLAI_CFD_TEMPLATE_DIR", str(template))
    return case_root


class _FakeProc:
    def __init__(self, returncode=0, stdout="ok", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _install_fake_run(monkeypatch, calls, *, overrides=None):
    """按 argv 内容分派的 subprocess 替身。默认全成功且行为忠实：
    gmsh → 真在 -o 目标落一个 mesh 文件；checkMesh → stdout 含 Mesh OK.；
    pgrep → 命中。overrides: {关键字: _FakeProc 或 callable(argv)->_FakeProc}。"""
    import tools_impl.cfd_solve_launch.adapter as mod

    def fake_run(argv, **kw):
        calls.append((argv, kw))
        joined = " ".join(str(a) for a in argv)
        for key, resp in (overrides or {}).items():
            if key in joined:
                return resp(argv) if callable(resp) else resp
        if argv[0] == "gmsh":
            Path(argv[argv.index("-o") + 1]).write_text("$MeshFormat\n")
            return _FakeProc()
        if "checkMesh" in joined:
            return _FakeProc(stdout="... Mesh OK.\nEnd\n")
        if "pgrep" in joined:
            # 两个调用点行为忠实：busy 扫（grep -q '^…run 根'）→ rc=1 无活跃
            # 求解；alive 验证（grep -qx 精确 cwd）→ rc=0 命中。
            if "grep -qx" in joined:
                return _FakeProc(stdout="")
            return _FakeProc(returncode=1, stdout="")
        return _FakeProc()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)


def _forbid_subprocess(monkeypatch):
    """入参拒绝必须先于任何 subprocess——一旦调用即测试失败（tamper② 教训：
    只断言 status==failed 会被「后续步骤碰巧失败」冒充通过路径）。"""
    import tools_impl.cfd_solve_launch.adapter as mod

    def _boom(*a, **kw):
        raise AssertionError("入参非法时不得触任何 subprocess（拒绝须先于拼路径/执行）")

    monkeypatch.setattr(mod.subprocess, "run", _boom)


def test_config_missing_fail_closed(monkeypatch):
    monkeypatch.delenv("FLAI_CFD_CONTAINER", raising=False)
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    monkeypatch.delenv("FLAI_CFD_TEMPLATE_DIR", raising=False)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"


def test_case_whitelist_only(monkeypatch, tmp_path):
    _env(monkeypatch, tmp_path)
    _forbid_subprocess(monkeypatch)
    out = run({"case": "'; rm -rf /", "run_id": RID})  # 注入尝试
    assert out["status"] == "failed"  # 白名单外拒绝
    assert "case" in out["error_message"]  # 失败原因=白名单，非后续碰巧失败


def test_run_id_traversal_rejected(monkeypatch, tmp_path):
    case_root = _env(monkeypatch, tmp_path)
    _forbid_subprocess(monkeypatch)
    out = run({"case": "cylinder_re100", "run_id": "../../etc"})
    assert out["status"] == "failed"  # 白名单 fullmatch 拒绝，先于任何路径拼接
    assert "run_id" in out["error_message"]
    assert list(case_root.iterdir()) == []  # 零路径副作用


def test_run_id_trailing_newline_rejected(monkeypatch, tmp_path):
    # Codex R0-P2-2：re.match+$ 会放行尾 \n（sidecar 对账时又读不回来）——须 fullmatch [0-9]
    case_root = _env(monkeypatch, tmp_path)
    _forbid_subprocess(monkeypatch)
    out = run({"case": "cylinder_re100", "run_id": RID + "\n"})
    assert out["status"] == "failed"
    assert list(case_root.iterdir()) == []


def test_existing_run_dir_not_overwritten(monkeypatch, tmp_path):
    case_root = _env(monkeypatch, tmp_path)
    (case_root / RID).mkdir()
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"


def test_never_deletes_anything(monkeypatch, tmp_path):
    # bind-mount 铁律强化版：每 run 新建子目录，adapter 全程零删除操作
    case_root = _env(monkeypatch, tmp_path)
    old_run = case_root / "20260101-000000"
    old_run.mkdir()
    (old_run / "keep.txt").write_text("old")
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert (old_run / "keep.txt").read_text() == "old"  # 旧 run 完好
    for argv, kw in calls:
        joined = " ".join(str(a) for a in argv)
        assert "rm -rf" not in joined and "rmdir" not in joined and "-delete" not in joined
    assert (case_root / RID / ".hub_run_id").is_file() or out["status"] == "failed"


def test_mesh_generated_from_geo_when_template_has_no_msh(monkeypatch, tmp_path):
    # Codex R0-P1-1：真实 template 无 cyl2d.msh——host gmsh 从 geo 生成进 run 子目录
    case_root = _env(monkeypatch, tmp_path, with_msh=False)
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    assert (case_root / RID / "cyl2d.msh").is_file()
    gmsh_calls = [argv for argv, kw in calls if argv[0] == "gmsh"]
    assert len(gmsh_calls) == 1
    assert kw_shell_all_false(calls)


def test_template_msh_used_directly_no_gmsh(monkeypatch, tmp_path):
    # 自备模板（template 已含 cyl2d.msh）→ 直接拷，不调 gmsh
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    assert (case_root / RID / "cyl2d.msh").is_file()
    assert not [argv for argv, kw in calls if argv[0] == "gmsh"]


def test_no_msh_and_no_geo_fail_closed(monkeypatch, tmp_path):
    # 两条腿都断（无 msh 无 geo）→ fail，不猜
    case_root = _env(monkeypatch, tmp_path, with_msh=False)
    import os
    tpl = os.environ["FLAI_CFD_TEMPLATE_DIR"]
    (Path(tpl) / "geo" / "domain_parametric.geo").unlink()
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()


def test_shell_false_argv_and_subdir_cwd(monkeypatch, tmp_path):
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    assert (case_root / RID / "cyl2d.msh").is_file()
    docker_calls = [argv for argv, kw in calls if argv and argv[0] == "docker"]
    assert docker_calls, "应有 docker exec 调用"
    assert kw_shell_all_false(calls)
    assert any(f"/home/openfoam/run/{RID}" in " ".join(a) for a in docker_calls)


def kw_shell_all_false(calls) -> bool:
    for argv, kw in calls:
        assert isinstance(argv, list)
        assert kw.get("shell", False) is False
    return True


def test_checkmesh_without_mesh_ok_marker_fail_closed(monkeypatch, tmp_path):
    # Codex R0-P1-3：tee 吞退出码——必须正向要求 Mesh OK.，缺 marker 即 fail
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls,
                      overrides={"checkMesh": _FakeProc(stdout="...FOAM FATAL ERROR piped away\nEnd\n")})
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()


def test_solver_not_running_after_fire_fail_closed_no_sidecar(monkeypatch, tmp_path):
    # Codex R0-P1-2：`... && nohup x &` 整体后台化恒返 0——必须 pgrep 验证进程在，
    # 不在即 fail 且不盖 sidecar（绝不谎报已发起）
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls, overrides={"pgrep": _FakeProc(returncode=1, stdout="")})
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()


def test_end_time_dict_failure_aborts_before_launch(monkeypatch, tmp_path):
    # Codex R0-P2-1：foamDictionary 失败必须 fail，绝不带错误 endTime 静默开跑
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls,
                      overrides={"foamDictionary system/controlDict": _FakeProc(returncode=1, stderr="cannot open")})
    out = run({"case": "cylinder_re100", "run_id": RID, "end_time": 60})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()
    assert not any("pimpleFoam" in " ".join(str(x) for x in argv) and "nohup" in " ".join(str(x) for x in argv)
                   for argv, kw in calls), "endTime 失败后不得发起求解"


def test_sidecar_written_last_and_success_shape(monkeypatch, tmp_path):
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    assert out["run_id"] == RID
    assert (case_root / RID / ".hub_run_id").read_text() == RID


def test_mesh_failure_fail_closed_no_sidecar(monkeypatch, tmp_path):
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls,
                      overrides={"gmshToFoam": _FakeProc(returncode=1, stderr="gmshToFoam: cannot read mesh")})
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()


def test_alive_check_covers_of11_foamrun_comm(monkeypatch, tmp_path):
    # R1 真跑取证回归：OF11 pimpleFoam 是 sh wrapper，真进程 comm=foamRun——
    # alive/busy 的 pgrep 必须 -x 'foamRun|pimpleFoam'（裸 pgrep pimpleFoam
    # 假阴性=孤儿 run；-f 会误中 cmdline 含 pimpleFoam 的启动壳=假阳性）。
    _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    pgrep_scripts = [" ".join(str(a) for a in argv) for argv, kw in calls
                     if "pgrep" in " ".join(str(a) for a in argv)]
    assert pgrep_scripts, "应有 pgrep 调用"
    for js in pgrep_scripts:
        assert "pgrep -x 'foamRun|pimpleFoam'" in js
        assert "pgrep -f" not in js


def test_completed_before_probe_is_success_with_sidecar(monkeypatch, tmp_path):
    # R1 CRS-P2：小 end_time 求解在探测窗口内正常跑完（log 以 End 收尾）——
    # 这是已完成的真 run，须照常盖 sidecar，而非误判启动失败。
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []

    def _launch_writes_completed_log(argv):
        (case_root / RID / "log.pimpleFoam").write_text(
            "Time = 2s\nExecutionTime = 3.1 s\nEnd\n")
        return _FakeProc()

    _install_fake_run(monkeypatch, calls, overrides={
        "nohup": _launch_writes_completed_log,
        "grep -qx": _FakeProc(returncode=1, stdout=""),  # alive 扑空（已跑完）
    })
    out = run({"case": "cylinder_re100", "run_id": RID, "end_time": 2})
    assert out["status"] == "success"
    assert (case_root / RID / ".hub_run_id").read_text() == RID


def test_crashed_solver_without_end_marker_still_fails(monkeypatch, tmp_path):
    # 对称负例：进程不在且 log 无 End（中途死/没起来）→ fail 不盖 sidecar，
    # 防「探测窗口内跑完」分支被崩溃 log 冒充。
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []

    def _launch_writes_truncated_log(argv):
        (case_root / RID / "log.pimpleFoam").write_text(
            "Time = 1.5s\nGAMG:  Solving for p, Initial residual = 0.01\n")
        return _FakeProc()

    _install_fake_run(monkeypatch, calls, overrides={
        "nohup": _launch_writes_truncated_log,
        "grep -qx": _FakeProc(returncode=1, stdout=""),
    })
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()


def test_active_solver_in_container_rejects_new_launch(monkeypatch, tmp_path):
    # R1 CRS-P2 单并发契约：容器内已有活跃求解（busy 扫 rc=0）→ 拒绝发起，
    # 不触 mesh/求解，不盖 sidecar。
    case_root = _env(monkeypatch, tmp_path, with_msh=True)
    calls = []
    _install_fake_run(monkeypatch, calls, overrides={
        "grep -q '^": _FakeProc(returncode=0, stdout=""),  # busy 扫命中
    })
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert "并发" in out["error_message"] or "活跃" in out["error_message"]
    assert not (case_root / RID / ".hub_run_id").exists()
    assert not any("gmshToFoam" in " ".join(str(x) for x in argv) for argv, kw in calls), \
        "单并发拒绝须先于任何容器 mesh 操作"
