"""样本→评测集固化通道（M10 治理闭环，ADR-0018 §2）。

把工程师审核认可（accepted_by_engineer == True）的样本固化为
`agents/<id>/eval_cases/case_NNN_from_sample.json`——每次人工审核从
「放行动作」变为「数据资产定标动作」。

诚实边界（loop-auditor 设计审 D7 落地）：
- 生成物一律 `curation: "draft"`——工程师 approve 的语义是「放行交付」，
  不是「逐字段核对为精确正确」；自动生成的断言必须经 Eval 维护者策展
  改 `approved` 后才进入正式评测集（eval runner 对 draft 不执行不计数）。
- 自动 checks 只生成有据可查的最低断言（status_is completed + 原任务真实
  产物的 artifact_exists），样本输出原文放 `sample_output` 供策展者参考，
  绝不自动编造字段级 eq 金标准。
- 原任务含输入文件的样本拒绝自动固化（不静默把用户上传数据搬进版本化的
  agent 包目录）——需人工落文件，V0.1 已声明限制。
- 幂等：同一 sample 已固化 → SampleAlreadyFixed 携既有文件名（provenance
  对账，绝不重复生成）。
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..storage import repos

logger = logging.getLogger(__name__)

_CASE_NUM_RE = re.compile(r"^case_(\d+)")

# 固化串行化（异源审 P2-9）：provenance 扫描与编号分配到写盘之间无竞态；
# 写盘用 'x' 独占创建双保险。跨进程锁是 V0.1 已声明限制。
_CURATION_LOCK = threading.Lock()


class CurationError(Exception):
    """固化前置不满足（API 层映射 422）。"""


class SampleAlreadyFixed(Exception):
    """该样本已固化过（API 层映射 409）。"""

    def __init__(self, case_file: str) -> None:
        self.case_file = case_file
        super().__init__(f"样本已固化为 {case_file}，拒绝重复生成")


class SampleNotFound(CurationError):
    """sample id 不存在（API 层映射 404）。"""


class SampleAcknowledgementConflict(CurationError):
    """sample 已有不可覆盖的人工拒绝/冲突证据（API 层映射 409）。"""


class CurationPackageConflict(CurationError):
    """live Agent Package 当前不可写（L1 或 promotion latch，API 映射 409）。"""


@dataclass(frozen=True, slots=True)
class SampleAcknowledgementResult:
    """公开响应与内部 CAS outcome 分离，避免改变幂等 HTTP 资源表示。"""

    record: dict[str, Any]
    created: bool


def _load_curation_context(
    *,
    conn: Any,
    agent_registry: Any,
    agent_id: str,
    sample_id: int,
    require_accepted: bool,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], Path]:
    try:
        agent = agent_registry.get(agent_id)
    except KeyError:
        agent = None
    if agent is None:
        raise CurationError(f"agent 不存在：{agent_id}")
    pkg_dir = agent_registry.package_dir(agent_id)
    if pkg_dir is None:
        raise CurationError(f"agent {agent_id} 的包目录不可用，拒绝 curation")
    cases_dir = pkg_dir / "eval_cases"

    sample = repos.get_sample(conn, sample_id)
    if sample is None:
        raise SampleNotFound(f"样本不存在：{sample_id}")
    if sample["agent_id"] != agent_id:
        raise CurationError(
            f"样本 {sample_id} 属于 agent {sample['agent_id']!r}，不属于 {agent_id!r}"
        )
    if require_accepted is True and sample.get("accepted_by_engineer") is not True:
        raise CurationError(
            f"样本 {sample_id} 未经工程师认可（accepted_by_engineer="
            f"{sample.get('accepted_by_engineer')!r}），拒绝固化"
        )
    # 分级固化门（ADR-0021 D5，internal-allowlist）：eval_cases 是版本化
    # agent 包目录，sensitive 内容入包=脱离 DB 门控的静默离场通道。
    if sample.get("classification") != "internal":
        raise CurationError(
            f"样本 {sample_id} 分级 {sample.get('classification')!r} 非 internal，"
            "拒绝固化入版本化包目录（ADR-0021 D5，fail-closed）"
        )
    task = repos.get_task(conn, sample["task_id"])
    if task is None:
        raise CurationError(f"样本 {sample_id} 的源任务不存在：{sample['task_id']}")
    if task.get("input_file_ids"):
        raise CurationError(
            "源任务含输入文件，V0.1 不自动把用户上传数据搬进 agent 包目录"
            "（需 Eval 维护者人工落文件后手写 case）"
        )
    output_files = repos.list_files_by_ids(conn, task.get("output_file_ids", []))
    return sample, task, output_files, cases_dir


def _scan_cases(
    cases_dir: Path,
    sample_id: int,
) -> tuple[Path | None, dict[str, Any] | None, int]:
    """找 provenance.sample_id 对应 case，并算下一编号；重复 provenance fail-closed。"""
    matches: list[tuple[Path, dict[str, Any]]] = []
    next_num = 1
    for path in sorted(cases_dir.glob("*.json")):
        m = _CASE_NUM_RE.match(path.stem)
        if m is not None:
            next_num = max(next_num, int(m.group(1)) + 1)
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CurationPackageConflict(
                f"eval case {path.name} 无法读取或不是合法 JSON；"
                "拒绝继续写 live package，须先人工修复"
            ) from exc
        if isinstance(existing, dict):
            prov = existing.get("provenance")
            if isinstance(prov, dict) and prov.get("sample_id") == sample_id:
                matches.append((path, existing))
    if len(matches) > 1:
        raise CurationError(
            f"样本 {sample_id} 已对应多个 eval case，provenance 冲突，fail-closed"
        )
    if matches:
        return matches[0][0], matches[0][1], next_num
    return None, None, next_num


def _build_case(
    *,
    sample: dict[str, Any],
    output_files: list[dict[str, Any]],
    case_num: int,
    fixed_by: str,
    fixed_at: str,
    curation: str = "draft",
    acknowledged_by_username: str | None = None,
    acknowledged_at: str | None = None,
) -> dict[str, Any]:
    checks: list[dict[str, Any]] = [{"kind": "status_is", "value": "completed"}]
    for output_file in output_files:
        checks.append({"kind": "artifact_exists", "file": output_file["filename"]})
    provenance: dict[str, Any] = {
        "sample_id": sample["id"],
        "task_id": sample["task_id"],
        "agent_version": sample["agent_version"],
        "fixed_by": fixed_by,
        "fixed_at": fixed_at,
    }
    if acknowledged_by_username is not None:
        provenance["acknowledged_by_username"] = acknowledged_by_username
        provenance["acknowledged_at"] = acknowledged_at
    return {
        "case_id": f"case_{case_num:03d}",
        "description": (
            f"由认可样本固化（sample {sample['id']} / 任务 {sample['task_id']}）。"
            "自动 checks 仅含终态与产物存在性最低断言；策展时按 docs/07 口径补强。"
        ),
        "curation": curation,
        "inputs": sample.get("input") or {},
        "checks": checks,
        "sample_output": sample.get("output"),
        "provenance": provenance,
    }


def _case_bytes(case: dict[str, Any]) -> bytes:
    return (json.dumps(case, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _create_bytes_atomically(path: Path, data: bytes) -> None:
    """同目录完整落盘后用 hard-link 原子发布，且绝不覆盖同名既有 case。"""
    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{path.name}.",
        suffix=".tmp",
        dir=path.parent,
    )
    published = False
    try:
        with os.fdopen(fd, "wb") as handle:
            if handle.write(data) != len(data):
                raise OSError(f"case 写入不完整：{path}")
            handle.flush()
            os.fsync(handle.fileno())
        # 同目录 hard-link 创建是 no-clobber：目标已存在时统一 FileExistsError。
        os.link(tmp_name, path)
        published = True
    finally:
        try:
            os.unlink(tmp_name)
        except FileNotFoundError:
            pass
        except OSError:
            # Windows 杀毒/索引器可能短暂占用 temp。目标若已经 hard-link 发布，
            # 清理失败不能把成功发布误报成失败；若发布本身失败，也必须保留
            # 原始异常而不是让 finally 覆盖它。隐藏 temp 不进入 *.json 分类源。
            logger.warning(
                "case 临时文件清理失败；保留 temp 供运维修复 "
                "(published=%s, target=%s, temp=%s)",
                published,
                path,
                tmp_name,
                exc_info=True,
            )


def _assert_package_curation_writable(
    *,
    conn: Any,
    agent_registry: Any,
    agent_id: str,
    sample_agent_version: str,
) -> Path:
    """在 SQLite write lock 内校验 live package 写权，与 promotion latch rendezvous。"""
    if repos.get_promotion_attestation_fault(conn) is not None:
        raise CurationPackageConflict(
            "存在 promotion operation/fault latch，拒绝修改 live Agent Package"
        )
    try:
        registry_agent = agent_registry.get(agent_id)
    except KeyError:
        registry_agent = None
    package_dir = agent_registry.package_dir(agent_id)
    db_agent = conn.execute(
        "SELECT version, maturity FROM agents WHERE id = ?",
        (agent_id,),
    ).fetchone()
    if registry_agent is None or package_dir is None or db_agent is None:
        raise CurationPackageConflict(
            f"agent {agent_id} 的 Registry/DB/package 投影不完整，拒绝 curation"
        )
    registry_version = registry_agent.get("version")
    registry_maturity = registry_agent.get("maturity")
    db_version = db_agent["version"]
    db_maturity = db_agent["maturity"]
    if (
        registry_maturity != "L0"
        or db_maturity != "L0"
        or registry_version != db_version
        or registry_version != sample_agent_version
    ):
        raise CurationPackageConflict(
            f"agent {agent_id} live package 不可写："
            f"registry={registry_version}/{registry_maturity}, "
            f"db={db_version}/{db_maturity}, sample={sample_agent_version}"
        )
    return Path(package_dir)


def fix_sample_as_eval_case(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    agent_id: str,
    sample_id: int,
    fixed_by: str,
) -> dict[str, Any]:
    """固化一条认可样本为 draft eval case，返回 {case_file, path, case}。"""
    with _CURATION_LOCK:
        return _fix_locked(
            conn_factory=conn_factory, agent_registry=agent_registry,
            agent_id=agent_id, sample_id=sample_id, fixed_by=fixed_by,
        )


def _fix_locked(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    agent_id: str,
    sample_id: int,
    fixed_by: str,
) -> dict[str, Any]:
    conn = conn_factory()
    published_path: Path | None = None
    committed = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        initial_sample = repos.get_sample(conn, sample_id)
        if initial_sample is None:
            raise SampleNotFound(f"样本不存在：{sample_id}")
        if initial_sample.get("agent_id") != agent_id:
            raise CurationError(
                f"样本 {sample_id} 属于 agent "
                f"{initial_sample.get('agent_id')!r}，不属于 {agent_id!r}"
            )
        _assert_package_curation_writable(
            conn=conn,
            agent_registry=agent_registry,
            agent_id=agent_id,
            sample_agent_version=str(initial_sample.get("agent_version") or ""),
        )
        sample, _task, output_files, cases_dir = _load_curation_context(
            conn=conn,
            agent_registry=agent_registry,
            agent_id=agent_id,
            sample_id=sample_id,
            require_accepted=True,
        )
        existing_path, _existing_case, next_num = _scan_cases(cases_dir, sample_id)
        if existing_path is not None:
            raise SampleAlreadyFixed(existing_path.name)
        fixed_at = datetime.now(timezone.utc).isoformat()
        case_file = f"case_{next_num:03d}_from_sample.json"
        case = _build_case(
            sample=sample,
            output_files=output_files,
            case_num=next_num,
            fixed_by=fixed_by,
            fixed_at=fixed_at,
        )
        dest = cases_dir / case_file
        payload = _case_bytes(case)
        _create_bytes_atomically(dest, payload)
        published_path = dest
        conn.execute("COMMIT")
        committed = True
        return {"case_file": case_file, "path": str(dest), "case": case}
    except Exception:
        if conn.in_transaction:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                logger.critical(
                    "eval case 固化 DB 回滚失败；保留原异常并要求人工核查",
                    exc_info=True,
                )
        if published_path is not None and committed is not True:
            logger.critical(
                "eval case 已发布但事务未提交；不做破坏性补偿，"
                "保留 %s 供人工对账",
                published_path,
            )
        raise
    finally:
        conn.close()


def acknowledge_sample(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    sample_id: int,
    actor_username: str,
) -> SampleAcknowledgementResult:
    """认证人按 sample id 认可，并幂等 ensure 一个 draft eval case（Issue #4）。

    draft 会进入与 Promotion 共源的 curation 两态账，但不会直接成为 approved
    金标准；这是 ADR-0018 D7 的假绿防线。首次 actor/时间 CAS-on-NULL，重试
    返回同一资源与首次签发者。
    """
    with _CURATION_LOCK:
        return _acknowledge_locked(
            conn_factory=conn_factory,
            agent_registry=agent_registry,
            sample_id=sample_id,
            actor_username=actor_username,
        )


def _acknowledge_locked(
    *,
    conn_factory: Callable[[], Any],
    agent_registry: Any,
    sample_id: int,
    actor_username: str,
) -> SampleAcknowledgementResult:
    if not isinstance(actor_username, str) or not actor_username.strip():
        raise CurationError("认可人 username 缺失，拒绝 sample 级认可")

    conn = conn_factory()
    published_path: Path | None = None
    committed = False
    try:
        conn.execute("BEGIN IMMEDIATE")
        sample = repos.get_sample(conn, sample_id)
        if sample is None:
            raise SampleNotFound(f"样本不存在：{sample_id}")
        agent_id = str(sample.get("agent_id") or "")
        _assert_package_curation_writable(
            conn=conn,
            agent_registry=agent_registry,
            agent_id=agent_id,
            sample_agent_version=str(sample.get("agent_version") or ""),
        )
        sample, task, output_files, cases_dir = _load_curation_context(
            conn=conn,
            agent_registry=agent_registry,
            agent_id=agent_id,
            sample_id=sample_id,
            require_accepted=False,
        )
        if sample.get("accepted_by_engineer") is False:
            raise SampleAcknowledgementConflict(
                f"样本 {sample_id} 已被人工拒绝，认可不得覆盖既有结论"
            )
        # sample 级认可只打开 requires_review=false 的正常完成样本，或为已完成
        # 任务中的单条样本补精细 curation；waiting_review/failed 不能绕过任务签发。
        if task.get("status") != "completed":
            raise CurationError(
                f"样本 {sample_id} 的源任务状态为 {task.get('status')!r}，"
                "仅 completed 样本可逐条认可"
            )
        if sample.get("validation_status") != "success":
            raise CurationError(
                f"样本 {sample_id} validation_status="
                f"{sample.get('validation_status')!r}，反例固化仍需人工定 checks"
            )

        existing_path, existing_case, next_num = _scan_cases(cases_dir, sample_id)
        db_actor = sample.get("acknowledged_by_username")
        db_at = sample.get("acknowledged_at")
        if (db_actor is None) != (db_at is None):
            raise SampleAcknowledgementConflict(
                f"样本 {sample_id} 的 DB 认可 provenance 不完整，fail-closed"
            )

        case_actor: Any = None
        case_at: Any = None
        if existing_case is not None:
            provenance = existing_case.get("provenance")
            if not isinstance(provenance, dict):
                raise SampleAcknowledgementConflict(
                    f"样本 {sample_id} 的 case provenance 非对象，fail-closed"
                )
            case_actor = provenance.get("acknowledged_by_username")
            case_at = provenance.get("acknowledged_at")

        if db_actor is None:
            if existing_case is not None:
                raise SampleAcknowledgementConflict(
                    f"样本 {sample_id} 的 DB 尚无认可 provenance，"
                    "但 live package 已有对应 case；拒绝在线补签，须人工迁移对账"
                )
            chosen_actor = actor_username
            chosen_at = datetime.now(timezone.utc).isoformat()
            expected_created = True
        else:
            if (
                not isinstance(db_actor, str)
                or not db_actor.strip()
                or not isinstance(db_at, str)
                or not db_at.strip()
                or sample.get("accepted_by_engineer") is not True
            ):
                raise SampleAcknowledgementConflict(
                    f"样本 {sample_id} 的既有 DB 认可 provenance 非法，fail-closed"
                )
            if (
                existing_case is None
                or case_actor != db_actor
                or case_at != db_at
            ):
                raise SampleAcknowledgementConflict(
                    f"样本 {sample_id} 的 DB/case 认可 provenance 不一致，fail-closed"
                )
            chosen_actor = db_actor
            chosen_at = db_at
            expected_created = False
        if (
            not isinstance(chosen_actor, str)
            or not chosen_actor.strip()
            or not isinstance(chosen_at, str)
            or not chosen_at.strip()
        ):
            raise SampleAcknowledgementConflict(
                f"样本 {sample_id} 的既有认可 provenance 非法，fail-closed"
            )

        payload: bytes | None = None
        dest: Path | None = None
        if expected_created is True:
            case_file = f"case_{next_num:03d}_from_sample.json"
            case = _build_case(
                sample=sample,
                output_files=output_files,
                case_num=next_num,
                fixed_by=chosen_actor,
                fixed_at=chosen_at,
                curation="draft",
                acknowledged_by_username=chosen_actor,
                acknowledged_at=chosen_at,
            )
            payload = _case_bytes(case)
            dest = cases_dir / case_file
            curation_state = "draft"
        else:
            if existing_path is None or existing_case is None:
                raise SampleAcknowledgementConflict(
                    f"样本 {sample_id} 的 DB 已有认可，但对应 case 缺失，fail-closed"
                )
            case_file = existing_path.name
            raw_curation = existing_case.get("curation")
            if raw_curation == "draft":
                curation_state = "draft"
            elif raw_curation is None or raw_curation == "approved":
                curation_state = "approved"
            else:
                raise CurationError(
                    f"样本 {sample_id} 对应 case 的 curation="
                    f"{raw_curation!r} 非法，fail-closed"
                )

        try:
            acknowledged, cas_created = repos.acknowledge_sample_once(
                conn,
                sample_id,
                actor_username=chosen_actor,
                acknowledged_at=chosen_at,
            )
        except repos.SampleAcknowledgementConflictError as exc:
            raise SampleAcknowledgementConflict(str(exc)) from exc
        if acknowledged is None:
            raise SampleNotFound(f"样本不存在：{sample_id}")
        if (
            cas_created is not expected_created
            or acknowledged.get("acknowledged_by_username") != chosen_actor
            or acknowledged.get("acknowledged_at") != chosen_at
            or acknowledged.get("accepted_by_engineer") is not True
        ):
            raise SampleAcknowledgementConflict(
                f"样本 {sample_id} 认可写入后证据不一致，fail-closed"
            )
        if cas_created is True:
            if dest is None or payload is None:  # pragma: no cover - 结构防线
                raise SampleAcknowledgementConflict(
                    f"样本 {sample_id} 首签缺少待发布 case，fail-closed"
                )
            _create_bytes_atomically(dest, payload)
            published_path = dest
        conn.execute("COMMIT")
        committed = True
        return SampleAcknowledgementResult(
            record={
                "sample_id": sample_id,
                "agent_id": agent_id,
                "case_file": case_file,
                "curation": curation_state,
                "acknowledged_by_username": chosen_actor,
                "acknowledged_at": chosen_at,
            },
            created=cas_created,
        )
    except Exception:
        if conn.in_transaction:
            try:
                conn.execute("ROLLBACK")
            except Exception:
                logger.critical(
                    "sample 认可 DB 回滚失败；保留原异常并要求人工核查",
                    exc_info=True,
                )
        if published_path is not None and committed is not True:
            logger.critical(
                "sample 认可 case 已发布但 DB 未提交；不做破坏性补偿，"
                "保留 %s 供人工对账",
                published_path,
            )
        raise
    finally:
        conn.close()
