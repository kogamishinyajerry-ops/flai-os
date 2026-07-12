"""Agent Registry：扫描 agents/ 目录、校验包完整性、同步进 DB（docs/02）。

规则来源：
- docs/02_Agent_Package_Standard.md §1 强制目录形态 + §3 limitations 强制规则。
- 该文档明示：「缺失 agent.yaml 或 schema 校验不通过的目录，一律不注册、
  不报错崩溃，仅在 Registry 日志中标记为无效包」——因此单包缺件/校验失败
  走 `.errors` 软记录路径，`scan()` 继续处理其余包；只有**重复 id** 是硬错误，
  直接抛出中止整次扫描（与 Tool Registry 同族语义，任务书 M1 契约明定）。
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError, validate

from ..core.errors import DuplicateAgentIdError, InvalidPackageError

# docs/02 §1 目录形态：除 agent.yaml 外的强制文件/目录（固定名，标准包形态图示）。
_REQUIRED_FILES: tuple[str, ...] = (
    "prompt.md",
    "workflow.py",
    "input_schema.json",
    "output_schema.json",
    "README.md",
    "changelog.md",
)
_REQUIRED_DIRS: tuple[str, ...] = ("eval_cases",)


class AgentRegistry:
    """扫描 `agents_dir` 下的 Agent Package，维护内存注册表并可同步进 DB。"""

    def __init__(self, agents_dir: str | Path, schema_path: str | Path) -> None:
        self.agents_dir = Path(agents_dir)
        self.schema_path = Path(schema_path)
        self._schema: dict[str, Any] = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self._agents: dict[str, dict[str, Any]] = {}
        self._dirs: dict[str, Path] = {}
        self.errors: list[dict[str, str]] = []

    def adopt(self, other: "AgentRegistry") -> None:
        """原子采纳另一实例的扫描结果（M10/ADR-0018 异源审 F1）。

        运行期重扫必须先在影子实例上完成 scan+reconcile，再一次性发布到
        活注册表——直接对活实例 scan 会先清空再逐项重建，期间其他请求线程
        可短暂读到部分注册表、甚至读到本应被 knowledge 对账注销的 Agent。

        发布序（R2 残余加固）：_dirs/errors 先行、_agents 收尾——_agents 是
        全部读者的入口（get/list），一个在 _agents 可见的 id 必已有对应 dir。
        单次 get() 或 package_dir() 各自原子；跨两次调用横跨发布点的读者可能
        新旧混读（dict 与 dir 同键、路径恒同，无既知危害路径）——完整快照
        句柄 API 是 V0.2 槽位（ADR-0018 已声明限制）。
        """
        self._dirs = other._dirs
        self.errors = other.errors
        self._agents = other._agents

    def scan(self) -> None:
        """重新扫描 agents_dir，覆盖式重建内存注册表（幂等：可重复调用）。"""
        self._agents = {}
        self._dirs = {}
        self.errors = []
        if not self.agents_dir.is_dir():
            return
        for entry in sorted(self.agents_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                data = self._load_one(entry)
            except InvalidPackageError as exc:
                self.errors.append({"path": str(entry), "error": str(exc)})
                continue
            agent_id = data["id"]
            if agent_id in self._agents:
                raise DuplicateAgentIdError(
                    f"重复的 Agent id: {agent_id!r}（{entry} 与 {self._dirs[agent_id]} 冲突）"
                )
            self._agents[agent_id] = data
            self._dirs[agent_id] = entry

    def _load_one(self, entry: Path) -> dict[str, Any]:
        yaml_path = entry / "agent.yaml"
        if not yaml_path.is_file():
            raise InvalidPackageError(f"{entry} 缺少 agent.yaml")
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise InvalidPackageError(f"{entry} agent.yaml 解析失败：{exc}") from exc
        if not isinstance(data, dict):
            raise InvalidPackageError(f"{entry} agent.yaml 顶层必须是 object")
        try:
            validate(data, self._schema)
        except ValidationError as exc:
            raise InvalidPackageError(f"{entry} agent.yaml 未通过 agent.schema.json 校验：{exc.message}") from exc

        missing = [f for f in _REQUIRED_FILES if not (entry / f).is_file()]
        missing += [f"{d}/" for d in _REQUIRED_DIRS if not (entry / d).is_dir()]
        if missing:
            raise InvalidPackageError(f"{entry} 缺少 docs/02 强制件：{', '.join(missing)}")

        # P2-7：trial/released 禁 TBD——agent.schema.json 对 owner.maintainer/
        # business_reviewer 的字段说明早已承诺"trial 及以上状态禁止 TBD"，本处
        # 是该承诺在 Registry 扫描侧的落地校验（jsonschema 本身无法表达"某枚举值
        # 组合下另一字段不得为某常量"这类跨字段条件，故在 Python 侧补）。
        status = data.get("status")
        owner = data.get("owner", {}) or {}
        if status in ("trial", "released") and (
            owner.get("maintainer") == "TBD" or owner.get("business_reviewer") == "TBD"
        ):
            raise InvalidPackageError(
                f"{entry} status={status!r} 但 owner.maintainer/business_reviewer 仍为 TBD"
                "（trial 及以上状态禁止 TBD，agent.schema.json owner 字段说明的强制校验）"
            )
        return data

    def get(self, agent_id: str) -> dict[str, Any] | None:
        """按 id 取已注册 Agent 的 agent.yaml 解析结果；未注册返回 None（不抛异常）。"""
        return self._agents.get(agent_id)

    def deregister(self, agent_id: str, reason: str) -> None:
        """把已注册 Agent 移出注册表并记录原因（ADR-0015 knowledge scope 启动对账用）。

        fail-closed 出口：对账不过的 Agent 从此 get/list 均不可见，create_task 对其
        404。只动内存注册表；装配顺序上 deregister 必须发生在 sync_to_db 之前，
        使 DB agents 表不再 upsert 该 id（历史行保留，属审计痕迹非可调用入口）。
        未注册 id 调用为 no-op（幂等，重扫场景安全）。
        """
        if agent_id not in self._agents:
            return
        entry = self._dirs.get(agent_id)
        del self._agents[agent_id]
        self._dirs.pop(agent_id, None)
        self.errors.append({"path": str(entry) if entry else agent_id, "error": reason})

    def list(self) -> list[dict[str, Any]]:
        return list(self._agents.values())

    def package_dir(self, agent_id: str) -> Path | None:
        """取 Agent 包所在目录（Runtime 定位 workflow.py / *_schema.json 用）。

        注：M1 接口契约未列出本方法，是 Runtime 依赖包目录定位 workflow.py
        的必要补充，随 `.get()/.list()` 一起在 `scan()` 后可用，同一扫描周期
        内与 `.get(agent_id)` 返回的 yaml 数据一一对应。
        """
        return self._dirs.get(agent_id)

    def sync_to_db(self, conn: sqlite3.Connection) -> None:
        """把内存注册表写入 agents 表（upsert）+ agent_versions 表（追加，UNIQUE 冲突忽略）。

        重复调用（重扫幂等）：agents 表按 id 覆盖式更新但保留首次 registered_at；
        agent_versions 按 (agent_id, version) 唯一约束，已存在的版本不重复插入。
        """
        now = datetime.now(timezone.utc).isoformat()
        for agent_id, data in self._agents.items():
            yaml_json = json.dumps(data, ensure_ascii=False)
            conn.execute(
                """
                INSERT INTO agents (id, name, version, status, maturity, category, summary, yaml_json, registered_at)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET
                    name = excluded.name,
                    version = excluded.version,
                    status = excluded.status,
                    maturity = excluded.maturity,
                    category = excluded.category,
                    summary = excluded.summary,
                    yaml_json = excluded.yaml_json
                """,
                (
                    agent_id, data["name"], data["version"], data["status"], data["maturity"],
                    data["category"], data["summary"], yaml_json, now,
                ),
            )
            conn.execute(
                """
                INSERT INTO agent_versions (agent_id, version, yaml_json, created_at)
                VALUES (?,?,?,?)
                ON CONFLICT(agent_id, version) DO NOTHING
                """,
                (agent_id, data["version"], yaml_json, now),
            )
