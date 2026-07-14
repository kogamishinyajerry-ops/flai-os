"""Job Runner：单 worker 轮询 queued 任务并驱动 AgentRuntime 执行。

sqlite claim_next_queued 用 BEGIN IMMEDIATE 保证单次拾取不双抢；worker 进程入口
另以跨平台文件锁强制单实例，避免两个真实工具执行器同时消费同一数据库。

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

import errno
import logging
import os
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import BinaryIO, Callable, Iterator

import sqlite3

from ..config import WORKER_GENERATION
from ..core.errors import IllegalTransitionError
from ..storage import repos

logger = logging.getLogger(__name__)

# WORKER_GENERATION 定义在 config（纯 stdlib，Codex R2 审 P2：部署自检探针
# 号称免应用依赖，从 runner 导会连带拉 repos→jsonschema）；此处经 import
# re-export，runner.WORKER_GENERATION 的既有引用与调用点不变。
# 部署自检门以「心跳新鲜 + 代际匹配」双条件见证独立 worker 进程跑当前代码——
# API 升级而 worker 未重启时旧 worker 落库走 DDL DEFAULT 洗白 sensitive 派生。
_HEARTBEAT_INTERVAL_SECONDS = 15.0

_INTERRUPTED_STATUSES = ("validating", "running", "parsing", "analyzing")
_WORKER_INTERRUPTED_ERROR = (
    "worker_interrupted：上次 worker 进程中断，任务未完成即失败；"
    "真实工具可能已产生外部副作用，请人工核查后重建任务"
)


class WorkerAlreadyRunningError(RuntimeError):
    """锁文件已被另一个 worker 持有。"""

    def __init__(self, lock_path: Path) -> None:
        super().__init__(
            f"已有 worker 正在运行，拒绝并行启动第二个 worker（锁文件：{lock_path}）"
        )


def _lock_file_nonblocking(handle: BinaryIO, lock_path: Path) -> None:
    """对已打开文件做跨平台非阻塞独占锁；竞争失败转为统一业务异常。"""
    if os.name == "nt":
        import msvcrt

        # msvcrt.locking 锁定的是当前位置起的一段字节，空文件必须先补一个字节。
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            # Windows 的锁冲突通常映射为 EACCES；句柄由本函数上游创建，
            # 因而这里的 locking 失败按“已有持有者”统一 fail-closed。
            raise WorkerAlreadyRunningError(lock_path) from exc
        return

    import fcntl

    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        if exc.errno not in {errno.EACCES, errno.EAGAIN}:
            raise
        raise WorkerAlreadyRunningError(lock_path) from exc


def _unlock_file(handle: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


@contextmanager
def worker_singleton_lock(lock_path: str | Path) -> Iterator[None]:
    """持有 worker 单实例锁直到上下文退出；锁文件本身不删除以避免竞态。"""
    path = Path(lock_path)
    handle = path.open("a+b")
    try:
        _lock_file_nonblocking(handle, path)
    except Exception:
        handle.close()
        raise

    try:
        yield
    finally:
        try:
            _unlock_file(handle)
        finally:
            handle.close()


def recover_interrupted_tasks(
    conn_factory: Callable[[], sqlite3.Connection],
) -> int:
    """启动时将上次进程遗留的执行态任务置 failed，绝不重放外部副作用。"""
    conn = conn_factory()
    recovered = 0
    try:
        placeholders = ", ".join("?" for _ in _INTERRUPTED_STATUSES)
        rows = conn.execute(
            f"SELECT id FROM tasks WHERE status IN ({placeholders}) ORDER BY created_at, id",
            _INTERRUPTED_STATUSES,
        ).fetchall()
        for row in rows:
            task_id = row[0]
            failed_task = repos.fail_task_from_execution(
                conn,
                task_id,
                _WORKER_INTERRUPTED_ERROR,
            )
            # 扫描后若任务已被并发推进到审核态/终态，仓储锁内白名单会拒绝；
            # 只有本次确实置 failed 才留事件，因此恢复天然幂等。
            if failed_task is None:
                continue
            repos.append_event(
                conn,
                task_id=task_id,
                agent_id=failed_task.get("agent_id"),
                event_type="task_failed",
                level="error",
                message=_WORKER_INTERRUPTED_ERROR,
                payload={"worker_interrupted": True},
            )
            recovered += 1
    finally:
        conn.close()
    return recovered


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
        self._last_beat_monotonic: float | None = None

    def beat(self) -> None:
        """写 worker 心跳+代际（迁移 #7）。失败只记日志不上抛——心跳是部署
        自检的观测通道，绝不许它反过来炸掉真正干活的 worker。

        conn_factory() 本身也在 try 内（Codex R2 审 P1）：连接层瞬时故障
        （SQLite 打开/PRAGMA 失败）此前在 try 外抛出、经 _beat_if_due 逃逸
        run_forever 直接杀 worker——与本方法「不上抛」的契约矛盾。
        """
        conn = None
        try:
            conn = self._conn_factory()
            repos.beat_worker_heartbeat(
                conn,
                generation=WORKER_GENERATION,
                detail=f"pid={os.getpid()}",
            )
            self._last_beat_monotonic = time.monotonic()
        except Exception:
            logger.exception("worker 心跳写入失败（不影响任务执行，继续轮询）")
        finally:
            if conn is not None:
                conn.close()

    def _beat_if_due(self) -> None:
        if (
            self._last_beat_monotonic is None
            or time.monotonic() - self._last_beat_monotonic >= _HEARTBEAT_INTERVAL_SECONDS
        ):
            self.beat()

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
                self._beat_if_due()  # 心跳先于拾取：空轮询也证明 worker 活着（迁移 #7）
                try:
                    did_work = self.run_once()
                except Exception:
                    logger.exception("run_forever：run_once 抛出未预期异常，继续轮询而非退出")
                    did_work = False
                if not did_work:
                    time.sleep(self._poll_interval)
        except KeyboardInterrupt:
            return


def _assemble_default_worker_runtime() -> tuple[Any, Any, Callable[[], sqlite3.Connection]]:
    """装配 worker 进程共享的 (assembly, runtime, conn_factory)——JobRunner 与
    EvalRunner（T1 异步评测队列，GH #2）复用同一份，避免 worker 启动跑两遍昂贵的
    bootstrap.assemble。走共享路径（ADR-0015 Finding 1）：与 API 进程同一条
    「scan→scope scan→reconcile→sync」。
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
        # ADR-0021 知识轴（Codex R1 审 P1）：漏传=registry 缺失分支把 enabled
        # Agent 全判 sensitive——public_internal 知识 Agent 的产物会 403。
        scope_registry=asm.scope_registry,
    )
    return asm, runtime, conn_factory


def _build_default_runner() -> JobRunner:
    """用 config 默认路径装配一个 JobRunner（真实 data/ 目录）。薄壳，复用
    _assemble_default_worker_runtime（与 EvalRunner 同源装配）。"""
    _asm, runtime, conn_factory = _assemble_default_worker_runtime()
    return JobRunner(runtime, conn_factory)


def run_worker_forever(
    runner_factory: Callable[[], JobRunner],
    conn_factory: Callable[[], sqlite3.Connection],
    lock_path: str | Path,
    *,
    eval_runner_factory: Callable[[], Any] | None = None,
) -> int:
    """持单实例锁装配 worker，恢复上次中断任务后进入常驻轮询。

    eval_runner_factory（T1，GH #2）：给定时，在锁内、恢复后、进入任务轮询前，
    起一条 daemon 线程跑 EvalRunner.run_forever——评测队列与任务队列同属这唯一
    worker 进程（单实例锁），故评测配额是全局的。两 factory 均在锁后调用（避免
    第二个进程重跑昂贵 bootstrap）；生产装配共享同一份 assembly（见 _run_default_worker）。
    """
    try:
        with worker_singleton_lock(lock_path):
            # factory 内含真实 registry/model runtime 装配，必须放在锁后，避免
            # 已有 worker 时第二个进程仍做一遍昂贵且可能写库的 bootstrap。
            runner = runner_factory()
            recovered = recover_interrupted_tasks(conn_factory)
            if recovered:
                logger.error(
                    "worker 启动恢复：已将 %d 条上次进程中断的执行态任务置 failed，"
                    "未自动重放，请人工核查外部副作用",
                    recovered,
                )
            if eval_runner_factory is not None:
                eval_runner = eval_runner_factory()
                # P1（Codex R1 审）：起轮询前先收口上次进程崩溃遗留的 running 评测僵尸，
                # 否则它们永久占配额（quota=1 立即锁死队列）。单实例锁下此刻 running 行
                # 必属已死的上一代 worker，收口 error 释放配额（与任务恢复同口径，不重放）。
                recovered_evals = eval_runner.recover_interrupted()
                if recovered_evals:
                    logger.error(
                        "worker 启动恢复：已将 %d 条上次中断的 running 评测收口 error"
                        "（配额释放，未自动重放，请人工核查外部副作用）",
                        recovered_evals,
                    )
                threading.Thread(
                    target=eval_runner.run_forever, daemon=True, name="eval-worker"
                ).start()
            runner.run_forever()
    except WorkerAlreadyRunningError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


def _run_default_worker() -> int:
    """默认 CLI 入口：锁位于数据库同目录的 worker.lock。"""
    from .. import config
    from ..storage.db import get_conn

    # FLAI_DB_PATH 可指向默认 data/ 之外的自定义位置；锁先于 init_db 创建，
    # 因而必须在加锁前显式确保该数据库父目录存在。
    config.ensure_dirs()
    Path(config.DB_PATH).parent.mkdir(parents=True, exist_ok=True)

    # worker 进程日志（ADR-0023）：恢复中断任务/心跳失败/未预期异常等 fail-closed
    # 事件落 flai-os-worker.log，不再随 detached 启动蒸发。enable_audit_file=False：
    # 审计事件全 API 侧产生，worker 不写 audit.log 避跨进程争用（D2）。
    from ..logging_setup import configure_logging
    configure_logging(
        Path(config.DB_PATH).parent / "logs", process_tag="worker", enable_audit_file=False
    )

    def conn_factory() -> sqlite3.Connection:
        return get_conn(config.DB_PATH)

    # T1（GH #2）：JobRunner 与 EvalRunner 共享单次 assembly（避免 worker 启动跑
    # 两遍 bootstrap）。job_factory 装配一次、旁建 EvalRunner 暂存，eval_factory
    # 取出——run_worker_forever 保证 job_factory 先于 eval_factory 调用（均在锁后）。
    from ..governance.eval_worker import EvalRunner

    _stash: dict[str, EvalRunner] = {}

    def job_factory() -> JobRunner:
        asm, runtime, cf = _assemble_default_worker_runtime()
        _stash["eval"] = EvalRunner(
            agent_registry=asm.agent_registry,
            runtime=runtime,
            conn_factory=cf,
            uploads_dir=config.UPLOADS_DIR,
            task_runs_dir=config.TASK_RUNS_DIR,
            quota=config.DEFAULT_EVAL_QUOTA,
        )
        return JobRunner(runtime, cf)

    def eval_factory() -> EvalRunner:
        return _stash["eval"]

    lock_path = Path(config.DB_PATH).parent / "worker.lock"
    return run_worker_forever(
        job_factory, conn_factory, lock_path, eval_runner_factory=eval_factory
    )


if __name__ == "__main__":
    raise SystemExit(_run_default_worker())
