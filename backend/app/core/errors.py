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
