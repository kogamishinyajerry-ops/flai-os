"""进程级日志基建 + 认证/访问审计（ADR-0023，纯 stdlib）。

只 import 标准库（logging / logging.handlers / pathlib）——无任何业务依赖，
杜绝循环导入，且满足离线包「stdlib + 预下载 wheel」约束（续 ADR-0021 R2-P2）。

两个真实入口装配日志（见 ADR-0023 D3）：
- API：main.py lifespan，log_dir 派生 db_path.parent/logs，process_tag="api"，
  写 flai-os-api.log + audit.log；lifespan 退出调 reset_logging（D5 防泄漏）。
- worker：jobs/runner.py `_run_default_worker`，process_tag="worker"，
  enable_audit_file=False（审计事件全 API 侧，worker 不写 audit.log 避争用）。

file-only（D4）：绝不往 root 挂 console handler——uvicorn 自带 console，
root 挂 StreamHandler 会污染 capsys 断言的测试。
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

AUDIT_LOGGER_NAME = "flai.audit"

# 审计字段白名单（Codex R0 P1-3 / P3-3）：audit_event 只接受这些附加字段，
# 其余（含任何可能的 password/token/cookie）一律 DROP 不落库——「绝不记 secret」
# 在边界内由构造保证，不靠调用点自觉。action/outcome/actor 是固定结构字段另计。
_AUDIT_ALLOWED_FIELDS = frozenset({
    "reason", "file_id", "classification", "display_name",
    # 治理签发审计（M12-2c）：task_id=被签发任务（opaque UUID），created_by=创建者
    # 显示名（非 secret，事件层已公开），self_review=自审标记（bool）。皆无
    # user-controlled 自由文本/secret，可安全入白名单。
    "task_id", "created_by", "self_review",
    # 迁移 #9：created_by_username=创建者唯一 username（登录标识，非 secret，与
    # actor 同类已入白名单）；self_review_basis='username'|'display_name' 标注自审
    # 判定的证据等级（精确 vs legacy 近似）。二者皆枚举/受控标识，无自由文本。
    "created_by_username", "self_review_basis",
})

_LOG_FORMAT = "%(asctime)s %(levelname)s [%(name)s] %(message)s"
# 单文件 5MB 滚动；进程日志留 5 份、审计留 10 份（合规回溯窗口更长）。
_MAX_BYTES = 5 * 1024 * 1024
_APP_BACKUP_COUNT = 5
_AUDIT_BACKUP_COUNT = 10

# 本模块所加 handler 的标记属性——configure/reset 只认自己加的，绝不误删
# 别处（如 uvicorn、pytest caplog）挂在同一 logger 上的 handler（D5）。
_MANAGED_ATTR = "_flai_managed"

# configure 前的 root/audit logger 原始 level 与 propagate（Codex R0 P3-1）：
# reset 时恢复，避免退出后残留全局 INFO 状态污染后续（尤其测试）。None=未保存。
_SAVED_STATE: dict[str, object] | None = None


def _flai_handlers(logger: logging.Logger) -> list[logging.Handler]:
    return [h for h in logger.handlers if getattr(h, _MANAGED_ATTR, False) is True]


def _clear_managed(logger: logging.Logger) -> None:
    """移除并 close 本模块之前挂在该 logger 上的 handler（幂等替换的前半步）。"""
    for handler in _flai_handlers(logger):
        logger.removeHandler(handler)
        try:
            handler.close()
        except Exception:  # noqa: BLE001 - close 失败不该阻断重配，best-effort
            pass


def _make_file_handler(
    path: Path, *, backup_count: int, fmt: str = _LOG_FORMAT
) -> RotatingFileHandler:
    handler = RotatingFileHandler(
        path, maxBytes=_MAX_BYTES, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter(fmt))
    setattr(handler, _MANAGED_ATTR, True)
    return handler


def configure_logging(
    log_dir: Path | str,
    *,
    process_tag: str,
    level: int = logging.INFO,
    enable_audit_file: bool = True,
) -> None:
    """把 root（业务 logger）与 flai.audit 配到 log_dir 下的滚动文件。

    幂等：每次先清本模块既有 handler 再加新的（D5），可安全重复调用，跨测试
    不累积 handler。file-only，不加 console（D4）。
    """
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    audit = logging.getLogger(AUDIT_LOGGER_NAME)

    # 首次 configure 时快照原始 logger 状态（P3-1）：reset 据此恢复，退出零残留。
    global _SAVED_STATE
    if _SAVED_STATE is None:
        _SAVED_STATE = {
            "root_level": root.level,
            "audit_level": audit.level,
            "audit_propagate": audit.propagate,
        }

    _clear_managed(root)
    root.setLevel(level)
    root.addHandler(
        _make_file_handler(log_dir / f"flai-os-{process_tag}.log", backup_count=_APP_BACKUP_COUNT)
    )

    _clear_managed(audit)
    audit.setLevel(logging.INFO)
    # propagate=True：审计事件同时进 root 的进程日志（单一时间线）与专用
    # audit.log（合规检索）。worker 侧 enable_audit_file=False 只入进程日志。
    audit.propagate = True
    if enable_audit_file is True:
        # audit.log 用 message-only 格式 → 纯 JSON Lines（每行一条自含 ts 的 JSON
        # 记录），机器可直接逐行 json.loads；人类时间线看 propagate 到 root 的进程日志。
        audit.addHandler(
            _make_file_handler(
                log_dir / "audit.log", backup_count=_AUDIT_BACKUP_COUNT, fmt="%(message)s"
            )
        )


def reset_logging() -> None:
    """移除本模块挂的所有 handler 并恢复 logger 原始状态（lifespan 退出调，D5）。

    生产 app 常驻，仅进程退出时触发，无副作用；测试 with TestClient 退出即清。
    恢复 root/audit 的原始 level 与 propagate（P3-1）——否则退出后残留全局 INFO 态
    污染后续（尤其同进程内多测试）。"""
    global _SAVED_STATE
    root = logging.getLogger()
    audit = logging.getLogger(AUDIT_LOGGER_NAME)
    _clear_managed(root)
    _clear_managed(audit)
    if _SAVED_STATE is not None:
        root.setLevel(_SAVED_STATE["root_level"])
        audit.setLevel(_SAVED_STATE["audit_level"])
        audit.propagate = _SAVED_STATE["audit_propagate"]
        _SAVED_STATE = None


def audit_logger() -> logging.Logger:
    return logging.getLogger(AUDIT_LOGGER_NAME)


def audit_event(action: str, *, actor: str, outcome: str, **fields: object) -> None:
    """记一条结构化审计事件（ADR-0023 D6 / Codex R0 P1-3）：**JSON Lines**，
    注入安全 + 字段白名单 + 绝不含 secret。

    此前是 `k=v` 空格拼接——user-controlled 的 actor（login username）含 CR/LF/空格/`=`
    可伪造额外审计行（日志注入）。改 json.dumps：换行/特殊字符在 JSON 字符串内被
    转义，单条记录恒单行不可越界。**字段白名单**（_AUDIT_ALLOWED_FIELDS）：非白名单
    附加字段一律 DROP（含任何误传的 password/token/cookie），「绝不记 secret」由构造
    保证而非调用点自觉。configure 前调用=audit logger 无 handler=静默丢弃不抛错（fail-safe）。
    """
    safe_fields = {k: v for k, v in fields.items() if k in _AUDIT_ALLOWED_FIELDS}
    dropped = sorted(set(fields) - _AUDIT_ALLOWED_FIELDS)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "action": action, "outcome": outcome, "actor": actor, **safe_fields,
    }
    audit_logger().info(json.dumps(record, ensure_ascii=False, sort_keys=True))
    if dropped:
        # 非白名单字段被丢弃（只记键名不记值，防 secret 经告警回流）——发现调用点
        # 误传即在日志留痕待修，但绝不因此漏记主审计事件或崩溃主流程。
        audit_logger().warning(
            json.dumps(
                {"action": "audit_field_dropped", "outcome": "warning",
                 "actor": actor, "dropped_keys": dropped},
                ensure_ascii=False, sort_keys=True,
            )
        )
