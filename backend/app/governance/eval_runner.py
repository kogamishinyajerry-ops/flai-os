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

import hashlib
import json
import logging
import shutil
import threading
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

# 同步执行的 single-flight（异源审 P2-10）：同一 agent 同时只许一个 eval run，
# 防重复请求耗尽工作线程与 SQLite 写锁。进程内锁——多进程部署是 V0.1 已声明限制。
_EVAL_LOCKS: dict[str, threading.Lock] = {}
_EVAL_LOCKS_GUARD = threading.Lock()


class EvalBusy(Exception):
    """该 agent 已有 eval run 在执行（API 层映射 409）。"""


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
    """跑一个 agent 的全部 eval_cases，返回终态 eval_run dict。

    调用方保证 agent 已注册（API 层 404 前置）。同步执行（V0.1 已声明限制：
    无异步队列，case 数小）。同一 agent single-flight：并发触发抛 EvalBusy。
    任何意外异常都先把 run 收口为 status='error' 再上抛——绝不留永久 running
    的僵尸证据（异源审 P2-7/P2-10）。
    """
    with _EVAL_LOCKS_GUARD:
        lock = _EVAL_LOCKS.setdefault(agent_id, threading.Lock())
    if lock.acquire(blocking=False) is not True:
        raise EvalBusy(f"agent {agent_id} 已有评测在执行，请等它结束")
    try:
        return _run_agent_evals_locked(
            conn_factory=conn_factory,
            agent_registry=agent_registry,
            runtime=runtime,
            uploads_dir=uploads_dir,
            task_runs_dir=task_runs_dir,
            agent_id=agent_id,
            triggered_by=triggered_by,
        )
    finally:
        lock.release()


def _run_agent_evals_locked(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    runtime: Any,
    uploads_dir: Path,
    task_runs_dir: Path,
    agent_id: str,
    triggered_by: str,
) -> dict[str, Any]:
    agent = agent_registry.get(agent_id)
    if agent is None:
        raise ValueError(f"agent 不存在：{agent_id}")
    pkg_dir = agent_registry.package_dir(agent_id)
    agent_version = str(agent.get("version"))
    is_interactive = (agent.get("workflow") or {}).get("mode") == "interactive"

    approved, drafts, broken = load_eval_cases(pkg_dir)
    digest = compute_digest(approved, pkg_dir, agent)

    run_id = f"eval_{uuid.uuid4().hex}"
    conn = conn_factory()
    try:
        repos.create_eval_run(
            conn, run_id=run_id, agent_id=agent_id,
            agent_version=agent_version, triggered_by=triggered_by,
        )
    finally:
        conn.close()

    case_results: list[dict[str, Any]] = []
    passed = failed = skipped = 0
    try:
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
