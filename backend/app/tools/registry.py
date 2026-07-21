"""Tool Registry：先注册再调用（docs/03_Tool_Package_Standard.md / ADR-0008）。

扫描 ``tools_impl/*/tool.yaml`` 通过 ``contracts/tool.schema.json`` 校验后方可调用；
调用前后强制走 input_schema/output_schema 契约，超时走线程 join（Python 线程无法
强杀，超时后诚实标注"线程可能仍在后台运行"而非假装已被干净终止，见 ADR-0008 决策3）。
"""

from __future__ import annotations

import importlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jsonschema import ValidationError as JsonSchemaValidationError
from jsonschema import validate

from ..core.errors import (
    DuplicateAgentIdError,
    ToolExecutionError,
    ToolInputInvalidError,
    ToolNotRegisteredError,
    ToolOutputInvalidError,
)
from ..storage import repos


_AX_L0_TOOL_ID = "ax_web_extract"
_AX_L0_ENTRYPOINT = "tools_impl.ax_web_extract.adapter:run"
_AX_L0_VERSION = "0.1.0"
_AX_L0_NETWORK_POLICY_ID = "l0-fixture-only"
_NETWORK_EGRESS_MODES = {"none", "fixture_only", "loopback_only", "production"}


def _network_egress_registration_error(tool: dict[str, Any]) -> str | None:
    """Keep external production networking unregistrable before its gates.

    The manifest declaration is an admission contract, not the future
    executable egress policy.  The latter still has to enforce DNS/IP/redirect
    checks at connection time.  Unknown or missing declarations are rejected
    again here for defense in depth when a test or caller mutates ``_tools``
    without going through schema validation.
    """

    tool_id = str(tool.get("id") or "")
    network_mode = (tool.get("egress") or {}).get("network")
    if network_mode not in _NETWORK_EGRESS_MODES:
        return "工具缺少合法 egress.network 显式声明，默认拒绝注册与调用"
    if network_mode == "production":
        return (
            "production 网络 adapter 注册已机械锁定：必须先完成运行时角色轴，"
            "再完成可执行 egress policy；独立 L1 仍必须默认 disabled"
        )
    if network_mode == "fixture_only" and tool_id != _AX_L0_TOOL_ID:
        return (
            "egress.network=fixture_only 当前仅保留给精确 ax L0 身份；"
            "任何生产候选必须先完成运行时角色轴与可执行 egress policy，"
            "独立 L1 仍必须默认 disabled"
        )
    return None


def _ax_registration_error(tool: dict[str, Any]) -> str | None:
    """Return the hard-fuse reason for an ax production candidate.

    ax L0 is an exact, fixture-only package.  Any L1/live sibling stays
    unregistrable until the runtime role axis and executable egress policy are
    implemented and this code fuse is replaced through an independently
    reviewed change.  Environment variables cannot alter this decision.
    """

    tool_id = str(tool.get("id") or "")
    entrypoint = str(tool.get("entrypoint") or "")
    module_path = entrypoint.partition(":")[0]
    input_properties = (tool.get("input_schema") or {}).get("properties", {})
    input_required = set((tool.get("input_schema") or {}).get("required") or [])
    operation_enum = set(
        (input_properties.get("operation") or {}).get("enum") or []
    )
    output_properties = (tool.get("output_schema") or {}).get("properties", {})
    id_is_ax_family = tool_id == "ax" or tool_id.startswith("ax_")
    entrypoint_is_ax_family = (
        module_path == "tools_impl.ax"
        or module_path.startswith("tools_impl.ax_")
        or module_path.startswith("tools_impl.ax.")
    )
    network_extract_shape = (
        "url" in input_properties
        or "url" in input_required
        or bool(operation_enum.intersection({"fetch", "discover", "extract"}))
        or "network_policy_id" in output_properties
    )

    if tool_id == _AX_L0_TOOL_ID:
        policy_const = (
            (tool.get("output_schema") or {})
            .get("properties", {})
            .get("network_policy_id", {})
            .get("const")
        )
        exact_l0 = (
            entrypoint == _AX_L0_ENTRYPOINT
            and tool.get("version") == _AX_L0_VERSION
            and tool.get("output_classification") == "sensitive"
            and (tool.get("egress") or {}).get("network") == "fixture_only"
            and policy_const == _AX_L0_NETWORK_POLICY_ID
        )
        if exact_l0:
            return None
        return (
            "ax_web_extract 仅允许精确的 L0 fixture-only manifest；"
            "运行时角色轴与可执行 egress policy 尚未完成，任何 L1/live 变体必须默认 disabled"
        )

    if id_is_ax_family or entrypoint_is_ax_family or network_extract_shape:
        return (
            "ax/联网抽取 L1/live 生产 adapter 注册已机械锁定：必须先完成运行时角色轴，"
            "再完成可执行 egress policy；独立 L1 仍必须默认 disabled"
        )
    return None


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class ToolRegistry:
    """扫描 ``tools_dir`` 建立可调用工具目录，并提供统一调用入口 :meth:`call`。"""

    def __init__(self, tools_dir: str | Path, schema_path: str | Path) -> None:
        self.tools_dir = Path(tools_dir)
        self.schema_path = Path(schema_path)
        self._tools: dict[str, dict[str, Any]] = {}
        self._tool_dirs: dict[str, Path] = {}
        # scan() 期间收集到的非法 tool.yaml（不炸整个 Registry，仅排除该工具）。
        # 每项：{"dir": 目录路径字符串, "error": 校验/解析失败信息}
        self.errors: list[dict[str, str]] = []

    def scan(self) -> None:
        """扫描 tools_dir 下每个子目录的 tool.yaml。

        - schema 校验不通过（含 YAML 语法错误）的目录记入 ``self.errors`` 并排除，
          不影响其余合法工具正常注册（不炸整个 Registry）。
        - 重复 id 是硬错：直接抛 ``DuplicateAgentIdError``，不允许静默去重。
        """
        schema = json.loads(self.schema_path.read_text(encoding="utf-8"))
        self._tools = {}
        self._tool_dirs = {}
        self.errors = []

        if not self.tools_dir.is_dir():
            return

        for entry in sorted(self.tools_dir.iterdir()):
            if not entry.is_dir():
                continue
            yaml_path = entry / "tool.yaml"
            if not yaml_path.is_file():
                continue  # 不是工具包目录（如 __pycache__），静默跳过
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                if not isinstance(data, dict):
                    raise ValueError("tool.yaml 顶层内容不是一个对象")
                validate(data, schema)
            except (yaml.YAMLError, JsonSchemaValidationError, ValueError, OSError) as exc:
                self.errors.append({"dir": str(entry), "error": str(exc)})
                continue

            egress_error = _network_egress_registration_error(data)
            if egress_error is not None:
                self.errors.append({"dir": str(entry), "error": egress_error})
                continue

            ax_error = _ax_registration_error(data)
            if ax_error is not None:
                self.errors.append({"dir": str(entry), "error": ax_error})
                continue

            tool_id = data["id"]
            if tool_id in self._tools:
                raise DuplicateAgentIdError(
                    f"重复的工具 id：{tool_id}（{self._tool_dirs[tool_id]} 与 {entry} 冲突）"
                )
            self._tools[tool_id] = data
            self._tool_dirs[tool_id] = entry

    def get(self, tool_id: str) -> dict[str, Any] | None:
        return self._tools.get(tool_id)

    def list(self) -> list[dict[str, Any]]:
        return list(self._tools.values())

    def call(
        self,
        tool_id: str,
        payload: dict[str, Any],
        *,
        conn: Any = None,
        task_id: str | None = None,
        tool_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一调用入口：入参契约校验 → 线程超时执行 → 出参契约校验 → 无论成败落 tool_runs。

        ``conn=None`` 时跳过落库（供库内自测使用，不落真实/临时 db）。
        ``tool_context``：任务级注入 adapter 的额外只读上下文（#8/R2-1，如 eval 任务的
        材化 fixture 根 eval_fixtures_dir），并入 adapter 的 context 参数。任务级传递、
        非进程全局 env，并发安全。
        """
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotRegisteredError(f"工具未注册：{tool_id}（先注册再调用，见 docs/03）")
        egress_error = _network_egress_registration_error(tool)
        if egress_error is not None:
            raise ToolNotRegisteredError(egress_error)
        ax_error = _ax_registration_error(tool)
        if ax_error is not None:
            raise ToolNotRegisteredError(ax_error)

        tool_version = tool["version"]
        mock = bool(tool.get("mock", False))
        started_at = _now_iso()
        sensitive_input = tool.get("output_classification") == "sensitive"
        if sensitive_input is True:
            if isinstance(payload, dict):
                default_recorded_input = {
                    "_redacted": True,
                    "input_keys": sorted(str(key) for key in payload),
                }
            else:
                default_recorded_input = {
                    "_redacted": True,
                    "input_type": type(payload).__name__,
                }
        else:
            default_recorded_input = payload

        def _record(
            *,
            status: str,
            output: dict[str, Any] | None,
            error_message: str | None,
            finished_at: str,
            record_raw_paths: bool = False,
        ) -> None:
            if conn is None:
                return
            # 解析/文件型工具可在已通过其 output_schema 的结果中声明原始件路径。
            # Registry 只做有类型的映射，不从 payload 接受路径，也不猜工具工作区；
            # 真正的路径约束由可信 tool_context + adapter 负责。此前两列始终 NULL，
            # 与 docs/03「原始件入 tool_runs」契约脱节。
            raw_input_path = None
            raw_output_path = None
            if record_raw_paths is True and isinstance(output, dict):
                if isinstance(output.get("raw_input_path"), str):
                    raw_input_path = output["raw_input_path"]
                if isinstance(output.get("raw_output_path"), str):
                    raw_output_path = output["raw_output_path"]
            repos.record_tool_run(
                conn,
                task_id=task_id,
                tool_id=tool_id,
                tool_version=tool_version,
                mock=mock,
                status=status,
                input_json=default_recorded_input,
                output_json=output,
                raw_input_path=raw_input_path,
                raw_output_path=raw_output_path,
                error_message=error_message,
                started_at=started_at,
                finished_at=finished_at,
            )

        # 1) 入参契约校验（fail-closed：不合格拒调，不进 adapter.py）
        try:
            validate(payload, tool["input_schema"])
        except JsonSchemaValidationError as exc:
            if sensitive_input is True:
                field_path = ".".join(str(part) for part in exc.absolute_path) or "$"
                error_message = (
                    "入参未通过 input_schema 校验："
                    f"field={field_path}, rule={exc.validator}；sensitive 输入值已遮蔽"
                )
            else:
                error_message = f"入参未通过 input_schema 校验：{exc.message}"
            _record(
                status="failed",
                output=None,
                error_message=error_message,
                finished_at=_now_iso(),
            )
            raise ToolInputInvalidError(error_message) from exc

        # 2) 加载 entrypoint（形如 module.path:func）。P2-3：import/getattr 失败也是
        #    一次失败的调用——必须先落 tool_runs failed 行（call() 成败皆落库的承诺）
        #    再抛，不允许坏靶 entrypoint 在 tool_runs 里无痕。
        module_path, _, func_name = tool["entrypoint"].partition(":")
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, func_name)
        except (ImportError, AttributeError) as exc:
            error_message = (
                f"entrypoint 解析失败（{tool['entrypoint']}）："
                f"{exc.__class__.__name__}: {exc}（工具包配置错误，未执行任何工具逻辑）"
            )
            _record(status="failed", output=None, error_message=error_message, finished_at=_now_iso())
            raise ToolExecutionError(error_message) from exc

        # 3) 线程 join 超时执行：Python 线程无法强杀，超时即放弃等待并诚实标注
        #    （ADR-0008 决策3：真隔离留给 M3 按需引入）。
        timeout_seconds = tool["runtime"]["timeout_seconds"]
        box: dict[str, Any] = {}

        # adapter context = task_id + 任务级注入（#8/R2-1）。both 空则传 None（向后兼容）。
        adapter_ctx: dict[str, Any] = {}
        if task_id:
            adapter_ctx["task_id"] = task_id
        if tool_context:
            adapter_ctx.update(tool_context)

        def _target() -> None:
            try:
                box["result"] = func(payload, adapter_ctx or None)
            except Exception as exc:  # noqa: BLE001 - adapter 契约要求绝不裸抛，这里兜底防炸 worker
                box["exc"] = exc

        thread = threading.Thread(target=_target, daemon=True)
        thread.start()
        thread.join(timeout_seconds)

        if thread.is_alive():
            error_message = (
                f"工具调用超时（timeout_seconds={timeout_seconds}）："
                "已放弃等待，线程可能仍在后台运行、未被强杀终止（诚实标注，见 ADR-0008 决策3）"
            )
            _record(status="failed", output=None, error_message=error_message, finished_at=_now_iso())
            raise TimeoutError(error_message)

        finished_at = _now_iso()

        if "exc" in box:
            error_message = f"工具适配器抛出未捕获异常（违反 docs/03 绝不裸抛约定）：{box['exc']}"
            _record(status="failed", output=None, error_message=error_message, finished_at=finished_at)
            raise box["exc"]

        output = box.get("result")

        # 4) 出参契约校验（fail-closed：绝不放行契约外输出）
        try:
            validate(output, tool["output_schema"])
        except JsonSchemaValidationError as exc:
            error_message = f"出参未通过 output_schema 校验：{exc.message}"
            _record(
                status="failed",
                output=output if isinstance(output, dict) else None,
                error_message=error_message,
                finished_at=finished_at,
            )
            raise ToolOutputInvalidError(error_message) from exc

        status = output.get("status")
        if status not in ("success", "failed"):
            # fail-closed（ADR-0013）：缺 status/非法 status 的输出绝不默认成功——
            # 此前 `get("status", "success")` 是 fail-open：未来任何工具漏声明
            # status，其输出会被静默判成功。契约层（tool.schema.json 已强制
            # output_schema.required 含 status）+ 本运行时守卫双层兜底。
            error_message = f"工具输出缺少合法 status（实得 {status!r}），按契约违规处理"
            _record(status="failed", output=output, error_message=error_message, finished_at=finished_at)
            raise ToolOutputInvalidError(error_message)

        save_raw_files = tool.get("safety", {}).get("save_raw_files") is True
        if save_raw_files is True:
            raw_keys = ("raw_input_path", "raw_output_path")
            evidence_path_keys = (*raw_keys, "manifest_path", "extracted_output_path")
            if status == "success" and not isinstance(output.get("raw_output_path"), str):
                error_message = (
                    "工具声明 save_raw_files=true，但成功输出缺 raw_output_path；"
                    "拒绝制造无原始件的成功记录"
                )
                _record(
                    status="failed",
                    output=output,
                    error_message=error_message,
                    finished_at=finished_at,
                )
                raise ToolOutputInvalidError(error_message)

            if status == "failed" and all(
                output.get(key) is None for key in evidence_path_keys
            ):
                # 预执行拒绝（如激活开关/URL 策略失败）尚未产生原始件；失败记录本身
                # 仍合法，不得因 output_dir 尚未创建而把契约内 failed 升成异常。
                save_raw_files = False

        if save_raw_files is True:
            root_raw = (tool_context or {}).get("output_dir")
            try:
                if not isinstance(root_raw, str) or not root_raw:
                    raise ValueError("可信 tool_context.output_dir 缺失")
                root = Path(root_raw)
                if not root.is_absolute() or root.is_symlink() or not root.is_dir():
                    raise ValueError("可信 output_dir 必须是已存在的绝对普通目录")
                root = root.resolve(strict=True)
                for key in evidence_path_keys:
                    value = output.get(key)
                    if value is None:
                        continue
                    if not isinstance(value, str):
                        raise ValueError(f"{key} 不是字符串")
                    candidate = Path(value)
                    if not candidate.is_absolute() or candidate.is_symlink():
                        raise ValueError(f"{key} 必须是绝对普通文件且不能是符号链接")
                    try:
                        candidate = candidate.resolve(strict=True)
                    except OSError as exc:
                        raise ValueError(f"{key} 不存在或不可解析") from exc
                    if not candidate.is_file():
                        raise ValueError(f"{key} 不是普通文件")
                    try:
                        candidate.relative_to(root)
                    except ValueError as exc:
                        raise ValueError(f"{key} 不在可信 output_dir 内") from exc
                    output[key] = str(candidate)
            except (OSError, ValueError) as exc:
                error_message = f"原始/证据件路径未通过可信 output_dir 校验：{exc}"
                _record(
                    status="failed",
                    output=output,
                    error_message=error_message,
                    finished_at=finished_at,
                )
                raise ToolOutputInvalidError(error_message) from exc

        _record(
            status=status,
            output=output,
            error_message=output.get("error_message"),
            finished_at=finished_at,
            record_raw_paths=save_raw_files,
        )
        return output
