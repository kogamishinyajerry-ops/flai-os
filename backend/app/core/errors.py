"""FLAi-OS 内核错误类型。

统一继承 FlaiError，便于 API 层做一处 try/except 兜底分类映射为 HTTP 状态码，
同时又能按具体子类做更精细的处理（fail-closed：未知错误绝不吞掉降级为绿）。
"""

from __future__ import annotations


class FlaiError(Exception):
    """FLAi-OS 内核异常基类。"""


class IllegalTransitionError(FlaiError):
    """任务状态机非法转移（docs/05 转移表之外的迁移）。"""


class RegistryError(FlaiError):
    """Agent/Tool 注册表相关错误基类。"""


class DuplicateAgentIdError(RegistryError):
    """扫描到重复的 Agent id 或 Tool id（硬错，不允许静默去重）。"""


class InvalidPackageError(RegistryError):
    """Agent Package / Tool Package 不满足强制件完整性要求。"""


class ToolNotRegisteredError(FlaiError):
    """调用了未在 Tool Registry 注册的工具（宪法铁律二：先注册再调用）。"""


class ToolNotAllowedError(FlaiError):
    """工具已注册但不在当前 Agent 的 agent.yaml.tools 白名单内（default-deny：
    不在白名单即不可调用——新注册工具绝不自动扩大存量 Agent 的权限面）。"""


class ToolExecutionError(FlaiError):
    """工具包 entrypoint 无法解析/加载（模块不存在、函数名写错等包配置错误）。"""


class ToolInputInvalidError(FlaiError):
    """工具入参未通过 input_schema 校验。"""


class ToolOutputInvalidError(FlaiError):
    """工具出参未通过 output_schema 校验（fail-closed：绝不放行契约外输出）。"""


class ProfileNotConfiguredError(FlaiError):
    """Model Gateway 收到了未在 profiles.yaml 中声明的 profile 名。"""


class ModelUpstreamError(FlaiError):
    """模型网关上游调用失败（env 缺失/网络错误/非 2xx）。"""


class TaskNotFoundError(FlaiError):
    """按 id 查不到对应任务。"""


class FileNotFoundInStoreError(FlaiError):
    """按 id 查不到对应的 File Store 记录。"""


class ConversationNotFoundError(FlaiError):
    """按 id 查不到对应的导引会话（M6）。"""


class ConversationClosedError(FlaiError):
    """会话已结束（concluded/abandoned），不再接受新消息（M6）。"""


class ConversationConflictError(FlaiError):
    """会话被并发修改（本轮基于的历史已过期），本轮不落库，可重试（ADR-0013）。"""


class NotInteractiveAgentError(FlaiError):
    """对非 interactive 型 Agent 发起会话，或对 interactive 型 Agent 建一次性任务
    （ADR-0012：两条运行时语义正交，不允许混用）。"""


class KnowledgeError(FlaiError):
    """Knowledge 内核服务错误基类（ADR-0015）。"""


class InvalidScopePackageError(RegistryError):
    """Knowledge Scope 包不合格：scope.yaml 缺失/解析失败/schema 不过/
    scope_id 与目录名不一致/path_or_uri 二选一违规/源路径逃逸 scope 目录。"""


class KnowledgeScopeNotRegisteredError(KnowledgeError):
    """查询了未在 Scope Registry 注册的 scope_id（default-deny：未注册即不存在）。"""


class KnowledgeScopeDeniedError(KnowledgeError):
    """scope 已注册但不在当前 Agent 的 agent.yaml knowledge.scopes 白名单内，
    或密级静态门拒绝（default-deny，与工具白名单同构：不在清单即不可访问）。"""


class KnowledgeSourceUnavailableError(KnowledgeError):
    """scope 的知识源当前不可用：source=obsidian_vault/mcp 未接入、
    kind≠document 未接入、path_or_uri_env 环境变量缺失、源目录不存在。
    诚实"未接入"而非静默空结果（docs/06 §6）。"""


class KnowledgeIngestError(KnowledgeError):
    """语料摄取失败：不支持的格式/空语料/解析失败/可选依赖缺失。
    fail-closed：部分可解析也不出部分语料（静默缺片比报错更毒）。"""
