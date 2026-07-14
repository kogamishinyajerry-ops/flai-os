"""T2 不可变评测快照（#5）存储原语。

eval_snapshots：handle=内容 sha256 的 insert-once 存储。二次写同 handle 绝不覆盖
（不可变；末尾 tamper：改 OR REPLACE 允许覆盖→RED）。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.storage import repos
from backend.app.storage.db import get_conn, init_db


@pytest.fixture()
def conn_factory(tmp_path: Path):
    db_path = tmp_path / "flai_os.db"
    init_db(db_path)

    def factory():
        return get_conn(db_path)

    return factory


def test_insert_snapshot_then_get_roundtrip(conn_factory) -> None:
    conn = conn_factory()
    try:
        repos.insert_eval_snapshot(conn, handle="h1", agent_id="a", agent_version="0.1.0",
                                   eval_cases_digest="d1", content_json='{"x":1}')
        snap = repos.get_eval_snapshot(conn, "h1")
    finally:
        conn.close()
    assert snap is not None
    assert snap["handle"] == "h1" and snap["content_json"] == '{"x":1}'
    assert snap["agent_version"] == "0.1.0" and snap["eval_cases_digest"] == "d1"


def test_get_missing_snapshot_returns_none(conn_factory) -> None:
    conn = conn_factory()
    try:
        assert repos.get_eval_snapshot(conn, "nope") is None
    finally:
        conn.close()


def test_snapshot_is_immutable_insert_once(conn_factory) -> None:
    """同 handle 二次写入（内容不同）绝不覆盖——不可变（tamper 改 OR REPLACE→RED）。"""
    conn = conn_factory()
    try:
        repos.insert_eval_snapshot(conn, handle="h", agent_id="a", agent_version="0.1.0",
                                   eval_cases_digest="d", content_json='{"frozen":true}')
        # 二次写同 handle 换内容（模拟 enqueue 重放 / 篡改尝试）
        repos.insert_eval_snapshot(conn, handle="h", agent_id="a", agent_version="9.9.9",
                                   eval_cases_digest="TAMPERED", content_json='{"frozen":false}')
        snap = repos.get_eval_snapshot(conn, "h")
    finally:
        conn.close()
    assert snap["content_json"] == '{"frozen":true}', "insert-once：二次写绝不覆盖冻结内容"
    assert snap["agent_version"] == "0.1.0" and snap["eval_cases_digest"] == "d"


REPO = Path(__file__).resolve().parents[2]


def _fresh_registry(tmp_path: Path):
    import shutil

    from backend.app.runtime.registry import AgentRegistry

    agents_dir = tmp_path / "agents"
    agents_dir.mkdir()
    shutil.copytree(REPO / "agents" / "hello_agent", agents_dir / "hello_agent")
    reg = AgentRegistry(agents_dir, REPO / "contracts" / "agent.schema.json")
    reg.scan()
    assert reg.get("hello_agent") is not None
    return reg, agents_dir / "hello_agent"


def test_enqueue_freezes_snapshot_and_binds_run(conn_factory, tmp_path) -> None:
    """enqueue 冻结不可变快照 + run 绑 handle；快照含材化所需文件（workflow.py + cases）。"""
    import json as _json

    from backend.app.governance import eval_runner

    reg, _pkg = _fresh_registry(tmp_path)
    conn = conn_factory()
    try:
        run = eval_runner.enqueue_eval_run(
            conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t"
        )
        snap = repos.get_eval_snapshot(conn, run["snapshot_handle"])
    finally:
        conn.close()
    assert run["status"] == "queued"
    handle = run["snapshot_handle"]
    assert handle and handle.startswith("snap_"), "run 绑定内容派生 handle"
    assert snap is not None
    content = _json.loads(snap["content_json"])
    assert content["agent_id"] == "hello_agent"
    assert "workflow.py" in content["files"], "workflow.py 必冻结（runtime 显式加载执行）"
    assert "agent.yaml" in content["files"]
    assert any(k.startswith("eval_cases/") for k in content["files"]), "eval_cases 必冻结"


def test_enqueue_snapshot_is_content_derived_and_deduped(conn_factory, tmp_path) -> None:
    """同一活包两次 enqueue → 同 handle（内容派生）→ 快照去重到一行（insert-once）。"""
    from backend.app.governance import eval_runner

    reg, _pkg = _fresh_registry(tmp_path)
    conn = conn_factory()
    try:
        r1 = eval_runner.enqueue_eval_run(conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t")
        r2 = eval_runner.enqueue_eval_run(conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t")
        n = conn.execute("SELECT COUNT(*) FROM eval_snapshots").fetchone()[0]
    finally:
        conn.close()
    assert r1["snapshot_handle"] == r2["snapshot_handle"], "同活包→同内容派生 handle"
    assert r1["id"] != r2["id"], "两个不同 run 引用同一快照"
    assert n == 1, "内容派生 + insert-once → 快照去重到一行"


def test_materialized_snapshot_is_frozen_against_live_edits(conn_factory, tmp_path) -> None:
    """#5 核心：enqueue 冻结后改活磁盘包（case/workflow），材化快照得到的仍是冻结原文——
    执行读快照非活磁盘，enqueue 后改活包对该 run 无影响（materialization 层确定性验证）。"""
    import json as _json
    import tempfile as _tempfile

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    conn = conn_factory()
    try:
        handle = eval_runner.freeze_eval_snapshot(conn, agent_registry=reg, agent_id="hello_agent")
        frozen_case = (pkg / "eval_cases" / "case_001.json").read_text(encoding="utf-8")
        # enqueue 之后篡改活磁盘包
        (pkg / "eval_cases" / "case_001.json").write_text('{"MUTATED_LIVE": true}', encoding="utf-8")
        (pkg / "workflow.py").write_text("# MUTATED LIVE WORKFLOW\n", encoding="utf-8")
        snap = repos.get_eval_snapshot(conn, handle)
    finally:
        conn.close()

    content = _json.loads(snap["content_json"])
    with _tempfile.TemporaryDirectory() as td:
        eval_runner._materialize_snapshot(content, Path(td))
        mat_case = (Path(td) / "eval_cases" / "case_001.json").read_text(encoding="utf-8")
        mat_wf = (Path(td) / "workflow.py").read_text(encoding="utf-8")
    assert "MUTATED_LIVE" not in mat_case and mat_case == frozen_case, "材化 case 是冻结原文"
    assert "MUTATED LIVE" not in mat_wf, "材化 workflow 是冻结原文，非活磁盘改动"


def test_freeze_captures_nested_input_files(conn_factory, tmp_path) -> None:
    """#1（Codex R0-P1）：case 的 input_files 引用嵌套 fixture（eval_cases/fixtures/…）
    必须冻结进快照——freeze 若用非递归 iterdir 会漏掉子目录内文件，材化后
    _run_one_case_inner 判「input_files 引用不合法或不存在」令每个此类 case 失败
    （checked-in cfd_evaluate_agent 正是这形态）。tamper：rglob 改回 iterdir → 嵌套
    文件不在 files → RED。"""
    import json as _json
    import tempfile as _tempfile

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    nested = pkg / "eval_cases" / "fixtures" / "run_x" / "postProcessing"
    nested.mkdir(parents=True)
    (nested / "forceCoeffs.dat").write_text("NESTED FIXTURE BYTES", encoding="utf-8")
    (pkg / "eval_cases" / "case_nested.json").write_text(
        _json.dumps({
            "case_id": "nested", "inputs": {"name": "x"},
            "input_files": ["fixtures/run_x/postProcessing/forceCoeffs.dat"],
            "checks": [{"kind": "status_is", "value": "completed"}],
        }),
        encoding="utf-8",
    )
    conn = conn_factory()
    try:
        handle = eval_runner.freeze_eval_snapshot(conn, agent_registry=reg, agent_id="hello_agent")
        snap = repos.get_eval_snapshot(conn, handle)
    finally:
        conn.close()
    content = _json.loads(snap["content_json"])
    key = "eval_cases/fixtures/run_x/postProcessing/forceCoeffs.dat"
    assert key in content["files"], "嵌套 input_files fixture 必冻结（rglob 递归，非 iterdir）"
    with _tempfile.TemporaryDirectory() as td:
        eval_runner._materialize_snapshot(content, Path(td))
        got = (Path(td) / "eval_cases" / "fixtures" / "run_x" / "postProcessing"
               / "forceCoeffs.dat").read_text(encoding="utf-8")
    assert got == "NESTED FIXTURE BYTES", "材化后嵌套 fixture 字节还原"


def test_freeze_digest_derived_from_frozen_bytes_not_live_reread(
    conn_factory, tmp_path, monkeypatch
) -> None:
    """#3（Codex R0-P2）：freeze 的 digest 必派生自已抓的冻结字节，非二次重读活磁盘。
    模拟「抓完 files、算 digest 前活包被并发改」：patch compute_digest 在真算前改活磁盘
    prompt.md。修复后 digest 从材化冻结字节算（读 frozen_dir 非活 pkg），不受活改影响；
    未修复（二次读活 pkg_dir）则 digest 反映改后 prompt、与冻结 files 打架。
    不变式：snapshot.eval_cases_digest == 从快照自身冻结字节复算的 digest（执行侧口径）。
    tamper：freeze 改回 compute_digest(approved, pkg_dir_live, agent) → RED。"""
    import base64 as _b64
    import json as _json
    import tempfile as _tempfile

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    (pkg / "prompt.md").write_text("ORIGINAL PROMPT", encoding="utf-8")  # 确保被捕获的已知原文
    real_compute = eval_runner.compute_digest

    def _mutate_live_then_compute(approved, pkg_dir=None, agent=None):
        # 模拟 freeze 抓完字节后、算 digest 前，活包 prompt.md 被并发改动
        (pkg / "prompt.md").write_text("MUTATED LIVE DURING FREEZE", encoding="utf-8")
        return real_compute(approved, pkg_dir, agent)

    monkeypatch.setattr(eval_runner, "compute_digest", _mutate_live_then_compute)
    conn = conn_factory()
    try:
        handle = eval_runner.freeze_eval_snapshot(conn, agent_registry=reg, agent_id="hello_agent")
        snap = repos.get_eval_snapshot(conn, handle)
    finally:
        conn.close()
    content = _json.loads(snap["content_json"])
    # 冻结的 prompt.md 是原文，未被并发改污染（旁证冻结字节独立于活磁盘）
    assert _b64.b64decode(content["files"]["prompt.md"]).decode("utf-8") == "ORIGINAL PROMPT"
    # 核心不变式：从快照自身冻结字节复算 digest（execute 侧材化后正是这么算），
    # 必与快照记录的 eval_cases_digest 全等——否则 run 与 GET /snapshot 指纹会打架。
    with _tempfile.TemporaryDirectory() as td:
        frozen = Path(td)
        eval_runner._materialize_snapshot(content, frozen)
        approved, _d, _b = eval_runner.load_eval_cases(frozen)
        recomputed = real_compute(approved, frozen, content["agent"])
    assert snap["eval_cases_digest"] == recomputed, \
        "digest 必派生自冻结字节：与快照自身内容复算一致（未修复的二次读活磁盘会打架）"


def test_freeze_rejects_symlink_escaping_package(conn_factory, tmp_path) -> None:
    """R1-P1（Codex）：eval_cases/ 内 symlink→包外，freeze 绝不把目标字节洗进快照。
    材化会把 symlink 目标固化成常规文件，绕过 _run_one_case_inner 对活磁盘的 resolve()
    containment（活路径拒 symlink 逃逸、快照路径却放行）。tamper：去掉 _grab 的
    resolve-under-root 封闭 → 外部字节入 files → RED。"""
    import base64 as _b64
    import json as _json

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    secret = tmp_path / "outside_secret.txt"
    secret.write_text("EXTERNAL SECRET BYTES", encoding="utf-8")
    (pkg / "eval_cases" / "sneaky.dat").symlink_to(secret)
    conn = conn_factory()
    try:
        handle = eval_runner.freeze_eval_snapshot(conn, agent_registry=reg, agent_id="hello_agent")
        snap = repos.get_eval_snapshot(conn, handle)
    finally:
        conn.close()
    content = _json.loads(snap["content_json"])
    assert "eval_cases/sneaky.dat" not in content["files"], "包外 symlink 目标绝不冻结"
    for b64 in content["files"].values():
        assert b"EXTERNAL SECRET BYTES" not in _b64.b64decode(b64), "外部字节绝不进快照任何文件"


def test_materialize_rejects_escaping_keys(tmp_path) -> None:
    """R1-P1（Codex，纵深防御）：_materialize_snapshot 绝不写出 dest_dir——快照 content
    按不可信对待，绝对/.. 逃逸 key 跳过。tamper：去掉 relative_to(dest_root) 封闭 →
    覆写 dest_dir 外文件 → RED。"""
    import base64 as _b64

    from backend.app.governance import eval_runner

    dest = tmp_path / "mat"
    dest.mkdir()
    victim = tmp_path / "victim.txt"
    victim.write_text("ORIGINAL", encoding="utf-8")
    content = {"files": {
        "../victim.txt": _b64.b64encode(b"HIJACKED").decode("ascii"),
        "eval_cases/ok.json": _b64.b64encode(b"{}").decode("ascii"),
    }}
    eval_runner._materialize_snapshot(content, dest)
    assert victim.read_text(encoding="utf-8") == "ORIGINAL", "越界 key 绝不覆写快照根外文件"
    assert (dest / "eval_cases" / "ok.json").is_file(), "正常 key 正常材化"


def test_enqueue_malformed_input_files_stays_observable_not_500(conn_factory, tmp_path) -> None:
    """R1-P2（Codex）：approved case 的 input_files 形态畸形（非 list[str]）此前会让 freeze
    的 compute_digest 抛 TypeError——T2 起 freeze 在 create_eval_run 之前算 digest，未捕获
    异常 → POST 500 且不落 run，async 端点失可观测。归类 broken 后 enqueue 正常返回
    queued run（digest 不碰畸形 case），执行侧记 failed。tamper：去掉 load_eval_cases 的
    input_files 形态校 → freeze 抛 → enqueue 抛 → RED。"""
    import json as _json

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    (pkg / "eval_cases" / "case_bad.json").write_text(
        _json.dumps({
            "case_id": "bad", "inputs": {"name": "x"},
            "input_files": [1, 2],  # 畸形：非 str 元素
            "checks": [{"kind": "status_is", "value": "completed"}],
        }),
        encoding="utf-8",
    )
    conn = conn_factory()
    try:
        run = eval_runner.enqueue_eval_run(
            conn, agent_registry=reg, agent_id="hello_agent", triggered_by="t"
        )
    finally:
        conn.close()
    assert run["status"] == "queued", "畸形 case 不该让 enqueue 抛，端点保持 202+queued 可观测"
    assert str(run.get("snapshot_handle") or "").startswith("snap_")
    approved, _d, broken = eval_runner.load_eval_cases(pkg)
    assert any(b["_file"] == "case_bad.json" for b in broken), "畸形 input_files → broken"
    assert not any(c["_file"] == "case_bad.json" for c in approved), "畸形 case 不进 approved"


def test_snapshot_registry_respects_live_deregistration(tmp_path) -> None:
    """R2-P1（Codex）：agent 被活注册表注销后（base.get→None），shim 绝不用冻结配置复活它
    ——授权以活注册表为准，返回 None 让 _run_eval_body 的 missing-agent 门 fail-closed。
    tamper：get 无条件返回 frozen → 返回冻结配置非 None → RED。"""
    from backend.app.governance import eval_runner

    class _DeregisteredBase:
        def get(self, aid):  # 已被 reconcile_agent_scopes 注销
            return None

    frozen = {"id": "hello_agent", "version": "0.1.0-frozen"}
    shim = eval_runner._SnapshotRegistry(_DeregisteredBase(), "hello_agent", frozen, tmp_path)
    assert shim.get("hello_agent") is None, "活注册表注销后绝不返回冻结 agent（授权 fail-closed）"


def test_snapshot_registry_returns_frozen_when_live_authorizes(tmp_path) -> None:
    """活注册表仍持有该 agent 时，shim 返回**冻结内容**（可复现执行），非活配置。"""
    from backend.app.governance import eval_runner

    class _AuthorizedBase:
        def get(self, aid):  # 活态仍在（版本刻意不同于冻结）
            return {"id": aid, "version": "9.9.9-live"}

    frozen = {"id": "hello_agent", "version": "0.1.0-frozen"}
    shim = eval_runner._SnapshotRegistry(_AuthorizedBase(), "hello_agent", frozen, tmp_path)
    got = shim.get("hello_agent")
    assert got is not None and got["version"] == "0.1.0-frozen", "活授权在→返回冻结内容非活配置"


def test_draft_with_malformed_input_files_stays_draft_not_broken(tmp_path) -> None:
    """R2-P2（Codex）：draft case（待策展 WIP）的 input_files 即便畸形也绝不判 broken
    （broken→failed 挡晋升覆盖，违 draft 隔离契约「列出但绝不计数」）——input_files 形态
    校仅施于 approved。tamper：把形态校移到 curation 分类之前 → draft 判 broken → RED。"""
    import json as _json

    from backend.app.governance import eval_runner

    reg, pkg = _fresh_registry(tmp_path)
    (pkg / "eval_cases" / "case_draft_wip.json").write_text(
        _json.dumps({
            "case_id": "wip", "curation": "draft", "inputs": {"name": "x"},
            "input_files": [1, 2],  # WIP 临时畸形
            "checks": [{"kind": "status_is", "value": "completed"}],
        }),
        encoding="utf-8",
    )
    approved, drafts, broken = eval_runner.load_eval_cases(pkg)
    assert any(d["_file"] == "case_draft_wip.json" for d in drafts), "draft 保持 draft（隔离契约）"
    assert not any(b["_file"] == "case_draft_wip.json" for b in broken), \
        "draft 绝不因畸形 input_files 判 broken"


def test_freeze_rejects_agent_with_escaping_schema_ref(conn_factory, tmp_path) -> None:
    """R2-P2（Codex）：agent 的 schema/entrypoint 引用逃出包根（绝对/..）→ freeze fail-closed
    拒。仅跳过捕获不足以堵：冻结的 agent 配置仍原样保留该路径，执行侧 AgentRuntime 与
    compute_digest 会用它读活磁盘（materialized_dir / "/abs" == "/abs"），快照声称冻结 A 却
    实评 live B。tamper：去掉 freeze 的引用封闭 raise → 不抛 → RED。"""
    import pytest as _pytest

    from backend.app.governance import eval_runner

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "agent.yaml").write_text("id: x\nversion: 0.1.0\n", encoding="utf-8")

    class _FakeReg:
        def get(self, aid):
            return {"id": "x", "version": "0.1.0", "input": {"schema": "/etc/hostname"}}  # 绝对逃逸

        def package_dir(self, aid):
            return pkg

    conn = conn_factory()
    try:
        with _pytest.raises(ValueError, match="逃出包根"):
            eval_runner.freeze_eval_snapshot(conn, agent_registry=_FakeReg(), agent_id="x")
    finally:
        conn.close()
