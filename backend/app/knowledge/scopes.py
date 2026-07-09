"""Knowledge Scope Registry：扫描 knowledge_dir 下的 scope 包 + 装配期对账（ADR-0015）。

与 runtime/registry.py AgentRegistry 刻意同构：scan() 覆盖式重建内存注册表
（幂等）、单包不合格走 `.errors` 软记录后继续扫描其余包（fail-closed 不注册，
不中止整次扫描）、get/list/scope_dir 与 AgentRegistry 的 get/list/package_dir
一一对应。差异：scope_id 强制等于目录名（防路径混淆，同 FDE casepack 纪律），
目录天然唯一，故不存在 AgentRegistry 那条重复 id 硬错路径。

resolve_source_dir 是「scope 配置 → 真实源目录」的唯一出口，fail-closed：
- source≠file_dir / kind≠document / env 变量缺失或空 / 目录不存在 → 诚实抛
  KnowledgeSourceUnavailableError（"未接入"绝不静默空结果，docs/06 §6）；
- path_or_uri 直填相对路径 resolve 后逃逸出 scope 目录 →
  InvalidScopePackageError（先于存在性检查：安全违规优先，收口 tamper T6 咬合点）。

reconcile_agent_scopes 在装配期对账（main.py 与 runner 共享 bootstrap 处调用）：
knowledge.enabled is True 的 Agent 引用未注册 scope 或密级静态门不过 →
AgentRegistry.deregister。与 runtime.py 的工具白名单同属 default-deny 家族：
不在清单/不满足密级即不可访问，新注册 scope 绝不自动扩大存量 Agent 的访问面。
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from jsonschema import ValidationError, validate

from ..core.errors import InvalidScopePackageError, KnowledgeSourceUnavailableError

if TYPE_CHECKING:
    from ..runtime.registry import AgentRegistry


class ScopeRegistry:
    """扫描 `knowledge_dir` 下的 Knowledge Scope 包，维护内存注册表。

    目录布局：`<knowledge_dir>/<scope_id>/scope.yaml` + 源文件目录。
    """

    def __init__(self, knowledge_dir: str | Path, schema_path: str | Path) -> None:
        self.knowledge_dir = Path(knowledge_dir)
        self.schema_path = Path(schema_path)
        self._schema: dict[str, Any] = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self._scopes: dict[str, dict[str, Any]] = {}
        self._dirs: dict[str, Path] = {}
        self.errors: list[dict[str, str]] = []

    def scan(self) -> None:
        """重新扫描 knowledge_dir，覆盖式重建内存注册表（幂等：可重复调用）。

        knowledge_dir 不存在 → 空注册表（部署可以还没有知识库，不是错误）。
        单包不合格 → `.errors` 软记录 + 跳过，其余包继续注册。
        """
        self._scopes = {}
        self._dirs = {}
        self.errors = []
        if not self.knowledge_dir.is_dir():
            return
        for entry in sorted(self.knowledge_dir.iterdir()):
            if not entry.is_dir():
                continue
            try:
                data = self._load_one(entry)
            except InvalidScopePackageError as exc:
                self.errors.append({"path": str(entry), "error": str(exc)})
                continue
            self._scopes[data["scope_id"]] = data
            self._dirs[data["scope_id"]] = entry

    def _load_one(self, entry: Path) -> dict[str, Any]:
        yaml_path = entry / "scope.yaml"
        if not yaml_path.is_file():
            raise InvalidScopePackageError(f"{entry} 缺少 scope.yaml")
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except yaml.YAMLError as exc:
            raise InvalidScopePackageError(f"{entry} scope.yaml 解析失败：{exc}") from exc
        if not isinstance(data, dict):
            raise InvalidScopePackageError(f"{entry} scope.yaml 顶层必须是 object")
        try:
            validate(data, self._schema)
        except ValidationError as exc:
            raise InvalidScopePackageError(
                f"{entry} scope.yaml 未通过 knowledge_scope.schema.json 校验：{exc.message}"
            ) from exc
        if data["scope_id"] != entry.name:
            raise InvalidScopePackageError(
                f"{entry} scope_id={data['scope_id']!r} 与目录名 {entry.name!r} 不一致"
                "（scope_id 即目录名，防路径混淆）"
            )
        # xor：path_or_uri 与 path_or_uri_env 必须恰好一个存在。jsonschema 表达
        # 不了跨字段 xor（与 registry.py P2-7 同为 Python 侧补校验）。
        has_path = "path_or_uri" in data
        has_env = "path_or_uri_env" in data
        if has_path == has_env:
            raise InvalidScopePackageError(
                f"{entry} path_or_uri 与 path_or_uri_env 必须恰好提供一个"
                f"（当前{'两者都有' if has_path else '两者都缺'}）"
            )
        return data

    def get(self, scope_id: str) -> dict[str, Any] | None:
        """按 id 取已注册 scope 的 scope.yaml 解析结果；未注册返回 None（不抛异常）。"""
        return self._scopes.get(scope_id)

    def list(self) -> list[dict[str, Any]]:
        return list(self._scopes.values())

    def scope_dir(self, scope_id: str) -> Path | None:
        """取 scope 包所在目录（resolve_source_dir 解析相对路径的基准）。"""
        return self._dirs.get(scope_id)


def resolve_source_dir(scope: dict[str, Any], scope_dir: Path) -> Path:
    """把已注册 scope 的配置解析为真实存在的源文件目录（KnowledgeService 唯一入口）。

    约束（docs/06 §6 + ADR-0015）：
    - 仅承载 source=file_dir 且 kind=document；obsidian_vault/mcp 待内网侦察，
      engineering_experience 走 docs/adr、run_memory 走 task_events，一律诚实
      KnowledgeSourceUnavailableError，绝不静默空结果；
    - path_or_uri_env 路线：环境变量由部署方受控注入（敏感路径不入仓），允许
      指向 scope 目录外，不做逃逸检查；缺失/空值即 Unavailable（消息含变量名）；
    - path_or_uri 直填路线：相对路径相对 scope_dir 解析，resolve 后必须仍在
      scope_dir 内——`../` 逃逸抛 InvalidScopePackageError，且先于存在性检查
      （安全违规优先，收口 tamper T6 咬合点）；
    - 两条路线的解析结果都必须是存在的目录，否则 Unavailable。
    """
    scope_id = scope.get("scope_id")
    if scope.get("source") != "file_dir":
        raise KnowledgeSourceUnavailableError(
            f"scope {scope_id!r} source={scope.get('source')!r} 未接入"
            "（obsidian_vault/mcp 待内网侦察，V0.1 仅承载 file_dir）"
        )
    if scope.get("kind") != "document":
        raise KnowledgeSourceUnavailableError(
            f"scope {scope_id!r} kind={scope.get('kind')!r} 不由本服务承载"
            "（engineering_experience 走 docs/adr，run_memory 走 task_events）"
        )
    scope_root = Path(scope_dir).resolve()
    if "path_or_uri_env" in scope:
        var = scope["path_or_uri_env"]
        raw = os.environ.get(var)
        if raw is None or raw.strip() == "":
            raise KnowledgeSourceUnavailableError(
                f"scope {scope_id!r} 的环境变量 {var} 缺失或为空"
                "（path_or_uri_env 路线由部署方注入，缺失即诚实不可用）"
            )
        candidate = Path(raw)
        if candidate.is_absolute() is False:
            candidate = scope_root / candidate
        candidate = candidate.resolve()
    else:
        candidate = Path(scope["path_or_uri"])
        if candidate.is_absolute() is False:
            candidate = scope_root / candidate
        candidate = candidate.resolve()
        if candidate.is_relative_to(scope_root) is False:
            raise InvalidScopePackageError(
                f"scope {scope_id!r} path_or_uri={scope['path_or_uri']!r} resolve 后逃逸出 scope 目录"
                f"（{candidate} 不在 {scope_root} 内；直填路线不得 ../ 逃逸，"
                "仓外敏感路径必须改走 path_or_uri_env）"
            )
    if candidate.is_dir() is False:
        raise KnowledgeSourceUnavailableError(
            f"scope {scope_id!r} 源目录不存在或不是目录：{candidate}"
        )
    return candidate


def reconcile_agent_scopes(
    agent_registry: "AgentRegistry", scope_registry: ScopeRegistry
) -> list[dict[str, str]]:
    """装配期对账：knowledge.enabled is True 的 Agent 逐条核对 scopes 白名单。

    fail-closed（ADR-0015）：任一违规即 agent_registry.deregister，该 Agent
    从此 get/list 不可见（装配顺序上必须先于 sync_to_db）。两类违规：
    ① 引用未注册 scope（default-deny：未注册即不存在）；
    ② 密级静态门（V0.1 无用户鉴权下的诚实近似——拿 Agent 的
       permissions.visibility 当受众上界做静态核对）：
       restricted → visibility 必须 == "admin_only"；
       department → visibility ∈ {"admin_only", "department_trial"}；
       public_internal → 任意（门不咬公开级）。
    enabled 不为字面 True（false/缺失）不检查：disabled Agent 的 scopes 引用
    只是配置残留，不构成访问面。返回违规记录 [{"agent_id","scope_id","reason"}]
    供装配处记日志；每个 Agent 只记首条违规（deregister 后续条目无意义）。
    """
    records: list[dict[str, str]] = []
    for agent in agent_registry.list():
        knowledge = agent.get("knowledge") or {}
        if knowledge.get("enabled") is not True:
            continue
        agent_id = agent["id"]
        visibility = (agent.get("permissions") or {}).get("visibility")
        for scope_id in knowledge.get("scopes") or []:
            scope = scope_registry.get(scope_id)
            if scope is None:
                reason = (
                    f"Agent {agent_id!r} 引用的 knowledge scope {scope_id!r} 未注册"
                    "（default-deny 启动对账，ADR-0015）"
                )
            else:
                reason = _confidentiality_denial(scope, visibility, agent_id)
            if reason is not None:
                agent_registry.deregister(agent_id, reason)
                records.append({"agent_id": agent_id, "scope_id": scope_id, "reason": reason})
                break
    return records


def _confidentiality_denial(scope: dict[str, Any], visibility: Any, agent_id: str) -> str | None:
    """密级静态门单格判定：放行返回 None，拒绝返回原因字符串。

    判定全部用 ==/in 显式比较；schema 枚举外的未知密级落到兜底拒绝（fail-closed：
    无法验证 = 拒绝，不是"验证到违规才拒绝"）。
    """
    conf = scope.get("confidentiality")
    if conf == "public_internal":
        return None
    if conf == "department" and visibility in ("admin_only", "department_trial"):
        return None
    if conf == "restricted" and visibility == "admin_only":
        return None
    return (
        f"Agent {agent_id!r}（visibility={visibility!r}）不满足 scope "
        f"{scope.get('scope_id')!r} 密级 {conf!r} 的静态门要求（ADR-0015）"
    )
