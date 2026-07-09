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
    ) -> dict[str, Any]:
        """统一调用入口：入参契约校验 → 线程超时执行 → 出参契约校验 → 无论成败落 tool_runs。

        ``conn=None`` 时跳过落库（供库内自测使用，不落真实/临时 db）。
        """
        tool = self._tools.get(tool_id)
        if tool is None:
            raise ToolNotRegisteredError(f"工具未注册：{tool_id}（先注册再调用，见 docs/03）")

        tool_version = tool["version"]
        mock = bool(tool.get("mock", False))
        started_at = _now_iso()

        def _record(*, status: str, output: dict[str, Any] | None, error_message: str | None, finished_at: str) -> None:
            if conn is None:
                return
            repos.record_tool_run(
                conn,
                task_id=task_id,
                tool_id=tool_id,
                tool_version=tool_version,
                mock=mock,
                status=status,
                input_json=payload,
                output_json=output,
                error_message=error_message,
                started_at=started_at,
                finished_at=finished_at,
            )

        # 1) 入参契约校验（fail-closed：不合格拒调，不进 adapter.py）
        try:
            validate(payload, tool["input_schema"])
        except JsonSchemaValidationError as exc:
            error_message = f"入参未通过 input_schema 校验：{exc.message}"
            _record(status="failed", output=None, error_message=error_message, finished_at=_now_iso())
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

        def _target() -> None:
            try:
                box["result"] = func(payload, {"task_id": task_id} if task_id else None)
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
        _record(status=status, output=output, error_message=output.get("error_message"), finished_at=finished_at)
        return output
