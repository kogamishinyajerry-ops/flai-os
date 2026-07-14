"""平台级 Eval Runner（M10 治理闭环，ADR-0018）。

把 `agents/<id>/eval_cases/*.json` 从「注册期强制存在的死目录」变成可执行的
回归证据：每个 approved case 经**真实 runtime.execute 全链**跑成一个
origin='eval' 的任务，按 checks 断言词汇表机器判定，结果落 eval_runs 表
（case 级结果回溯到真实 task_id 与事件时间轴）。

判定纪律（loop-auditor 设计审 D3/D7/S3 落地）：
- 无 checks / interactive 型 → skipped（绝不计入 passed）；
- checks 配置坏掉（未识别 kind / 必填字段缺失）→ **failed**——坏断言绝不空洞通过；
- curation=draft 的 case（样本固化通道生成）不执行、不计入任何计数，单列
  draft_cases 清单——未经策展的自动断言不充当回归金标准；
- 「全绿」= total > 0 且 failed == 0 且 skipped == 0，由晋升门二次判定
  （见 promotion.py），本模块只如实记账。

eval_cases_digest（D2）：本次运行加载的全部 approved case 文件内容按文件名
排序拼接后的 sha256。晋升门用它咬合「同版本号下改软/删除 checks 后拿旧全绿
证据晋升」的博弈面。digest 只证内容未变，不证内容正确（正确性锚在 curation
人工域）。
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Any, Callable

from ..storage import repos
from ..storage.file_integrity import open_verified_file

logger = logging.getLogger(__name__)

_CHECK_KINDS = ("status_is", "artifact_exists", "artifact_contains", "output_field")
_OUTPUT_FIELD_OPS = ("eq", "contains", "exists", "gte", "lte")

# 证据指纹除 approved case 原文外还须绑定被测对象本体（异源审 P1-4/F3）：
# 同版本号下改 workflow/prompt/schema 后，旧全绿证据必须失效。文件名从 agent
# 配置**实际解析**（契约允许任意 schema/entrypoint 文件名——写死默认名会让
# custom_schema.json 的改动逃出指纹）。tool/model/scope 级 provenance 是
# manifest 的完整形态，V0.1 已声明限制（ADR-0018）。
def _referenced_package_files(agent: dict[str, Any]) -> list[str]:
    names = ["agent.yaml", "prompt.md"]
    for ref in (
        (agent.get("workflow") or {}).get("entrypoint"),
        (agent.get("input") or {}).get("schema"),
        (agent.get("output") or {}).get("schema"),
    ):
        if isinstance(ref, str) and ref:
            names.append(ref)
    return sorted(set(names))

# T1（异步评测队列，GH #2）：原进程内 single-flight 锁（EvalBusy→409）已由
# 「入队 + worker 配额门」替换——并发触发不再拒绝，超配额的 run 排队最终执行
# （见 storage.claim_next_queued_eval_run 与 governance.eval_worker.EvalRunner）。


class CheckConfigError(Exception):
    """checks 配置本身不合法（未识别 kind / 必填字段缺失 / 类型不对）。

    按 ADR-0018（审计 D3）：配置错误的 case 记 failed 而非 skipped——
    坏掉的断言绝不能空洞通过。
    """


def load_eval_cases(pkg_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """扫描 eval_cases/ 目录，返回 (approved, drafts, broken)。

    broken = JSON 解析失败的文件（按 D3 记 failed，附原因）。
    每个条目附 `_file`（文件名）与 `_raw`（原始字节，供 digest）。
    """
    approved: list[dict[str, Any]] = []
    drafts: list[dict[str, Any]] = []
    broken: list[dict[str, Any]] = []
    cases_dir = pkg_dir / "eval_cases"
    if not cases_dir.is_dir():
        return approved, drafts, broken
    for path in sorted(cases_dir.glob("*.json")):
        raw = path.read_bytes()
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            broken.append({"_file": path.name, "error": f"case 文件不是合法 JSON：{exc}"})
            continue
        if not isinstance(data, dict):
            broken.append({"_file": path.name, "error": "case 文件顶层必须是 JSON 对象"})
            continue
        data["_file"] = path.name
        data["_raw"] = raw
        # curation 三值严判（异源审 P2-8）：缺省=approved（既有手写口径）、
        # 精确 "draft"=待策展、其余任何值（"pending"/"draft "/false…）一律
        # broken——fail-closed 于畸形策展状态，绝不静默当 approved。
        curation = data.get("curation")
        if curation == "draft":
            drafts.append(data)
        elif curation is None or curation == "approved":
            approved.append(data)
        else:
            broken.append({
                "_file": path.name,
                "error": f"curation 字段值不合法：{curation!r}（只认缺省/approved/draft）",
            })
    return approved, drafts, broken


def compute_digest(
    approved: list[dict[str, Any]],
    pkg_dir: Path | None = None,
    agent: dict[str, Any] | None = None,
) -> str | None:
    """评测证据指纹：approved case 原文 + 引用的输入文件实体 + 配置实际引用的包文件。

    按文件名排序拼接后 sha256；无 approved case 返回 None。
    绑定被测对象本体（异源审 P1-4/F3）：同版本号下改 workflow/prompt/schema/
    输入文件后旧证据必须失效。tool/model/scope 级完整 manifest 是 V0.2 槽位。
    """
    if not approved:
        return None
    h = hashlib.sha256()
    for case in sorted(approved, key=lambda c: c["_file"]):
        h.update(case["_file"].encode("utf-8"))
        h.update(b"\n")
        h.update(case["_raw"])
        h.update(b"\n")
        if pkg_dir is not None:
            for rel_name in sorted(case.get("input_files", []) or []):
                src = pkg_dir / "eval_cases" / rel_name
                h.update(f"input:{rel_name}\n".encode("utf-8"))
                h.update(src.read_bytes() if src.is_file() else b"<missing>")
                h.update(b"\n")
    if pkg_dir is not None and agent is not None:
        for name in _referenced_package_files(agent):
            f = pkg_dir / name
            h.update(f"pkg:{name}\n".encode("utf-8"))
            h.update(f.read_bytes() if f.is_file() else b"<missing>")
            h.update(b"\n")
    return h.hexdigest()


def _dig(obj: Any, dotted: str) -> tuple[bool, Any]:
    """按点路径取值：返回 (found, value)。中途缺键/类型不对 → (False, None)。"""
    cur = obj
    for part in dotted.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
            cur = cur[int(part)]
        else:
            return False, None
    return True, cur


def _require(check: dict[str, Any], field: str, types: tuple[type, ...] = (str,)) -> Any:
    value = check.get(field)
    if not isinstance(value, types):
        raise CheckConfigError(
            f"check kind={check.get('kind')!r} 缺必填字段 {field!r} 或类型不对：{value!r}"
        )
    return value


def _read_artifact_bytes(record: dict[str, Any], task_runs_dir: Path) -> bytes:
    """经 File Store 完整性闸读产物（异源审 P1-5）：root 圈定 + size/sha256
    对账 + 拒 symlink——绝不裸读 record['path']（产物可被执行后替换/删除
    制造假绿或越界读）。校验失败上抛，调用方按 check 失败如实记账。
    """
    with open_verified_file(
        record["path"],
        allowed_root=task_runs_dir,
        expected_size=record["size_bytes"],
        expected_sha256=record["sha256"],
    ) as handle:
        return handle.read()


def _eval_one_check(
    check: Any,
    *,
    final_task: dict[str, Any],
    output_files: list[dict[str, Any]],
    task_runs_dir: Path,
) -> tuple[bool, str]:
    """单条 check 判定：返回 (passed, detail)。配置坏掉抛 CheckConfigError。"""
    if not isinstance(check, dict):
        raise CheckConfigError(f"check 必须是对象：{check!r}")
    kind = check.get("kind")
    if kind not in _CHECK_KINDS:
        raise CheckConfigError(f"未识别的 check kind：{kind!r}（词汇表：{_CHECK_KINDS}）")

    if kind == "status_is":
        expected = _require(check, "value")
        actual = final_task.get("status")
        return actual == expected, f"status_is: 期望 {expected!r}，实际 {actual!r}"

    # 产物归属双保险：output_file_ids 本就属本任务，仍显式过滤 task_id+kind
    by_name = {
        f["filename"]: f
        for f in output_files
        if f.get("task_id") == final_task.get("id") and f.get("kind") == "output"
    }

    if kind == "artifact_exists":
        fname = _require(check, "file")
        record = by_name.get(fname)
        if record is None:
            return False, f"artifact_exists: {fname!r}（产物：{sorted(by_name)}）"
        # 不只看 DB 记录：磁盘实体须过完整性闸（存在+未被替换）才算存在
        try:
            _read_artifact_bytes(record, task_runs_dir)
        except Exception as exc:  # noqa: BLE001 - 完整性失败=产物不可信，如实判失败
            return False, f"artifact_exists: {fname!r} 完整性校验失败：{exc}"
        return True, f"artifact_exists: {fname!r}"

    if kind == "artifact_contains":
        fname = _require(check, "file")
        needle = _require(check, "value")
        record = by_name.get(fname)
        if record is None:
            return False, f"artifact_contains: 产物 {fname!r} 不存在"
        try:
            text = _read_artifact_bytes(record, task_runs_dir).decode("utf-8", errors="replace")
        except Exception as exc:  # noqa: BLE001
            return False, f"artifact_contains: 产物 {fname!r} 完整性校验失败：{exc}"
        return needle in text, f"artifact_contains: {needle!r} in {fname!r}"

    # kind == "output_field"：具名 JSON 产物 + 点路径（任务行不存 result JSON，
    # 产物文件是唯一持久输出载体）。
    fname = _require(check, "file")
    dotted = _require(check, "path")
    op = check.get("op")
    if op not in _OUTPUT_FIELD_OPS:
        raise CheckConfigError(f"output_field 的 op 必须是 {_OUTPUT_FIELD_OPS}：{op!r}")
    if op != "exists" and "value" not in check:
        raise CheckConfigError(f"output_field op={op!r} 缺必填字段 'value'")
    expected = check.get("value")
    if op in ("gte", "lte") and (
        isinstance(expected, bool) or not isinstance(expected, (int, float))
    ):
        # 异源审 P2-7：期望值类型不数值，比较会 TypeError 炸穿 runner——
        # 这是配置错误，fail-closed 记 case failed 而非 500。
        raise CheckConfigError(f"output_field op={op!r} 的 value 必须是数值：{expected!r}")
    record = by_name.get(fname)
    if record is None:
        return False, f"output_field: 产物 {fname!r} 不存在"
    try:
        doc = json.loads(_read_artifact_bytes(record, task_runs_dir).decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        return False, f"output_field: 产物 {fname!r} 不是可读 JSON 或完整性失败：{exc}"
    found, actual = _dig(doc, dotted)
    if op == "exists":
        return found, f"output_field: {dotted!r} exists={found}"
    if not found:
        return False, f"output_field: 路径 {dotted!r} 不存在于 {fname!r}"
    if op == "eq":
        # JSON 严格相等：Python 的 True==1 会让布尔与数字互判相等——按类型先拒
        ok = isinstance(actual, bool) == isinstance(expected, bool) and actual == expected
    elif op == "contains":
        ok = isinstance(actual, str) and isinstance(expected, str) and expected in actual
    elif op == "gte":
        ok = isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual >= expected
    else:  # lte
        ok = isinstance(actual, (int, float)) and not isinstance(actual, bool) and actual <= expected
    return ok, f"output_field: {dotted!r} {op} {expected!r}，实际 {actual!r}"


# 执行材化所需的包文件集（T2/#5）：runtime 显式加载 pkg_dir/workflow.py（见
# runtime.execute），故 workflow.py 必冻结；其余引用文件（agent.yaml/prompt.md/
# schemas/entrypoint）+ eval_cases/ 全量（case + input_files）覆盖 load_eval_cases /
# compute_digest / _run_one_case 的全部磁盘读点。
def freeze_eval_snapshot(conn: Any, *, agent_registry: Any, agent_id: str) -> str:
    """冻结当前活包为不可变快照，返回内容派生 handle（T2/#5）。捕获 { 解析配置 agent +
    材化所需全部包文件 + eval_cases_digest }，canonical JSON 的 sha256 为 handle，
    insert-once 落库。执行侧据 handle 材化读取而非活磁盘——enqueue 后改活包对该 run 无
    影响，「评的就是晋升的那版」由冻结保证而非靠检测篡改。"""
    agent = agent_registry.get(agent_id)
    if agent is None:
        raise ValueError(f"agent 不存在：{agent_id}")
    pkg_dir = agent_registry.package_dir(agent_id)
    files: dict[str, str] = {}

    def _grab(rel: str) -> None:
        p = pkg_dir / rel
        if p.is_file():
            files[rel] = base64.b64encode(p.read_bytes()).decode("ascii")

    for name in _referenced_package_files(agent):
        _grab(name)
    _grab("workflow.py")
    # eval_cases/ 递归全量冻结（Codex R0 审 P1）：iterdir 非递归、只抓直接子文件，会漏
    # 掉 case 的 input_files 引用的嵌套 fixture（如 cfd_evaluate_agent 的
    # fixtures/<run>/postProcessing/.../forceCoeffs.dat）。材化后这些文件缺席，
    # _run_one_case_inner 判「input_files 引用不合法或不存在」令每个此类 case 失败。
    # rglob 保相对路径全量抓，覆盖任意深度 fixture。
    cases_dir = pkg_dir / "eval_cases"
    if cases_dir.is_dir():
        for f in sorted(cases_dir.rglob("*")):
            if f.is_file():
                _grab(f.relative_to(pkg_dir).as_posix())

    # 指纹从冻结字节派生（Codex R0 审 P2）：原实现首遍抓 files、次遍重读活磁盘算
    # digest，两读之间活包被并发改（部署/case 编辑）会让 content 存 A 版字节却配 B 版
    # 指纹，执行侧再从材化 A 字节重算得第三个值——run 记录的 digest 与 GET /snapshot
    # 暴露的 digest 打架。改为把已抓的 files 材化到临时目录、就地 load+算 digest：
    # 「冻结的字节 == 算指纹的字节 == 执行侧材化读的字节」三者恒等，freeze 内部无 TOCTOU。
    with tempfile.TemporaryDirectory(prefix="flai_eval_freeze_") as _td:
        frozen_dir = Path(_td)
        _materialize_snapshot({"files": files}, frozen_dir)
        approved, _drafts, _broken = load_eval_cases(frozen_dir)
        digest = compute_digest(approved, frozen_dir, agent)
    content = {
        "agent_id": agent_id,
        "agent_version": str(agent.get("version")),
        "agent": agent,
        "files": files,
        "eval_cases_digest": digest,
    }
    content_json = json.dumps(content, ensure_ascii=False, sort_keys=True)
    handle = "snap_" + hashlib.sha256(content_json.encode("utf-8")).hexdigest()
    repos.insert_eval_snapshot(
        conn, handle=handle, agent_id=agent_id,
        agent_version=str(agent.get("version")), eval_cases_digest=digest,
        content_json=content_json,
    )
    return handle


def enqueue_eval_run(
    conn: Any,
    *,
    agent_registry: Any,
    agent_id: str,
    triggered_by: str,
) -> dict[str, Any]:
    """入队一次评测跑批（T1，GH #2）：建 status='queued' 的 eval_run 立即返回，
    真正执行交给 worker（配额门内认领 queued→running）。调用方保证 agent 已注册
    （API 层 404 前置）。agent_version 在入队时刻从活注册表采样落库。

    T2/#5：入队瞬间冻结不可变快照并把 run 绑定其 handle——执行读快照材化而非活磁盘，
    enqueue 后改活包对该 run 无影响。"""
    agent = agent_registry.get(agent_id)
    if agent is None:
        raise ValueError(f"agent 不存在：{agent_id}")
    snapshot_handle = freeze_eval_snapshot(conn, agent_registry=agent_registry, agent_id=agent_id)
    run_id = f"eval_{uuid.uuid4().hex}"
    return repos.create_eval_run(
        conn, run_id=run_id, agent_id=agent_id,
        agent_version=str(agent.get("version")), triggered_by=triggered_by,
        status="queued", snapshot_handle=snapshot_handle,
    )


def run_agent_evals(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    runtime: Any,
    uploads_dir: Path,
    task_runs_dir: Path,
    agent_id: str,
    triggered_by: str,
) -> dict[str, Any]:
    """同步跑一个 agent 的全部 eval_cases 到终态，返回终态 eval_run dict。

    = 建 status='running' 的 run + 立即 `execute_eval_run`（不入队、不经 worker）。
    T1 起生产入口改异步（API 走 enqueue_eval_run + worker）；本函数保留作
    「立即跑完拿终态」的同步便捷（测试与需要内联结果处），已去除原 single-flight
    锁——并发控制归 worker 配额门。调用方保证 agent 已注册（API 层 404 前置）。

    已知限制（Codex R2 复审 P2，显式接受入 retro）：本同步路径直建 running 不经
    `claim_next_queued_eval_run` 的配额门，故与 worker 并发时评测配额不是全局硬上限
    ——promote_agent_l1.py 之类 CLI 可在 worker 满额时另起一评测。这是刻意的：CLI
    须能在**无 worker 独立进程**下跑（走队列会因无人排空而死等）；配额语义定为「worker
    并发上限」而非「跨所有入口的全局资源硬闸」。CLI 评测是操作者审慎的单发动作，非高
    并发面。若未来需全局硬闸，另开工单加「CLI 也走配额预留」而非在此埋隐性队列依赖。
    """
    agent = agent_registry.get(agent_id)
    if agent is None:
        raise ValueError(f"agent 不存在：{agent_id}")
    run_id = f"eval_{uuid.uuid4().hex}"
    conn = conn_factory()
    try:
        repos.create_eval_run(
            conn, run_id=run_id, agent_id=agent_id,
            agent_version=str(agent.get("version")), triggered_by=triggered_by,
            status="running",
        )
    finally:
        conn.close()
    return execute_eval_run(
        run_id=run_id,
        conn_factory=conn_factory,
        agent_registry=agent_registry,
        runtime=runtime,
        uploads_dir=uploads_dir,
        task_runs_dir=task_runs_dir,
    )


class _SnapshotRegistry:
    """只读注册表 shim（T2/#5）：对被评测 agent 返回快照冻结的解析配置与材化包目录，
    其余 agent 委托活注册表。让执行（含 runtime 的 workflow/schema 定位）读冻结内容而非
    活磁盘——enqueue 后改活包对本 run 无影响。"""

    def __init__(self, base: Any, agent_id: str, frozen_agent: dict[str, Any], materialized_dir: Path) -> None:
        self._base = base
        self._agent_id = agent_id
        self._frozen_agent = frozen_agent
        self._dir = materialized_dir

    def get(self, agent_id: str) -> Any:
        return self._frozen_agent if agent_id == self._agent_id else self._base.get(agent_id)

    def package_dir(self, agent_id: str) -> Any:
        return self._dir if agent_id == self._agent_id else self._base.package_dir(agent_id)

    def __getattr__(self, name: str) -> Any:  # 其余方法（list/scan/deregister…）委托活注册表
        return getattr(self._base, name)


def _materialize_snapshot(content: dict[str, Any], dest_dir: Path) -> None:
    """把快照冻结的包文件（base64）还原到临时目录，保持相对路径（agent.yaml/workflow.py/
    schemas/eval_cases/* 等），供执行读取。"""
    for rel, b64 in content.get("files", {}).items():
        p = dest_dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(base64.b64decode(b64))


def _clone_runtime_with_registry(runtime: Any, registry: Any) -> Any:
    """克隆运行时、仅替换 agent_registry（T2/#5）：runtime.execute 用其 agent_registry
    定位 workflow.py / schema，必须指向快照材化目录才能读冻结代码/配置。其余依赖
    （tool_registry/model_gateway/conn_factory/dirs/knowledge/scope）原样复用。"""
    from ..runtime.runtime import AgentRuntime

    return AgentRuntime(
        agent_registry=registry,
        tool_registry=runtime.tool_registry,
        model_gateway=runtime.model_gateway,
        conn_factory=runtime.conn_factory,
        task_runs_dir=runtime.task_runs_dir,
        knowledge_service=runtime.knowledge_service,
        uploads_dir=runtime.uploads_dir,
        scope_registry=runtime.scope_registry,
    )


def execute_eval_run(
    *,
    run_id: str,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    runtime: Any,
    uploads_dir: Path,
    task_runs_dir: Path,
) -> dict[str, Any]:
    """执行一个**已建行且处于 running 态**的 eval_run（T1，GH #2）。

    T2/#5：若 run 绑定不可变快照，把快照材化到临时目录 + 用快照绑定的注册表/运行时
    执行——读冻结内容而非活磁盘，enqueue 后改活包对本 run 无影响。无快照（旧行/同步
    路径未冻结）回退活注册表读活磁盘（向后兼容）。真正的执行核在 `_run_eval_body`。
    """
    conn = conn_factory()
    try:
        run = repos.get_eval_run(conn, run_id)
    finally:
        conn.close()
    if run is None:
        raise ValueError(f"eval_run 不存在：{run_id}")
    agent_id = run["agent_id"]
    triggered_by = run["triggered_by"]

    snapshot_handle = run.get("snapshot_handle")
    if not snapshot_handle:
        return _run_eval_body(
            run=run, run_id=run_id, agent_id=agent_id, triggered_by=triggered_by,
            conn_factory=conn_factory, agent_registry=agent_registry, runtime=runtime,
            uploads_dir=uploads_dir, task_runs_dir=task_runs_dir,
        )

    conn = conn_factory()
    try:
        snap = repos.get_eval_snapshot(conn, snapshot_handle)
    finally:
        conn.close()
    if snap is None:
        # 绑定的快照丢失=证据不可信，fail-closed 收口 error（绝不回退活磁盘伪装成功）
        conn = conn_factory()
        try:
            return repos.finish_eval_run(
                conn, run_id, status="error", total=0, passed=0, failed=0, skipped=0,
                case_results=[{
                    "case_file": "<runner>", "verdict": "failed",
                    "detail": f"绑定的不可变快照缺失，证据不可信：{snapshot_handle}",
                }],
                draft_cases=[], eval_cases_digest=None,
            )
        finally:
            conn.close()

    content = json.loads(snap["content_json"])
    with tempfile.TemporaryDirectory(prefix="flai_eval_snap_") as _td:
        materialized = Path(_td)
        _materialize_snapshot(content, materialized)
        shim_registry = _SnapshotRegistry(agent_registry, agent_id, content["agent"], materialized)
        shim_runtime = _clone_runtime_with_registry(runtime, shim_registry)
        return _run_eval_body(
            run=run, run_id=run_id, agent_id=agent_id, triggered_by=triggered_by,
            conn_factory=conn_factory, agent_registry=shim_registry, runtime=shim_runtime,
            uploads_dir=uploads_dir, task_runs_dir=task_runs_dir,
        )


def _run_eval_body(
    *,
    run: dict[str, Any],
    run_id: str,
    agent_id: str,
    triggered_by: str,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    runtime: Any,
    uploads_dir: Path,
    task_runs_dir: Path,
) -> dict[str, Any]:
    """评测执行核（活磁盘或快照材化均复用）：agent 解析 → 版本守卫 → 跑全部 approved
    case → 起终点 digest 复核 → 收口。agent_registry/runtime 由 execute_eval_run 决定是
    活注册表还是快照绑定的 shim。任何意外异常先收口 error 再上抛，绝不留僵尸 running。"""
    agent = agent_registry.get(agent_id)
    if agent is None:
        conn = conn_factory()
        try:
            return repos.finish_eval_run(
                conn, run_id, status="error", total=0, passed=0, failed=0, skipped=0,
                case_results=[{
                    "case_file": "<runner>", "verdict": "failed",
                    "detail": f"agent 在评测执行前已消失：{agent_id}",
                }],
                draft_cases=[], eval_cases_digest=None,
            )
        finally:
            conn.close()

    # 版本漂移拒执（P1，Codex R1 审）：agent_version 在入队时刻由 API 侧注册表采样落库，
    # 执行发生在 worker 进程、读 worker 侧活注册表。只重启一侧的分离部署会让二者分叉——
    # 若仍用 worker 版本执行却贴入队版本标签，证据链就认证了错误版本（digest 只哈希 case
    # 与引用文件内容，model/tools/review 等 yaml 字段改动+文件名不变会漏网，可让错版本过
    # 晋升门）。fail-closed 收口 error，交由部署对齐后重新入队。同步路径入队与执行同一注册
    # 表同一瞬间，version 恒等，不会误伤。
    enqueued_version = run.get("agent_version")
    live_version = str(agent.get("version"))
    if enqueued_version is not None and str(enqueued_version) != live_version:
        conn = conn_factory()
        try:
            return repos.finish_eval_run(
                conn, run_id, status="error", total=0, passed=0, failed=0, skipped=0,
                case_results=[{
                    "case_file": "<runner>", "verdict": "failed",
                    "detail": f"agent 版本漂移：入队登记 {enqueued_version!r} ≠ worker 执行时活版本 "
                              f"{live_version!r}（API/worker 分离部署未同步）；拒以错版本认证评测",
                }],
                draft_cases=[], eval_cases_digest=None,
            )
        finally:
            conn.close()

    case_results: list[dict[str, Any]] = []
    passed = failed = skipped = 0
    digest: str | None = None
    drafts: list[dict[str, Any]] = []
    try:
        # 整段 prelude 纳入 try（P1，Codex R1 审）：package_dir / load_eval_cases /
        # compute_digest 抛异常（注册表故障、畸形 case、包 I/O、input_files 非法类型等）
        # 此前落在保护范围外，会让 worker 已认领的行永久停 running 泄配额。纳入后与 case
        # 循环统一 fail-closed 收口 error。
        pkg_dir = agent_registry.package_dir(agent_id)
        is_interactive = (agent.get("workflow") or {}).get("mode") == "interactive"
        approved, drafts, broken = load_eval_cases(pkg_dir)
        digest = compute_digest(approved, pkg_dir, agent)
        for item in broken:
            failed += 1
            case_results.append(
                {"case_file": item["_file"], "verdict": "failed", "detail": item["error"]}
            )

        for case in approved:
            case_file = case["_file"]
            checks = case.get("checks")
            if is_interactive:
                skipped += 1
                case_results.append({
                    "case_file": case_file, "verdict": "skipped",
                    "detail": "interactive 型 Agent 不在本批 runner 覆盖内（会话评测属人工评审集，V0.2）",
                })
                continue
            if not isinstance(checks, list) or len(checks) == 0:
                skipped += 1
                case_results.append({
                    "case_file": case_file, "verdict": "skipped",
                    "detail": "case 无 checks 块，机器不可判定（不计入 passed）",
                })
                continue
            result = _run_one_case(
                conn_factory=conn_factory,
                runtime=runtime,
                uploads_dir=uploads_dir,
                task_runs_dir=task_runs_dir,
                pkg_dir=pkg_dir,
                agent=agent,
                case=case,
                triggered_by=triggered_by,
            )
            case_results.append(result)
            if result["verdict"] == "passed":
                passed += 1
            else:
                failed += 1
    except Exception as exc:  # noqa: BLE001 - 意外异常：run 收口 error 再上抛，绝不留僵尸 running
        logger.exception("eval run %s 意外中断", run_id)
        conn = conn_factory()
        try:
            repos.finish_eval_run(
                conn, run_id,
                status="error",
                total=passed + failed + skipped, passed=passed, failed=failed, skipped=skipped,
                case_results=case_results + [
                    {"case_file": "<runner>", "verdict": "failed", "detail": f"runner 意外中断：{exc}"}
                ],
                draft_cases=[],
                eval_cases_digest=digest,
            )
        finally:
            conn.close()
        raise

    total = passed + failed + skipped
    draft_list = [
        {"case_file": d["_file"], "detail": "curation=draft，待 Eval 维护者策展后生效"}
        for d in drafts
    ]

    # run 后复核（异源审 F3）：digest 在 run 起点采样，若执行期间 approved case/
    # 引用文件/包文件被改，起点指纹与实际执行对象已分叉——证据一律作废
    # （status='error'），绝不把「哈希的是 A、跑的是 B」的 run 交给晋升门。
    # 复核自身失败（并发删除/权限/畸形引用）同样按证据作废收口（R2 残余：
    # 复核路径此前在保护范围外，抛异常会让 run 永久停 running）。
    try:
        post_approved, _post_drafts, _post_broken = load_eval_cases(pkg_dir)
        post_digest = compute_digest(post_approved, pkg_dir, agent)
    except Exception as exc:  # noqa: BLE001 - 复核不可得=证据不可信，fail-closed 作废
        logger.exception("eval run %s 终点复核失败", run_id)
        post_digest = f"<recheck-failed:{exc}>"
    if post_digest != digest:
        conn = conn_factory()
        try:
            return repos.finish_eval_run(
                conn, run_id,
                status="error",
                total=total, passed=passed, failed=failed, skipped=skipped,
                case_results=case_results + [{
                    "case_file": "<runner>", "verdict": "failed",
                    "detail": "执行期间评测集或包内容发生变化，本次证据作废（digest 起终点不一致）",
                }],
                draft_cases=draft_list,
                eval_cases_digest=None,
            )
        finally:
            conn.close()

    conn = conn_factory()
    try:
        return repos.finish_eval_run(
            conn, run_id,
            status="completed",
            total=total, passed=passed, failed=failed, skipped=skipped,
            case_results=case_results,
            draft_cases=draft_list,
            eval_cases_digest=digest,
        )
    finally:
        conn.close()


def _run_one_case(
    *,
    conn_factory: Callable[[], Any],
    runtime: Any,
    uploads_dir: Path,
    task_runs_dir: Path,
    pkg_dir: Path,
    agent: dict[str, Any],
    case: dict[str, Any],
    triggered_by: str,
) -> dict[str, Any]:
    """单 case：建 origin='eval' 任务 → claim → 真实 runtime.execute → checks 判定。

    整体兜底：任一环节异常（含建任务/文件登记的 DB 错误）都按本 case failed
    如实记账，绝不炸穿整个 run（异源审 P2-7）。
    """
    case_file = case["_file"]
    agent_id = agent["id"]
    try:
        return _run_one_case_inner(
            conn_factory=conn_factory, runtime=runtime, uploads_dir=uploads_dir,
            task_runs_dir=task_runs_dir, pkg_dir=pkg_dir, agent=agent, case=case,
            triggered_by=triggered_by,
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("eval case %s 环节异常", case_file)
        return {
            "case_file": case_file, "verdict": "failed",
            "detail": f"case 执行环节异常：{exc}",
        }


def _run_one_case_inner(
    *,
    conn_factory: Callable[[], Any],
    runtime: Any,
    uploads_dir: Path,
    task_runs_dir: Path,
    pkg_dir: Path,
    agent: dict[str, Any],
    case: dict[str, Any],
    triggered_by: str,
) -> dict[str, Any]:
    case_file = case["_file"]
    agent_id = agent["id"]

    conn = conn_factory()
    try:
        # 注册 case 声明的输入文件：复制进 uploads（与上传端点同一落盘形态），
        # 绝不让任务产物链反向引用 agent 包目录。
        input_file_ids: list[str] = []
        for rel_name in case.get("input_files", []) or []:
            src = (pkg_dir / "eval_cases" / rel_name).resolve()
            eval_cases_root = (pkg_dir / "eval_cases").resolve()
            if eval_cases_root not in src.parents or not src.is_file():
                return {
                    "case_file": case_file, "verdict": "failed",
                    "detail": f"input_files 引用不合法或不存在：{rel_name!r}（只允许 eval_cases/ 内文件）",
                }
            file_id = str(uuid.uuid4())
            dest_dir = uploads_dir / file_id
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / src.name
            shutil.copyfile(src, dest)
            repos.create_file(
                conn,
                file_id=file_id,
                task_id=None,
                kind="input",
                filename=src.name,
                path=str(dest),
                size_bytes=dest.stat().st_size,
                sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),
                # eval case 内容经人工放行+策展双关（ADR-0018），包内数据 internal
                # 是治理流程的构造性口径（ADR-0021 D3）；非人工上传，uploaded_by 留 NULL。
                classification="internal",
            )
            input_file_ids.append(file_id)

        task_id = f"task_{uuid.uuid4().hex}"
        repos.create_task(
            conn,
            task_id=task_id,
            agent_id=agent_id,
            agent_version=str(agent.get("version")),
            name=f"eval:{case_file}",
            created_by=triggered_by,
            inputs=case.get("inputs") or {},
            input_file_ids=input_file_ids,
            metadata={"eval_case_file": case_file},
            origin="eval",
        )
        repos.set_task_status(conn, task_id, "queued")
        claimed = repos.claim_task(conn, task_id)
    finally:
        conn.close()

    if claimed is None:
        # fail-closed：认领失败（理论上不可能——worker 候选集不含 eval 任务）
        # 绝不带病继续，按 case 失败如实记账。
        return {
            "case_file": case_file, "verdict": "failed", "task_id": task_id,
            "detail": "eval 任务认领失败（queued→validating 未成立），按失败记账",
        }

    try:
        runtime.execute(task_id)
    except Exception as exc:  # noqa: BLE001 - 单 case 崩溃不摧毁整个 run，如实记账
        logger.exception("eval case %s 执行异常", case_file)
        # 异源审 F4：任务不许停在执行态（validating/running/…）成非终态孤儿——
        # best-effort 置 failed（与 Job Runner 对用户任务的兜底同款语义）。
        try:
            conn = conn_factory()
            try:
                repos.fail_task_from_execution(
                    conn, task_id, f"eval 执行异常：{exc}"
                )
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - 兜底失败只留痕，不遮蔽原始异常语境
            logger.exception("eval 任务 %s 终态化兜底失败", task_id)
        return {
            "case_file": case_file, "verdict": "failed", "task_id": task_id,
            "detail": f"runtime.execute 异常：{exc}",
        }

    conn = conn_factory()
    try:
        final_task = repos.get_task(conn, task_id)
        if final_task is None:
            return {
                "case_file": case_file, "verdict": "failed", "task_id": task_id,
                "detail": "执行后任务行消失（不可能路径），按失败记账",
            }
        output_files = repos.list_files_by_ids(conn, final_task.get("output_file_ids", []))
    finally:
        conn.close()

    check_details: list[dict[str, Any]] = []
    all_ok = True
    for check in case["checks"]:
        try:
            ok, detail = _eval_one_check(
                check, final_task=final_task, output_files=output_files,
                task_runs_dir=task_runs_dir,
            )
        except CheckConfigError as exc:
            # D3：配置坏掉 → case failed，绝不空洞通过
            check_details.append({"ok": False, "detail": f"check 配置错误：{exc}"})
            all_ok = False
            continue
        check_details.append({"ok": ok, "detail": detail})
        if ok is not True:
            all_ok = False

    return {
        "case_file": case_file,
        "verdict": "passed" if all_ok is True else "failed",
        "task_id": task_id,
        "task_status": final_task.get("status"),
        "checks": check_details,
    }
