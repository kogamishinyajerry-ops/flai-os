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
    conversation_id TEXT,
    origin TEXT NOT NULL DEFAULT 'user',
    -- data_classification（迁移 #8/ADR-0025）：不可变任务级派生分级（internal|
    -- sensitive）。可空：新任务 create 时留 NULL，执行期 runtime 落库；read 门读此
    -- 列不重派生（抗工具卸载漂移，Codex R1-B）。
    data_classification TEXT,
    -- depends_on / input_binding（迁移 #9/协作运行时 forge §3.1）：声明式任务依赖 +
    -- artifact→input 绑定。均可空 NULL=无依赖。depends_on=JSON array 上游 task_id
    -- （建时冻结、只引已存在任务 → DAG-by-construction）；input_binding=JSON
    -- （None=默认拷全部上游 output_file_ids 入本任务 input_file_ids）。
    depends_on TEXT,
    input_binding TEXT,
    -- source_binding_json（迁移 #14/版本化 DAG）：任务创建时冻结的当前轮参数与
    -- 附件来源证据。可空：存量任务、门户直建任务不冒充有来源绑定。仅 INSERT
    -- 时写入，不提供覆盖更新接口（不可变列遵守 CAS-on-NULL 边界）。
    source_binding_json TEXT,
    -- created_by_username（迁移 #9/批C，与协作运行时 forge 同期并行两支各称 #9）：发起人的
    -- 不可变唯一 username，区别于 created_by（display_name，可变且非唯一）。批C 个人贡献归因/
    -- 职责分离的身份主键——按 username 归因绝不撞名。可空：存量行留 NULL（自报时代之后才有的
    -- 追溯，不可从 display_name 反推，同迁移 #6 uploaded_by 口径）。
    created_by_username TEXT
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

-- classification（迁移 #6/ADR-0021）：internal|sensitive 数据分级轴。DDL DEFAULT
-- 只服务存量回填（mock 期数据全 internal 是如实标注）；新写入走 repos 必填 kwarg。
-- uploaded_by 仅上传端点记登录身份；runtime 产物/eval 复制件非人工标注场景留 NULL。
CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    task_id TEXT,
    kind TEXT NOT NULL,
    filename TEXT NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL,
    sha256 TEXT NOT NULL,
    created_at TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT 'internal',
    uploaded_by TEXT,
    -- 不可变认证 username；uploaded_by 继续保留 display_name 仅供人读。
    -- 存量行留 NULL，绝不从可变/可撞名 display_name 反推。
    uploaded_by_username TEXT
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
    created_at TEXT NOT NULL,
    classification TEXT NOT NULL DEFAULT 'internal'
);

-- M6 导引 Agent（interactive 会话运行时，ADR-0012）。会话是多轮对话状态，
-- 与一次性 tasks 表正交：一次导引会话最终产出一份「预填任务草案」（recommendation），
-- 交人确认后由人经 tasks 表提交——会话本身绝不签发任务。
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    created_by_username TEXT,
    -- 客户端创建幂等键。只与 owner username 组合唯一；NULL 保持旧行为。
    creation_request_id TEXT,
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

-- ADR-0031：认证会话 safe_auto 的幂等回执。相同 conversation_id/request_id
-- 至多物化一次任务；同 key 不同 request_digest 必须响亮冲突，不能静默复用。
CREATE TABLE IF NOT EXISTS conversation_dispatches (
    conversation_id TEXT NOT NULL,
    request_id TEXT NOT NULL,
    request_digest TEXT NOT NULL,
    result_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (conversation_id, request_id)
);

-- M10 治理闭环（ADR-0018）。eval_runs=评测跑批证据（case_results 回溯到真实
-- task_id 与事件时间轴；eval_cases_digest 咬合「同版本号下改 checks 后拿旧全绿
-- 证据晋升」的博弈面）。promotions=晋升审计记录（机器判定与人工确认项分离落档）。
CREATE TABLE IF NOT EXISTS eval_runs (
    id TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    triggered_by TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    total INTEGER NOT NULL DEFAULT 0,
    passed INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    skipped INTEGER NOT NULL DEFAULT 0,
    case_results_json TEXT NOT NULL DEFAULT '[]',
    draft_cases_json TEXT NOT NULL DEFAULT '[]',
    eval_cases_digest TEXT
);

-- 不可变评测快照（T2/#5）：enqueue 时把 { agent 解析配置 + 引用包文件 + approved
-- case 集 } 冻结成一行，handle=内容 sha256（内容派生、去重）。执行读快照材化而非活
-- 磁盘——enqueue 后改活包对该 run 无影响，「评的就是晋升的那版」由冻结保证而非检测。
-- handle 为 PK ⇒ 写入 INSERT OR IGNORE 即 insert-once（同 handle=同内容，二次不覆盖）。
CREATE TABLE IF NOT EXISTS eval_snapshots (
    handle TEXT PRIMARY KEY,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    eval_cases_digest TEXT,
    content_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id TEXT NOT NULL,
    agent_version TEXT NOT NULL,
    from_maturity TEXT NOT NULL,
    to_maturity TEXT NOT NULL,
    eval_run_id TEXT NOT NULL,
    checks_json TEXT NOT NULL,
    confirmations_json TEXT NOT NULL,
    confirmed_by TEXT NOT NULL,
    created_at TEXT NOT NULL
);

-- 迁移 #5（ADR-0019/M11-B1）：本地账户 + 服务端会话。新表无存量列迁移，
-- CREATE TABLE IF NOT EXISTS 即幂等。账户只由 scripts/user_admin.py 建立。
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    display_name TEXT NOT NULL,
    role TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);

-- auth_sessions 存 token 的 SHA-256（DB 文件泄露不直接换取活会话）；
-- 明文 token 只存在于 Set-Cookie。过期判定 now < expires_at 严格比较。
CREATE TABLE IF NOT EXISTS auth_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

-- 迁移 #7（ADR-0021/Codex R1 审 P1）：worker 心跳+代际。Job Runner 是独立
-- 进程——API 换到新代码而 worker 仍是旧进程时，旧 worker 落库走 DDL DEFAULT
-- 把 sensitive 派生洗白成 internal，仅探 API 的部署自检会假 PASS。worker
-- 单实例锁保证同库唯一 worker，固定 worker_id='default' 单行 upsert 不增长。
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    generation TEXT NOT NULL,
    detail TEXT,
    started_at TEXT NOT NULL,
    last_beat_at TEXT NOT NULL
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
    "CREATE INDEX IF NOT EXISTS idx_conversation_dispatches_created_at "
    "ON conversation_dispatches(created_at)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_conversations_owner_creation_request "
    "ON conversations(created_by_username, creation_request_id) "
    "WHERE creation_request_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_tasks_conversation_id ON tasks(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_agent_id ON tasks(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_tasks_status_created_at ON tasks(status, created_at)",
    "CREATE INDEX IF NOT EXISTS idx_eval_runs_agent_id ON eval_runs(agent_id)",
    # T1 异步队列 worker 的 claim 预检 + FIFO 认领（status='queued' ORDER BY started_at, id）
    # 与 running 计数（status='running'）——避免评测史增长后每 poll 全表扫（P2，Codex R1 复审）。
    "CREATE INDEX IF NOT EXISTS idx_eval_runs_status_started ON eval_runs(status, started_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_promotions_agent_id ON promotions(agent_id)",
    "CREATE INDEX IF NOT EXISTS idx_auth_sessions_user_id ON auth_sessions(user_id)",
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
            # 迁移 #4（ADR-0018/M10）：tasks.origin——eval 跑批任务与用户任务的
            # 执行方隔离轴（worker 只认 origin='user'，eval runner 只认自己建的
            # origin='eval'，两候选集不相交故双跑竞态在结构上不存在）。存量任务
            # 全部是用户任务，DEFAULT 'user' 即正确回填。同在写锁内探测补列。
            if "origin" not in task_cols:
                conn.execute(
                    "ALTER TABLE tasks ADD COLUMN origin TEXT NOT NULL DEFAULT 'user'"
                )
            # 迁移 #6（ADR-0021/M11-B2）：files/samples 数据分级轴 + 上传者追溯。
            # 存量行 DEFAULT 'internal' 即如实回填（mock 期数据全部是演示产物，
            # 同迁移 #4 origin 的裁决口径）；uploaded_by 存量留 NULL（自报时代
            # 数据不冒充有追溯）。同在写锁内探测补列。
            file_cols = {row[1] for row in conn.execute("PRAGMA table_info(files)")}
            if "classification" not in file_cols:
                conn.execute(
                    "ALTER TABLE files ADD COLUMN classification TEXT NOT NULL DEFAULT 'internal'"
                )
            if "uploaded_by" not in file_cols:
                conn.execute("ALTER TABLE files ADD COLUMN uploaded_by TEXT")
            if "uploaded_by_username" not in file_cols:
                conn.execute("ALTER TABLE files ADD COLUMN uploaded_by_username TEXT")
            sample_cols = {row[1] for row in conn.execute("PRAGMA table_info(samples)")}
            if "classification" not in sample_cols:
                conn.execute(
                    "ALTER TABLE samples ADD COLUMN classification TEXT NOT NULL DEFAULT 'internal'"
                )
            # 迁移 #8（ADR-0025）：tasks.data_classification——不可变任务级派生分级。
            # 可空（无 DEFAULT）：存量行留 NULL，由 bootstrap.assemble 按持久证据回填
            # （registry 可用处），新任务执行期由 runtime 落库；NULL=未分级，read 门
            # 兜底 fail-closed（有派生内容即封）。**不设 NOT NULL DEFAULT 'internal'**：
            # 那会把存量 monitor（0.1.0 期）任务错洗成 internal，正是 R1-B 要闭的洞。
            task_cols_v8 = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            if "data_classification" not in task_cols_v8:
                conn.execute("ALTER TABLE tasks ADD COLUMN data_classification TEXT")
            # 迁移 #9：tasks.created_by_username——发起人不可变唯一身份轴（批C 个人
            # 贡献归因/职责分离前置）。可空、无 DEFAULT：存量行留 NULL，绝不用
            # created_by（display_name）反推冒充（自报时代不冒充追溯，同迁移 #6
            # uploaded_by）。同在写锁内探测补列，口径同前八迁移。
            # 迁移 #10（协作运行时 forge §3.1）：tasks.depends_on / input_binding——
            # 声明式任务依赖 + artifact→input 绑定。均可空：存量行 NULL=无依赖，
            # 行为不变（resolver 只扫 depends_on 非空的 created 任务）。depends_on=
            # JSON array of 上游 task_id（建时冻结、只引已存在任务 → 图按构造即 DAG）；
            # input_binding=JSON（None=默认拷全部上游 output_file_ids）。
            task_cols_v9 = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            if "created_by_username" not in task_cols_v9:
                conn.execute("ALTER TABLE tasks ADD COLUMN created_by_username TEXT")
            if "depends_on" not in task_cols_v9:
                conn.execute("ALTER TABLE tasks ADD COLUMN depends_on TEXT")
            if "input_binding" not in task_cols_v9:
                conn.execute("ALTER TABLE tasks ADD COLUMN input_binding TEXT")
            # 迁移 #14（版本化 DAG 来源绑定）：任务创建时一次写入的来源证据。
            # 存量行 NULL，不从 inputs/input_file_ids 猜测或回填。
            if "source_binding_json" not in task_cols_v9:
                conn.execute("ALTER TABLE tasks ADD COLUMN source_binding_json TEXT")
            # 迁移 #11（T2/#5）：eval_runs.snapshot_handle——run 绑定其冻结快照句柄。存量 run
            # 无快照=NULL（执行侧回退活磁盘，向后兼容）。同写锁内探测补列。原 feat 分支标 #10，
            # 合并（→ main）时 #10 已被协作运行时 forge 的 depends_on/input_binding 占用，顺延 #11。
            eval_cols = {row[1] for row in conn.execute("PRAGMA table_info(eval_runs)")}
            if "snapshot_handle" not in eval_cols:
                conn.execute("ALTER TABLE eval_runs ADD COLUMN snapshot_handle TEXT")
            # 迁移 #12（ADR-0031）：conversations.created_by_username——safe_auto 的
            # 不可变所有者身份。存量会话留 NULL，绝不从可变/可撞名 display_name
            # 反推；因此存量会话只能继续 plan_only，不能取得自动执行授权。
            conversation_cols = {
                row[1] for row in conn.execute("PRAGMA table_info(conversations)")
            }
            if "created_by_username" not in conversation_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN created_by_username TEXT")
            if "creation_request_id" not in conversation_cols:
                conn.execute("ALTER TABLE conversations ADD COLUMN creation_request_id TEXT")
            # 迁移 #13（ADR-0031 授权审查）：用户角色轴。旧系统所有认证账户均可
            # 调用全部任务端点，迁移为 admin 是对既有权限的显式化而非扩权；新账户
            # 由 create_user 显式写角色（默认 business_user）。异常 NULL 在执行门拒绝。
            user_cols = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
            if "role" not in user_cols:
                conn.execute("ALTER TABLE users ADD COLUMN role TEXT")
                conn.execute("UPDATE users SET role = 'admin' WHERE role IS NULL")
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
