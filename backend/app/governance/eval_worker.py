"""异步评测 Worker（T1 异步评测队列 + 配额，GH #2）。

把「触发评测」从 API 请求线程里的同步阻塞，改成：API 入队一条 status='queued'
的 eval_run 立即返回，本 worker 轮询队列、在**配额门**内认领（queued→running）
并在独立线程里驱动 `execute_eval_run` 跑到终态。

配额=同时 running 的 eval-run 数上限（config.DEFAULT_EVAL_QUOTA）。原子性锚在
`repos.claim_next_queued_eval_run`（统计 running + 配额判断 + CAS 同一写锁内），
本 worker 是单实例（与 Job Runner 同进程、共用 worker 单实例锁），故轮询者唯一。

设计与 Job Runner 对称：run_once 认领一条→起线程执行→run_forever 空转休眠。
每个 running run 在自己的线程里顺序跑 case（每 case 建 origin='eval' 任务 +
runtime.execute），故配额=并发线程数上限。线程异常绝不炸 worker：execute_eval_run
自身把 run 收口为 error；本层再兜一层日志。
"""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path
from typing import Any, Callable

from .eval_runner import execute_eval_run

logger = logging.getLogger(__name__)


class EvalRunner:
    def __init__(
        self,
        *,
        agent_registry: Any,
        runtime: Any,
        conn_factory: Callable[[], Any],
        uploads_dir: Path,
        task_runs_dir: Path,
        quota: int,
        poll_interval: float = 1.0,
    ) -> None:
        self._agent_registry = agent_registry
        self._runtime = runtime
        self._conn_factory = conn_factory
        self._uploads_dir = uploads_dir
        self._task_runs_dir = task_runs_dir
        self._quota = max(1, int(quota))
        self._poll_interval = poll_interval
        self._active: dict[str, threading.Thread] = {}
        self._active_lock = threading.Lock()

    def _reap(self) -> None:
        with self._active_lock:
            for run_id in [rid for rid, t in self._active.items() if not t.is_alive()]:
                del self._active[run_id]

    def active_count(self) -> int:
        self._reap()
        with self._active_lock:
            return len(self._active)

    def run_once(self) -> bool:
        """认领至多一条 queued run 起线程执行。返回是否认领到（供 run_forever
        决定是否休眠）。配额判断+CAS 认领在 claim_next_queued_eval_run 内原子完成。"""
        self._reap()
        with self._active_lock:
            if len(self._active) >= self._quota:
                return False
        # 从 storage 导入放调用点内避免与 eval_runner 的循环导入风险（本模块已导
        # execute_eval_run；claim 属存储层，就近导入）。
        from ..storage import repos

        conn = self._conn_factory()
        try:
            run = repos.claim_next_queued_eval_run(conn, quota=self._quota)
        finally:
            conn.close()
        if run is None:
            return False
        run_id = run["id"]
        thread = threading.Thread(
            target=self._execute_claimed, args=(run_id,), daemon=True,
            name=f"eval-run-{run_id[:12]}",
        )
        with self._active_lock:
            self._active[run_id] = thread
        thread.start()
        return True

    def _execute_claimed(self, run_id: str) -> None:
        try:
            execute_eval_run(
                run_id=run_id,
                conn_factory=self._conn_factory,
                agent_registry=self._agent_registry,
                runtime=self._runtime,
                uploads_dir=self._uploads_dir,
                task_runs_dir=self._task_runs_dir,
            )
        except Exception:  # noqa: BLE001 - execute_eval_run 自身已把 run 收口 error；此处兜底不炸 worker
            logger.exception("eval-run %s 执行线程未预期异常", run_id)
        finally:
            self._reap()

    def run_forever(self) -> None:
        """常驻轮询：认领到就立即再试（尽快填满配额），空转按 poll_interval 休眠。
        run_once 之外的意外（conn_factory 故障等）记日志后继续，绝不退出 worker。"""
        try:
            while True:
                try:
                    claimed = self.run_once()
                except Exception:  # noqa: BLE001
                    logger.exception("eval worker：run_once 抛出未预期异常，继续轮询")
                    claimed = False
                if not claimed:
                    time.sleep(self._poll_interval)
        except KeyboardInterrupt:
            return
