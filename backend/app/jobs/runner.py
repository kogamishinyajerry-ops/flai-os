"""Job Runner：单 worker 轮询 queued 任务并驱动 AgentRuntime 执行。

ADR-0008：sqlite claim_next_queued 用 BEGIN IMMEDIATE 保证单 worker 下无双抢；
多 worker 并发场景留给 M3 按需引入分布式锁。

P2-5 兜底纪律：run_once() 对单任务执行绝不裸抛——
- claim 到 validating 后、真正执行前，任务若被外部竞态转移到其他状态
  （如取消），`AgentRuntime.execute` 内部的 `assert_transition` 会炸出
  `IllegalTransitionError`；这是良性竞态而非 bug，记一条 warning 事件后
  runner 照常存活、继续轮询。
- 其他任何未预期异常同样不许上抛炸掉 worker 进程：仅当任务仍在执行态时
  尽力标记 failed 并留痕；若已进入 waiting_review/终态则拒绝自动迁移，
  记错误日志并尽力追加 warning 事件，留痕失败也只记日志、绝不上抛。
run_forever() 循环体再兜一层，防御 run_once 之外的意外（如 conn_factory
自身故障）；KeyboardInterrupt 照旧干净退出，不被这层兜底吞掉。
"""

from __future__ import annotations

import logging
import time
from typing import Callable

import sqlite3

from ..core.errors import IllegalTransitionError
from ..storage import repos

logger = logging.getLogger(__name__)


class JobRunner:
    """轮询驱动：run_once() 拾取一条任务；run_forever() 常驻轮询。"""

    def __init__(
        self,
        runtime: object,
        conn_factory: Callable[[], sqlite3.Connection],
        poll_interval: float = 1.0,
    ) -> None:
        self._runtime = runtime
        self._conn_factory = conn_factory
        self._poll_interval = poll_interval

    def run_once(self) -> bool:
        """拾取并执行一条 queued 任务；无任务可拾取返回 False。

        本方法本身绝不上抛：claim 阶段异常之外的任何单任务执行失败都被
        就地兜住（见模块 docstring），保证 runner 进程性存活。
        """
        conn = self._conn_factory()
        try:
            task = repos.claim_next_queued(conn)
        finally:
            conn.close()
        if task is None:
            return False

        task_id = task["id"]
        try:
            self._runtime.execute(task_id)
        except IllegalTransitionError as exc:
            self._record_race_warning(task_id, task.get("agent_id"), exc)
        except Exception as exc:  # noqa: BLE001 - 兜底防炸 worker，fail-closed 记录而非吞声
            self._mark_failed_best_effort(task_id, exc)
        return True

    def _record_race_warning(self, task_id: str, agent_id: str | None, exc: Exception) -> None:
        conn = self._conn_factory()
        try:
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id=agent_id,
                event_type="warning",
                level="warning",
                message=f"任务在执行前发生状态竞态迁移（如被并发取消），本次拾取放弃：{exc}",
                payload={"race": "illegal_transition", "detail": str(exc)},
            )
        except Exception:
            logger.exception("run_once：记录竞态 warning 事件本身失败，任务 %s，异常已吞掉不上抛", task_id)
        finally:
            conn.close()

    def _mark_failed_best_effort(self, task_id: str, exc: Exception) -> None:
        error_message = f"{exc.__class__.__name__}: {exc}"
        conn = self._conn_factory()
        try:
            try:
                failed_task = repos.fail_task_from_execution(conn, task_id, error_message)
            except Exception:
                logger.exception(
                    "run_once 兜底失败：任务 %s 无法检查或置 failed，原始异常：%s",
                    task_id, error_message,
                )
                return

            if failed_task is None:
                refusal_message = (
                    "任务处于非执行态（如 waiting_review/终态），Runner 拒绝自动置 failed"
                    "——waiting_review 只能由人工放行转出"
                )
                logger.error(
                    "run_once：任务 %s %s；原始异常：%s",
                    task_id, refusal_message, error_message,
                )
                try:
                    repos.append_event(
                        conn,
                        task_id=task_id,
                        event_type="warning",
                        level="error",
                        message=refusal_message,
                        payload={"runner_action": "auto_fail_refused", "error": error_message},
                    )
                except Exception:
                    logger.exception(
                        "run_once：任务 %s 的拒绝自动失败 warning 事件写入失败，状态未被改动",
                        task_id,
                    )
                return

            try:
                repos.append_event(
                    conn,
                    task_id=task_id,
                    event_type="task_failed",
                    level="error",
                    message=f"Job Runner 兜底：任务执行异常，已强制置 failed：{error_message}",
                )
            except Exception:
                logger.exception(
                    "run_once：任务 %s 已置 failed，但 task_failed 事件写入失败",
                    task_id,
                )
        finally:
            conn.close()

    def run_forever(self) -> None:
        """常驻轮询：无任务时按 poll_interval 休眠；Ctrl-C 干净退出。

        run_once() 本身已不裸抛，这里再兜一层纯防御（如 conn_factory 自身
        故障等 run_once 契约之外的意外），记日志后继续轮询而非让 worker 退出。
        """
        try:
            while True:
                try:
                    did_work = self.run_once()
                except Exception:
                    logger.exception("run_forever：run_once 抛出未预期异常，继续轮询而非退出")
                    did_work = False
                if not did_work:
                    time.sleep(self._poll_interval)
        except KeyboardInterrupt:
            return


def _build_default_runner() -> JobRunner:
    """用 backend/app/config.py 默认路径装配一个 JobRunner（真实 data/ 目录）。

    装配走共享 bootstrap.assemble（ADR-0015 Finding 1）：与 API 进程同一条
    「scan→scope scan→reconcile→sync」路径，本函数只剩取 config 默认值的薄壳。
    """
    from .. import config
    from ..bootstrap import assemble
    from ..runtime.runtime import AgentRuntime
    from ..storage.db import get_conn, init_db

    config.ensure_dirs()
    init_db(config.DB_PATH)

    def conn_factory() -> sqlite3.Connection:
        return get_conn(config.DB_PATH)

    asm = assemble(
        agents_dir=config.AGENTS_DIR,
        tools_dir=config.TOOLS_DIR,
        contracts_dir=config.CONTRACTS_DIR,
        knowledge_dir=config.KNOWLEDGE_DIR,
        conn_factory=conn_factory,
    )
    runtime = AgentRuntime(
        asm.agent_registry, asm.tool_registry, asm.model_gateway, conn_factory,
        config.TASK_RUNS_DIR, knowledge_service=asm.knowledge_service,
    )
    return JobRunner(runtime, conn_factory)


if __name__ == "__main__":
    _build_default_runner().run_forever()
