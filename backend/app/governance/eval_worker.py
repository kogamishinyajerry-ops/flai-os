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
        try:
            thread.start()
        except Exception:  # noqa: BLE001 - 线程起不来（OS 线程耗尽/关停）：认领态行已 running 却无
            # 执行者，run_forever 会吞掉本异常继续轮询而启动恢复不再触发 → 僵尸永久占配额。
            # 收口 error 释放配额再返回（P2，Codex R1 复审）。
            logger.exception("eval-run %s 执行线程启动失败，收口 error 释放配额", run_id)
            with self._active_lock:
                self._active.pop(run_id, None)
            self._terminalize_zombie(run_id)
            return False
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
        except Exception:  # noqa: BLE001 - execute_eval_run 保护范围内已自收口 error；此处只记日志
            logger.exception("eval-run %s 执行线程未预期异常", run_id)
        finally:
            # 兜底收口移入 finally（P1，Codex R1 复审）：正常结束→行已终态跳过；Exception→
            # execute 已自收口跳过；BaseException（SystemExit/KeyboardInterrupt 等 execute 的
            # `except Exception` 拦不住的）→行仍 running，此处收口后 BaseException 继续传播
            # （finally 不吞），任何线程退出路径都不留 running 僵尸泄配额。
            self._terminalize_zombie(run_id)
            self._reap()

    def _terminalize_zombie(self, run_id: str) -> None:
        """兜底收口（P1，Codex R1 审）：execute_eval_run 已在其 try 内自收口 error；此处
        只兜它保护范围之外的意外（如读 run 行前 conn/get_eval_run 瞬时故障）。仅当行仍
        running 才收口 error——不覆盖已终态行。单实例 worker + 本行执行线程为唯一写者，
        check-then-set 无并发对手。兜底本身失败只记日志，绝不炸 worker。"""
        from ..storage import repos

        try:
            conn = self._conn_factory()
            try:
                run = repos.get_eval_run(conn, run_id)
                if run is not None and run.get("status") == "running":
                    repos.finish_eval_run(
                        conn, run_id, status="error", total=0, passed=0, failed=0, skipped=0,
                        case_results=[{
                            "case_file": "<worker>", "verdict": "failed",
                            "detail": "执行线程意外中断且未自收口，兜底收口 error（配额释放）",
                        }],
                        draft_cases=[], eval_cases_digest=None,
                    )
            finally:
                conn.close()
        except Exception:  # noqa: BLE001 - 兜底失败不上抛，绝不炸 worker
            logger.exception("eval-run %s 兜底收口失败", run_id)

    def recover_interrupted(self) -> int:
        """worker 启动回收（P1，Codex R1 审）：上次进程崩溃遗留的 running eval_run 是无
        执行线程的僵尸，永久占配额（quota=1 立即锁死；默认 quota 两次崩溃后锁死）。worker
        单实例锁保证同库唯一 poller——此刻任何 running 行必属已死的上一代 worker，逐条收口
        error（不自动重放：case 会真起 origin='eval' 任务有外部副作用，与 runner 的
        recover_interrupted_tasks 同口径 fail-closed）。返回回收条数；须在起轮询线程前调。"""
        from ..storage import repos

        conn = self._conn_factory()
        try:
            rows = conn.execute(
                "SELECT id FROM eval_runs WHERE status = 'running' ORDER BY started_at, id"
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            conn = self._conn_factory()
            try:
                repos.finish_eval_run(
                    conn, row["id"], status="error", total=0, passed=0, failed=0, skipped=0,
                    case_results=[{
                        "case_file": "<worker-recovery>", "verdict": "failed",
                        "detail": "worker 上次进程中断，遗留 running 评测收口 error（未自动重放，配额释放）",
                    }],
                    draft_cases=[], eval_cases_digest=None,
                )
            finally:
                conn.close()
        return len(rows)

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
