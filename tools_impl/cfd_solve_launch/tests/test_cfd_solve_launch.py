"""cfd_solve_launch 安全属性测试（mock subprocess/docker，无容器）：
case 白名单 / run_id 正则先于拼路径 / config fail-closed / shell=False 参数列表 /
bind-mount 铁律强化版（零删除——旧 run 与 case/run 本体谁都不碰）。
"""
from tools_impl.cfd_solve_launch.adapter import run

RID = "20260713-101010"


def _env(monkeypatch, tmp_path):
    case_root = tmp_path / "run"
    case_root.mkdir()
    template = tmp_path / "template"
    template.mkdir()
    # 最小 template：真实模板含 0/ constant/ system/ cyl2d.msh，测试只需存在性
    (template / "cyl2d.msh").write_text("$MeshFormat\n")
    for d in ("0", "constant", "system"):
        (template / d).mkdir()
    monkeypatch.setenv("FLAI_CFD_CONTAINER", "cfd-openfoam-live")
    monkeypatch.setenv("FLAI_CFD_CASE_DIR", str(case_root))
    monkeypatch.setenv("FLAI_CFD_TEMPLATE_DIR", str(template))
    return case_root


def test_config_missing_fail_closed(monkeypatch):
    monkeypatch.delenv("FLAI_CFD_CONTAINER", raising=False)
    monkeypatch.delenv("FLAI_CFD_CASE_DIR", raising=False)
    monkeypatch.delenv("FLAI_CFD_TEMPLATE_DIR", raising=False)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"


def _forbid_subprocess(monkeypatch):
    """入参拒绝必须先于任何 subprocess——一旦调用即测试失败（tamper② 教训：
    只断言 status==failed 会被「后续步骤碰巧失败」冒充通过路径）。"""
    import tools_impl.cfd_solve_launch.adapter as mod

    def _boom(*a, **kw):
        raise AssertionError("入参非法时不得触任何 subprocess（拒绝须先于拼路径/执行）")

    monkeypatch.setattr(mod.subprocess, "run", _boom)


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
    assert out["status"] == "failed"  # 非 ^\d{8}-\d{6}$ 拒绝，先于任何路径拼接
    assert "run_id" in out["error_message"]  # 失败原因=正则白名单
    assert list(case_root.iterdir()) == []  # 零路径副作用（没铺任何东西）


def test_existing_run_dir_not_overwritten(monkeypatch, tmp_path):
    # 零删除的另一半：同名 run 已存在 → 拒绝覆写（防覆写在跑的 run）
    case_root = _env(monkeypatch, tmp_path)
    (case_root / RID).mkdir()
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"


def test_never_deletes_anything(monkeypatch, tmp_path):
    # bind-mount 铁律强化版（落法 2026-07-13）：每 run 新建子目录，adapter 全程
    # 零删除操作——旧 run 与 case/run 本体谁都不碰
    case_root = _env(monkeypatch, tmp_path)
    old_run = case_root / "20260101-000000"
    old_run.mkdir()
    (old_run / "keep.txt").write_text("old")
    import tools_impl.cfd_solve_launch.adapter as mod
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert (old_run / "keep.txt").read_text() == "old"  # 旧 run 完好
    for argv, kw in calls:
        joined = " ".join(argv)
        assert "rm -rf" not in joined and "rmdir" not in joined and "-delete" not in joined
    assert (case_root / RID / ".hub_run_id").is_file() or out["status"] == "failed"


def test_shell_false_argv_and_subdir_cwd(monkeypatch, tmp_path):
    # 容器名来自 config；docker 调用是参数列表非 shell 串拼；cwd=子目录
    import tools_impl.cfd_solve_launch.adapter as mod
    case_root = _env(monkeypatch, tmp_path)
    calls = []

    def fake_run(argv, **kw):
        calls.append((argv, kw))

        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    assert (case_root / RID / "cyl2d.msh").is_file()  # host 侧铺算例进子目录
    docker_calls = [argv for argv, kw in calls if argv and argv[0] == "docker"]
    assert docker_calls, "应有 docker exec 调用"
    for argv, kw in calls:
        assert isinstance(argv, list)
        assert kw.get("shell", False) is False
    # 求解 cwd 必须是时间戳子目录（-w /home/openfoam/run/<run_id>）
    assert any(f"/home/openfoam/run/{RID}" in " ".join(a) for a in docker_calls)


def test_sidecar_written_last_and_success_shape(monkeypatch, tmp_path):
    # sidecar 是 hub marker：success 时必在场且内容=run_id
    import tools_impl.cfd_solve_launch.adapter as mod
    case_root = _env(monkeypatch, tmp_path)

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        return R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "success"
    assert out["run_id"] == RID
    assert (case_root / RID / ".hub_run_id").read_text() == RID


def test_mesh_failure_fail_closed_no_sidecar(monkeypatch, tmp_path):
    # 网格失败 → failed 且不盖 sidecar（hub 不认作 run，绝不谎报已发起）
    import tools_impl.cfd_solve_launch.adapter as mod
    case_root = _env(monkeypatch, tmp_path)

    def fake_run(argv, **kw):
        class R:
            returncode = 0
            stdout = "ok"
            stderr = ""
        joined = " ".join(argv)
        if "gmshToFoam" in joined:
            R.returncode = 1
            R.stderr = "gmshToFoam: cannot read mesh"
        return R()

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = run({"case": "cylinder_re100", "run_id": RID})
    assert out["status"] == "failed"
    assert not (case_root / RID / ".hub_run_id").exists()
