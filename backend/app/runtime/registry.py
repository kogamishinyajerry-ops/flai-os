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

# output_schema.json 字节上界（Codex R2 P2）：正常输出契约在 KB 量级；病态大/
# 深嵌套 schema（json.loads 可 RecursionError）解析前先挡。
_OUT_SCHEMA_MAX_BYTES = 512 * 1024

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

        # 判决⟹人签 注册期不变量（协作运行时 F3 owner 裁决=注册期不变量）：
        # 作为 job 任务运行且调 LLM（profile != none）的 Agent 必须 review-gated——令
        # 协作运行时 depends_on 链里的非 review-gated 上游恒为 profile=none 确定性 Agent，
        # 自动链是安全自动化，LLM 判决永不无人签流经依赖链。interactive Agent 豁免（跑
        # ConversationService 不入链、create_task 本就 409 拒之，安全阀=ADR-0012 绝不建任务）。
        # 同 P2-7：跨字段条件（mode×profile ⟹ requires_human_review）jsonschema 无法表达，
        # 故在 Registry 扫描侧 Python 补，fail-closed 拒载。
        workflow = data.get("workflow", {}) or {}
        model = data.get("model", {}) or {}
        if (
            workflow.get("mode") == "job"
            and model.get("profile") not in (None, "none")
            and workflow.get("requires_human_review") is not True
        ):
            raise InvalidPackageError(
                f"{entry} workflow.mode=job 且 model.profile={model.get('profile')!r}（调 LLM）"
                "但 workflow.requires_human_review 非 True——判决型 job Agent 必须 review-gated"
                "（协作运行时 F3 注册期不变量：LLM 判决必经人签，绝不自动流经依赖链）"
            )
        # P0-N2（导入准入门，docs/PRODUCTION-READINESS-PROGRAM.md）：交互 Agent 声明护栏。
        # 交互运行时（ConversationService）当前只注入 messages/model_gateway/agent_registry/
        # agent_config 四键，**不注入 tool_registry/knowledge**——interactive Agent 声明了
        # tools/knowledge 也静默拿不到，agent 以为有、实则空手产结论 = 假绿死罪。能力就绪前
        # fail-closed 拒载（T3-a 落地注入后放宽本不变量）。同 job×profile：jsonschema 无法
        # 表达跨字段条件（mode×tools/knowledge），故在扫描侧 Python 补。
        if workflow.get("mode") == "interactive" and (
            (data.get("tools") or [])
            or (data.get("knowledge") or {}).get("enabled") is True
        ):
            raise InvalidPackageError(
                f"{entry} workflow.mode=interactive 但声明了 tools/knowledge——交互运行时"
                "尚未注入 tool_registry/knowledge，声明了也静默拿不到（假绿死罪）；能力就绪前"
                "fail-closed 拒载（P0-N2；T3-a 落地后放宽）"
            )

        # 批七 ADR-0030 ①：L3「带我做」承诺 ⟹ 人在回路装载期不变量。既有
        # job×LLM 不变量只咬调 LLM 的包；L3 是更强的能力承诺（替我执行），
        # 即使 profile=none 的确定性 job 包也必须 review-gated——「带我做」
        # 级别的产物没有免签通道（人是唯一签发者）。
        expertise = data.get("expertise", {}) or {}
        if expertise.get("usefulness_level") == "L3":
            # 3-lens P2 收紧：L3 ⟹ mode=job 且 rhr=True。interactive 运行时根本
            # 没有 waiting_review 状态机——L3 承诺挂在 interactive 包上=永久没有
            # 人签闸可兑现，同样拒载（不止咬「job 且未开 rhr」一种姿势）。
            if workflow.get("mode") != "job" or workflow.get("requires_human_review") is not True:
                raise InvalidPackageError(
                    f"{entry} expertise.usefulness_level=L3（带我做）要求 workflow.mode=job"
                    "且 requires_human_review=True——L3 承诺装载期强制人签，interactive"
                    "运行时无人签闸不可承载 L3（ADR-0030：带我做级产物无免签通道）"
                )
        # 批七 ADR-0030 ②：依据纪律声明 ⟹ 输出契约结构落地校验。声明了
        # 「推荐必附依据」却无 findings 输出结构 = 承诺无处兑现（假绿温床），
        # 装载期读盘 spot-check，缺失即拒载。
        evidence_policy = data.get("evidence_policy", {}) or {}
        if evidence_policy.get("required") is True:
            _out_name = (data.get("output") or {}).get("schema") or "output_schema.json"
            _out_path = entry / _out_name
            _findings_ok = False
            if _out_path.is_file():
                try:
                    # 体量上界（Codex R2 P2）：深嵌套 schema 会让 json.loads 抛
                    # RecursionError（except 同步兜住）；先设字节上界把「病态大
                    # schema」在解析前挡下——正常输出契约远小于此。
                    _raw_schema = _out_path.read_bytes()
                    if len(_raw_schema) > _OUT_SCHEMA_MAX_BYTES:
                        raise InvalidPackageError(
                            f"{entry} {_out_name} 超过 {_OUT_SCHEMA_MAX_BYTES} 字节上界"
                            "（病态 schema，fail-closed 拒载）"
                        )
                    _out_doc = json.loads(_raw_schema.decode("utf-8"))
                    # Codex R0 P1：schema 顶层可以是任意 JSON（`[]`/`"x"` 均合法
                    # JSON）——非 dict 直接判不合格并隔离，绝不让 AttributeError
                    # 崩掉整个 scan（一个坏包炸全场=可用性投毒面）。
                    if not isinstance(_out_doc, dict):
                        raise InvalidPackageError(
                            f"{entry} {_out_name} 顶层必须是 object（JSON Schema 文档）"
                        )
                    _fs = (_out_doc.get("properties") or {}).get("findings")
                    # 3-lens P2 收紧 + Codex R0 P2：仅「顶层有 findings 键」无判别力，
                    # 字符串搜 '"evidence"' 又会被 description 里提一嘴骗过——改为
                    # 结构化路径校验：findings 是 array，且 items.properties 里真有
                    # evidence（array）与 resolved（依据行+核验态是 §2.2 输出契约的
                    # 不可省核心；resolved 缺席=核验态无处落地）。items 为 list
                    # （tuple-schema 写法）时取首元素。
                    if isinstance(_fs, dict) and _fs.get("type") == "array":
                        _items = _fs.get("items")
                        if isinstance(_items, list) and _items:
                            _items = _items[0]
                        if isinstance(_items, dict):
                            _props = _items.get("properties")
                            _ev = _props.get("evidence") if isinstance(_props, dict) else None
                            if isinstance(_ev, dict) and _ev.get("type") == "array":
                                _ev_items = _ev.get("items")
                                if isinstance(_ev_items, list) and _ev_items:
                                    _ev_items = _ev_items[0]
                                _ev_props = (
                                    _ev_items.get("properties")
                                    if isinstance(_ev_items, dict)
                                    else None
                                )
                                _findings_ok = (
                                    isinstance(_ev_props, dict) and "resolved" in _ev_props
                                )
                                # Codex R2 P2：evidence_policy.kinds 白名单装载期强制
                                # ——manifest 宣称 default-deny 白名单，但 schema 若放
                                # 任意 kind（或根本不约束 kind），白名单只是装饰。
                                # kinds 声明非空 ⟹ schema 的 evidence.items.properties
                                # .kind 必须 const/enum 且 ⊆ 声明列表，否则拒载。
                                _kinds_decl = evidence_policy.get("kinds")
                                if (
                                    _findings_ok is True
                                    and isinstance(_kinds_decl, list)
                                    and _kinds_decl
                                ):
                                    _kind_schema = _ev_props.get("kind")
                                    _schema_kinds = None
                                    if isinstance(_kind_schema, dict):
                                        if "const" in _kind_schema:
                                            _schema_kinds = [_kind_schema["const"]]
                                        elif isinstance(_kind_schema.get("enum"), list):
                                            _schema_kinds = _kind_schema["enum"]
                                    if _schema_kinds is None or (
                                        set(_schema_kinds) <= set(_kinds_decl)
                                    ) is False:
                                        raise InvalidPackageError(
                                            f"{entry} evidence_policy.kinds={_kinds_decl} 但 "
                                            f"{_out_name} 的 evidence kind 未以 const/enum 约束"
                                            f"在白名单内（实际={_schema_kinds}）——default-deny"
                                            " 白名单必须由输出契约强制（ADR-0030）"
                                        )
                except (json.JSONDecodeError, UnicodeError, OSError, AttributeError, TypeError, RecursionError):
                    # 防御性兜底：畸形 schema 一律判不合格走拒载，不崩 scan。
                    _findings_ok = False
            if _findings_ok is not True:
                raise InvalidPackageError(
                    f"{entry} evidence_policy.required=true 但 {_out_name} 缺失、顶层"
                    "properties 无 findings、或 findings 非 array/缺 evidence+resolved"
                    "结构——依据承诺必须有可核验的输出结构承接"
                    "（ADR-0030：无处兑现的承诺=假绿温床，fail-closed 拒载）"
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
