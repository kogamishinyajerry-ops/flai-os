"""sqlite3 连接与九表 DDL（ADR-0008：stdlib sqlite3 + 仓储函数层，不引 ORM）。

连接采用 isolation_level=None（Python sqlite3 的"手动事务"模式）：
- 普通读写语句保持事实上的 autocommit，调用方无需逐条 commit；
- 需要原子性的地方（claim_next_queued）显式 `BEGIN IMMEDIATE` ... `COMMIT`，
  拿到写锁后再读再写，杜绝两个 worker 同时抢到同一条 queued 任务。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

_DDL = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    version TEXT NOT NULL,
    status TEXT NOT NULL,
    maturity TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    yaml_json TEXT NOT NULL,
    registered_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    version TEXT NOT NULL,
    yaml_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(agent_id, version)
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    name TEXT,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    started_at TEXT,
    finished_at TEXT,
    input_file_ids TEXT NOT NULL DEFAULT '[]',
    output_file_ids TEXT NOT NULL DEFAULT '[]',
    inputs_json TEXT NOT NULL DEFAULT '{}',
    error_message TEXT,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    conversation_id TEXT
);

CREATE TABLE IF NOT EXISTS task_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    task_id TEXT NOT NULL,
    agent_id TEXT,
    event_type TEXT NOT NULL,
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_id TEXT,
    agent_version TEXT,
    rating TEXT,
    category TEXT,
    message TEXT,
    created_by TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    tool_id TEXT NOT NULL,
    tool_version TEXT NOT NULL,
    mock INTEGER NOT NULL,
    status TEXT NOT NULL,
    input_json TEXT NOT NULL,
    output_json TEXT,
    raw_input_path TEXT,
    raw_output_path TEXT,
    error_message TEXT,
    started_at TEXT NOT NULL,
    finished_at TEXT
);

CREATE TABLE IF NOT EXISTS model_calls (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT,
    conversation_id TEXT,
    agent_id TEXT,
    model_profile TEXT NOT NULL,
    model_name TEXT,
    status TEXT NOT NULL,
    request_summary TEXT,
    response_summary TEXT,
    error_message TEXT,
    token_usage_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS samples (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    tool_id TEXT,
    tool_version TEXT,
    case_id TEXT,
    input_json TEXT NOT NULL,
    output_json TEXT,
    raw_input_path TEXT,
    raw_output_path TEXT,
    validation_status TEXT,
    accepted_by_engineer INTEGER,
    created_at TEXT NOT NULL
);

-- M6 导引 Agent（interactive 会话运行时，ADR-0012）。会话是多轮对话状态，
-- 与一次性 tasks 表正交：一次导引会话最终产出一份「预填任务草案」（recommendation），
-- 交人确认后由人经 tasks 表提交——会话本身绝不签发任务。
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    recommendation_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    recommendation_json TEXT,
    file_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);
"""

_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_tool_runs_task_id ON tool_runs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_calls_task_id ON model_calls(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_calls_conversation_id ON model_calls(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_samples_task_id ON samples(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_task_id ON feedback(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id "
    "ON conversation_messages(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id ON tasks(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON tasks(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at)",
)


def get_conn(db_path: str | Path) -> sqlite3.Connection:
    """打开一个 sqlite3 连接：Row 工厂 + WAL + 外键约束 + 手动事务模式。

    busy_timeout 显式设 5000ms：并发写的可用性此前隐式依赖 Python sqlite3
    默认 timeout=5.0（审计 P3——若有人改 connect 参数或依赖漂移，BEGIN IMMEDIATE
    竞争会立刻 database is locked）。显式声明使这一承载并发正确性的前提可见。
    """
    conn = sqlite3.connect(str(db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=5000")
    return conn


def init_db(db_path: str | Path) -> None:
    """幂等建表：CREATE TABLE IF NOT EXISTS，可重复调用。

    另含最小幂等列迁移：CREATE TABLE IF NOT EXISTS 不会给**已存在**的表补新列，
    对存量库需 ALTER TABLE 补齐（V0.1 无迁移框架，此处按列探测，重复调用安全）。
    """
    conn = get_conn(db_path)
    try:
        conn.executescript(_DDL)
        # 迁移 #1（ADR-0013）：model_calls.conversation_id——导引会话的模型调用归因。
        # 并发启动安全（Codex R1-P1）：API 进程与 Job Runner 进程都在启动时调
        # init_db，对 pre-ADR-0013 存量库，无锁的 check-then-ALTER 会让双方同时
        # 观察到「列缺失」，输家撞 duplicate column name 直接启动失败。改为先
        # BEGIN IMMEDIATE 拿写锁、锁内复查——锁内读到的列集即权威，赢家先完成
        # 迁移则此处如实跳过。
        conn.execute("BEGIN IMMEDIATE")
        try:
            cols = {row[1] for row in conn.execute("PRAGMA table_info(model_calls)")}
            if "conversation_id" not in cols:
                conn.execute("ALTER TABLE model_calls ADD COLUMN conversation_id TEXT")
            # 迁移 #2（ADR-0014/M7）：conversation_messages.file_ids——会话消息附件。
            # 同在写锁内探测补列，口径同迁移 #1。
            msg_cols = {row[1] for row in conn.execute("PRAGMA table_info(conversation_messages)")}
            if "file_ids" not in msg_cols:
                conn.execute(
                    "ALTER TABLE conversation_messages ADD COLUMN file_ids TEXT NOT NULL DEFAULT '[]'"
                )
            # 迁移 #3（ADR-0016/M8）：tasks.conversation_id——把导引协作会话产出的
            # N 个任务归到同一次会话下（协作工作台按会话分组）。可空：非会话产出的
            # 任务（门户直建）留 NULL。同在写锁内探测补列，口径同迁移 #1/#2。
            task_cols = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            if "conversation_id" not in task_cols:
                conn.execute("ALTER TABLE tasks ADD COLUMN conversation_id TEXT")
            # 索引必须在存量列迁移完成后创建，否则旧库尚无 conversation_id 时
            # 会在建表脚本阶段直接失败。与迁移共用写锁，重复启动亦幂等。
            for statement in _INDEX_DDL:
                conn.execute(statement)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
