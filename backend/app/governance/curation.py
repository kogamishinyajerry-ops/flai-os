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
import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable

from ..storage import repos

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
    agent = agent_registry.get(agent_id)
    if agent is None:
        raise ValueError(f"agent 不存在：{agent_id}")
    pkg_dir = agent_registry.package_dir(agent_id)
    cases_dir = pkg_dir / "eval_cases"

    conn = conn_factory()
    try:
        sample = repos.get_sample(conn, sample_id)
        if sample is None:
            raise CurationError(f"样本不存在：{sample_id}")
        if sample["agent_id"] != agent_id:
            raise CurationError(
                f"样本 {sample_id} 属于 agent {sample['agent_id']!r}，不属于 {agent_id!r}"
            )
        # 固化门（is True）：只有工程师明确认可的样本才可固化。失败样本反例
        # 固化需人工定口径，V0.2（ADR-0018 已声明限制）。
        if sample.get("accepted_by_engineer") is not True:
            raise CurationError(
                f"样本 {sample_id} 未经工程师认可（accepted_by_engineer="
                f"{sample.get('accepted_by_engineer')!r}），拒绝固化"
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
    finally:
        conn.close()

    # 幂等：provenance.sample_id 对账
    next_num = 1
    for path in sorted(cases_dir.glob("*.json")):
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(existing, dict):
            prov = existing.get("provenance")
            if isinstance(prov, dict) and prov.get("sample_id") == sample_id:
                raise SampleAlreadyFixed(path.name)
        m = _CASE_NUM_RE.match(path.stem)
        if m is not None:
            next_num = max(next_num, int(m.group(1)) + 1)

    checks: list[dict[str, Any]] = [{"kind": "status_is", "value": "completed"}]
    for f in output_files:
        checks.append({"kind": "artifact_exists", "file": f["filename"]})

    case_file = f"case_{next_num:03d}_from_sample.json"
    case: dict[str, Any] = {
        "case_id": f"case_{next_num:03d}",
        "description": (
            f"由认可样本固化（sample {sample_id} / 任务 {sample['task_id']}）。"
            "自动 checks 仅含终态与产物存在性最低断言；策展时按 docs/07 口径补强。"
        ),
        "curation": "draft",
        "inputs": sample.get("input") or {},
        "checks": checks,
        "sample_output": sample.get("output"),
        "provenance": {
            "sample_id": sample_id,
            "task_id": sample["task_id"],
            "agent_version": sample["agent_version"],
            "fixed_by": fixed_by,
            "fixed_at": datetime.now(timezone.utc).isoformat(),
        },
    }
    dest = cases_dir / case_file
    # 'x' 独占创建：即使锁外还有并发写者（多进程），也绝不静默覆盖
    with open(dest, "x", encoding="utf-8") as fh:
        fh.write(json.dumps(case, ensure_ascii=False, indent=2) + "\n")
    return {"case_file": case_file, "path": str(dest), "case": case}
