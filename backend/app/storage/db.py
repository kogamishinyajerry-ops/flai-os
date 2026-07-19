"""sqlite3 连接与九表 DDL（ADR-0008：stdlib sqlite3 + 仓储函数层，不引 ORM）。

连接采用 isolation_level=None（Python sqlite3 的"手动事务"模式）：
- 普通读写语句保持事实上的 autocommit，调用方无需逐条 commit；
- 需要原子性的地方（claim_next_queued）显式 `BEGIN IMMEDIATE` ... `COMMIT`，
  拿到写锁后再读再写，杜绝两个 worker 同时抢到同一条 queued 任务。
"""

from __future__ import annotations

import json
import sqlite3
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path

from .. import config

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
    -- created_by_username（迁移 #9/批C，与协作运行时 forge 同期并行两支各称 #9）：发起人的
    -- 不可变唯一 username，区别于 created_by（display_name，可变且非唯一）。批C 个人贡献归因/
    -- 职责分离的身份主键——按 username 归因绝不撞名。可空：存量行留 NULL（自报时代之后才有的
    -- 追溯，不可从 display_name 反推，同迁移 #6 uploaded_by 口径）。
    created_by_username TEXT,
    -- retry_of（迁移 #12/评审 N4b）：「复制为新任务」的血缘注记——本任务复制自哪个
    -- 既有任务。纯元数据：不改队列/审计/管道语义（inputs 由前端复制进请求体、附件仍走
    -- kind=input 白名单），resolver/review/worker 均不读此列。可空 NULL=非重跑任务。
    retry_of TEXT
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

-- P2.1 live cursor v1 derives per-task sequence from immutable insertion
-- order.  Enforce that premise in SQLite so UPDATE/DELETE cannot silently
-- renumber COUNT+OFFSET cursors while an old anchor still appears valid.
CREATE TRIGGER IF NOT EXISTS trg_task_events_no_update
BEFORE UPDATE ON task_events
BEGIN
    SELECT RAISE(ABORT, 'task_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_task_events_no_delete
BEFORE DELETE ON task_events
BEGIN
    SELECT RAISE(ABORT, 'task_events is append-only');
END;

-- SQLite INSERT OR REPLACE can perform an implicit uniqueness-conflict delete.
-- Reject the conflicting INSERT before that algorithm can rewrite an existing
-- event, including callers that explicitly target the internal integer id.
CREATE TRIGGER IF NOT EXISTS trg_task_events_no_conflicting_insert
BEFORE INSERT ON task_events
WHEN EXISTS (
    SELECT 1 FROM task_events
    WHERE event_id = NEW.event_id OR (NEW.id <> -1 AND id = NEW.id)
)
BEGIN
    SELECT RAISE(ABORT, 'task_events is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_task_events_positive_rowid
AFTER INSERT ON task_events
WHEN NEW.rowid <= 0
BEGIN
    SELECT RAISE(ABORT, 'task event internal rowid must be positive');
END;

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
    uploaded_by TEXT
);

-- M4 前置结果遥测（ADR-0036）：只为新代码上线后的人签权威产物建立
-- observation cohort，绝不扫描/回填历史。capture_started 仅表示采集器从该产物
-- 开始生效，不是使用结果；full_download / pipeline_handoff 才是两个 lower-bound
-- flow signal，且分别只能解释为「完整正文已交付」/「已流入下游任务」。
CREATE TABLE IF NOT EXISTS artifact_outcome_events (
    id TEXT PRIMARY KEY NOT NULL,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('capture_started', 'full_download', 'pipeline_handoff')
    ),
    source_task_id TEXT NOT NULL REFERENCES tasks(id),
    source_file_id TEXT NOT NULL REFERENCES files(id),
    review_event_id TEXT NOT NULL REFERENCES task_events(event_id),
    source_task_witness_json TEXT,
    source_file_witness_json TEXT,
    actor_username TEXT,
    downstream_task_id TEXT REFERENCES tasks(id),
    delivered_bytes INTEGER,
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    created_at TEXT NOT NULL,
    CHECK (
        (
            event_type = 'capture_started'
            AND actor_username IS NULL
            AND downstream_task_id IS NULL
            AND delivered_bytes IS NULL
        )
        OR (
            event_type = 'full_download'
            AND actor_username IS NOT NULL
            AND length(trim(actor_username, char(
                9,10,11,12,13,28,29,30,31,32,133,160,5760,
                8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,
                8232,8233,8239,8287,12288
            ))) > 0
            AND downstream_task_id IS NULL
            AND delivered_bytes IS NOT NULL
            AND delivered_bytes >= 0
        )
        OR (
            event_type = 'pipeline_handoff'
            AND actor_username IS NULL
            AND downstream_task_id IS NOT NULL
            AND delivered_bytes IS NULL
        )
    )
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

-- 判断资产化：机器顾问候选与人工终裁物理隔离。机器表只表达
-- clear/concerns/abstain，绝不承载 approve/reject 人签动作。
CREATE TABLE IF NOT EXISTS task_review_advice (
    id TEXT PRIMARY KEY NOT NULL,
    task_id TEXT NOT NULL REFERENCES tasks(id),
    model_call_id INTEGER NOT NULL UNIQUE REFERENCES model_calls(id),
    advisor_id TEXT NOT NULL,
    advisor_version TEXT NOT NULL,
    model_profile TEXT NOT NULL,
    model_name TEXT,
    advisory_outcome TEXT NOT NULL CHECK (
        advisory_outcome IN ('clear', 'concerns', 'abstain')
    ),
    doubts_json TEXT NOT NULL CHECK (
        json_valid(doubts_json) AND json_type(doubts_json) = 'array'
    ),
    evidence_file_ids_json TEXT NOT NULL DEFAULT '[]' CHECK (
        json_valid(evidence_file_ids_json)
        AND json_type(evidence_file_ids_json) = 'array'
    ),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_human_decisions (
    id TEXT PRIMARY KEY NOT NULL,
    task_id TEXT NOT NULL UNIQUE REFERENCES tasks(id),
    paired_advice_id TEXT REFERENCES task_review_advice(id),
    action TEXT NOT NULL CHECK (action IN ('approve', 'reject')),
    reason_code TEXT CHECK (
        reason_code IS NULL OR reason_code IN (
            'source_doubt', 'method_error', 'conclusion_overreach',
            'insufficient_evidence', 'classification_issue', 'other'
        )
    ),
    comment TEXT CHECK (comment IS NULL OR length(comment) <= 2000),
    reviewer_username TEXT NOT NULL CHECK (
        length(trim(reviewer_username, char(
            9,10,11,12,13,28,29,30,31,32,133,160,5760,
            8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,
            8232,8233,8239,8287,12288
        ))) > 0
    ),
    reviewer_display_name TEXT NOT NULL CHECK (
        length(trim(reviewer_display_name, char(
            9,10,11,12,13,28,29,30,31,32,133,160,5760,
            8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,
            8232,8233,8239,8287,12288
        ))) > 0
    ),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    created_at TEXT NOT NULL,
    CHECK (
        (action = 'approve' AND reason_code IS NULL)
        OR (action = 'reject' AND reason_code IS NOT NULL)
    ),
    CHECK (
        reason_code <> 'other'
        OR (comment IS NOT NULL AND length(trim(comment, char(
            9,10,11,12,13,28,29,30,31,32,133,160,5760,
            8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,
            8232,8233,8239,8287,12288
        ))) > 0)
    )
);

-- ADR-0035 fixed point: every persisted signer event receives an immutable,
-- byte-exact snapshot.  ``legacy_pre_instrumentation`` rows are written only
-- once by init_db while upgrading a database that predates the strict review
-- event generation; runtime inserts are limited by a canonical trigger to
-- ``structured_v1``.  Keeping the task_events internal integer identity in the
-- witness closes drop-guard -> rowid rewrite -> restore false-green paths.
CREATE TABLE IF NOT EXISTS task_review_event_witnesses (
    event_id TEXT PRIMARY KEY NOT NULL REFERENCES task_events(event_id),
    event_internal_id INTEGER NOT NULL UNIQUE CHECK (event_internal_id > 0),
    task_id TEXT NOT NULL REFERENCES tasks(id),
    agent_id TEXT,
    event_type TEXT NOT NULL CHECK (
        event_type IN ('review_approved', 'review_rejected')
    ),
    level TEXT NOT NULL,
    message TEXT NOT NULL,
    payload_json TEXT NOT NULL CHECK (
        json_valid(payload_json) AND json_type(payload_json) = 'object'
    ),
    created_at TEXT NOT NULL,
    decision_id TEXT UNIQUE REFERENCES task_human_decisions(id),
    witness_kind TEXT NOT NULL CHECK (
        witness_kind IN ('legacy_pre_instrumentation', 'structured_v1')
    ),
    schema_version INTEGER NOT NULL CHECK (schema_version = 1),
    CHECK (
        (witness_kind = 'legacy_pre_instrumentation' AND decision_id IS NULL)
        OR (witness_kind = 'structured_v1' AND decision_id IS NOT NULL)
    ),
    CHECK (
        typeof(event_id) = 'text'
        AND typeof(event_internal_id) = 'integer'
        AND typeof(task_id) = 'text'
        AND typeof(agent_id) IN ('null', 'text')
        AND typeof(event_type) = 'text'
        AND typeof(level) = 'text'
        AND typeof(message) = 'text'
        AND typeof(payload_json) = 'text'
        AND typeof(created_at) = 'text'
        AND typeof(decision_id) IN ('null', 'text')
        AND typeof(witness_kind) = 'text'
        AND typeof(schema_version) = 'integer'
    )
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
    id TEXT PRIMARY KEY NOT NULL,
    agent_id TEXT NOT NULL,
    status TEXT NOT NULL,
    created_by TEXT NOT NULL,
    -- 迁移 #14（P2.3）：会话稳定 owner 的唯一身份键。created_by 仍是展示名
    -- （可撞名）；本列存认证 principal 的 exact username。可空仅为 legacy：
    -- 存量 NULL 不从 display_name 猜 owner，也不向普通用户开放认领。
    created_by_username TEXT,
    recommendation_json TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS conversation_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    -- 迁移 #15（P2.3）：对外稳定消息 id。内部自增 id 仅负责严格插入顺序，
    -- 不再泄漏为公开引用；legacy 行在 init_db 写锁内一次性回填。
    message_id TEXT NOT NULL UNIQUE,
    conversation_id TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    recommendation_json TEXT,
    file_ids TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL
);

-- P2.3 普通会话澄清 Question。status 不落库：pending/answered/expired/
-- superseded 均由 closed_reason + expires_at 在仓储投影时推导。问题规格列冻结；
-- resolution tuple 要么全空、要么一次性完整闭合，避免半回答事实。
CREATE TABLE IF NOT EXISTS conversation_questions (
    id TEXT PRIMARY KEY NOT NULL,
    conversation_id TEXT NOT NULL,
    prompt_message_id TEXT NOT NULL,
    asked_to_username TEXT NOT NULL,
    revision INTEGER NOT NULL CHECK (revision = 1),
    kind TEXT NOT NULL CHECK (kind IN ('single_choice', 'free_text')),
    prompt TEXT NOT NULL,
    description TEXT,
    options_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    closed_reason TEXT CHECK (
        closed_reason IS NULL
        OR closed_reason IN ('answered', 'expired', 'superseded')
    ),
    closed_at TEXT,
    submission_id TEXT,
    answer_json TEXT,
    answered_by_username TEXT,
    answer_message_id TEXT,
    response_message_id TEXT,
    CHECK (
        (
            closed_reason IS NULL
            AND closed_at IS NULL
            AND submission_id IS NULL
            AND answer_json IS NULL
            AND answered_by_username IS NULL
            AND answer_message_id IS NULL
            AND response_message_id IS NULL
        )
        OR (
            closed_reason IN ('expired', 'superseded')
            AND closed_at IS NOT NULL
            AND submission_id IS NULL
            AND answer_json IS NULL
            AND answered_by_username IS NULL
            AND answer_message_id IS NULL
            AND response_message_id IS NULL
        )
        OR (
            closed_reason = 'answered'
            AND closed_at IS NOT NULL
            AND submission_id IS NOT NULL
            AND answer_json IS NOT NULL
            AND answered_by_username IS NOT NULL
            AND answered_by_username = asked_to_username
            AND answer_message_id IS NOT NULL
            AND response_message_id IS NOT NULL
            AND response_message_id <> prompt_message_id
        )
    )
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

-- 迁移 #13（批八/ADR-0031）：专家团队模板。teams=蓝本头（owner_user 取 username
-- 唯一键，同 created_by_username 口径；created_from_conversation_id=血缘，会话可
-- 后删故不设 FK）；team_members=席位（seq 主键轴，同 agent 可多席；after_json=
-- 同团队内前序 seq 列表，仅可引用更小 seq → 按构造 DAG；agent_version_at_save=
-- 保存时点版本快照，summon 对账基准防漂移伪史）。新表 IF NOT EXISTS 即幂等。
CREATE TABLE IF NOT EXISTS teams (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    goal_template TEXT,
    owner_user TEXT NOT NULL,
    created_from_conversation_id TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS team_members (
    team_id TEXT NOT NULL REFERENCES teams(id),
    agent_id TEXT NOT NULL,
    agent_version_at_save TEXT NOT NULL,
    role TEXT,
    seq INTEGER NOT NULL,
    after_json TEXT,
    PRIMARY KEY (team_id, seq)
);
"""

_JUDGMENT_OBJECT_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_task_review_advice_task_created "
    "ON task_review_advice(task_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_task_human_decisions_paired_advice "
    "ON task_human_decisions(paired_advice_id) "
    "WHERE paired_advice_id IS NOT NULL",
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_model_call_witness
    BEFORE INSERT ON task_review_advice
    WHEN NOT EXISTS (
        SELECT 1
        FROM model_calls
        WHERE id = NEW.model_call_id
          AND task_id = NEW.task_id
          AND status = 'success'
          AND agent_id IS NEW.advisor_id
          AND model_profile IS NEW.model_profile
          AND model_name IS NEW.model_name
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'advice requires same-task successful model call with exact provenance'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_validate_doubts
    BEFORE INSERT ON task_review_advice
    WHEN (
        (NEW.advisory_outcome = 'clear' AND json_array_length(NEW.doubts_json) <> 0)
        OR (NEW.advisory_outcome = 'concerns' AND json_array_length(NEW.doubts_json) = 0)
        OR json_array_length(NEW.doubts_json) > 20
        OR EXISTS (
            SELECT 1
            FROM json_each(NEW.doubts_json) AS doubt
            WHERE doubt.type <> 'object'
               OR (SELECT COUNT(*) FROM json_each(doubt.value)) <> 2
               OR NOT EXISTS (
                   SELECT 1
                   FROM json_each(doubt.value) AS field
                   WHERE field.key = 'code'
                     AND field.type = 'text'
                     AND field.value IN (
                         'source_doubt', 'method_error', 'conclusion_overreach',
                         'insufficient_evidence', 'classification_issue', 'other'
                     )
               )
               OR NOT EXISTS (
                   SELECT 1
                   FROM json_each(doubt.value) AS field
                   WHERE field.key = 'detail'
                     AND field.type = 'text'
                     AND length(trim(field.value, char(
                         9,10,11,12,13,28,29,30,31,32,133,160,5760,
                         8192,8193,8194,8195,8196,8197,8198,8199,
                         8200,8201,8202,8232,8233,8239,8287,12288
                     ))) > 0
                     AND length(field.value) <= 2000
               )
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'invalid advice doubts contract');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_validate_evidence
    BEFORE INSERT ON task_review_advice
    WHEN (
        json_array_length(NEW.evidence_file_ids_json) > 50
        OR (
            SELECT COUNT(*) FROM json_each(NEW.evidence_file_ids_json)
        ) <> (
            SELECT COUNT(DISTINCT value)
            FROM json_each(NEW.evidence_file_ids_json)
        )
        OR EXISTS (
            SELECT 1
            FROM json_each(NEW.evidence_file_ids_json) AS ref
            WHERE ref.type <> 'text'
               OR length(ref.value) = 0
               OR length(ref.value) > 100
               OR NOT EXISTS (
                   SELECT 1 FROM files WHERE id = ref.value
               )
               OR NOT EXISTS (
                   SELECT 1
                   FROM tasks AS task
                   WHERE task.id = NEW.task_id
                     AND (
                         EXISTS (
                             SELECT 1 FROM json_each(task.input_file_ids) AS input_ref
                             WHERE input_ref.type = 'text'
                               AND input_ref.value = ref.value
                         )
                         OR EXISTS (
                             SELECT 1 FROM json_each(task.output_file_ids) AS output_ref
                             WHERE output_ref.type = 'text'
                               AND output_ref.value = ref.value
                         )
                     )
               )
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'invalid advice evidence references');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_validate_storage
    BEFORE INSERT ON task_review_advice
    WHEN (NEW.id IS NOT NULL AND typeof(NEW.id) <> 'text')
         OR typeof(NEW.task_id) <> 'text'
         OR typeof(NEW.model_call_id) <> 'integer'
         OR typeof(NEW.advisor_id) <> 'text'
         OR typeof(NEW.advisor_version) <> 'text'
         OR typeof(NEW.model_profile) <> 'text'
         OR typeof(NEW.model_name) NOT IN ('null', 'text')
         OR typeof(NEW.advisory_outcome) <> 'text'
         OR typeof(NEW.doubts_json) <> 'text'
         OR typeof(NEW.evidence_file_ids_json) <> 'text'
         OR typeof(NEW.schema_version) <> 'integer'
         OR NOT (
             typeof(NEW.created_at) = 'text'
             AND (
                 NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'
                 OR NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
             )
             AND julianday(NEW.created_at) IS NOT NULL
         )
    BEGIN
        SELECT RAISE(ABORT, 'invalid advice storage classes or timestamp');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_no_update
    BEFORE UPDATE ON task_review_advice
    BEGIN
        SELECT RAISE(ABORT, 'task_review_advice is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_no_delete
    BEFORE DELETE ON task_review_advice
    BEGIN
        SELECT RAISE(ABORT, 'task_review_advice is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_no_conflicting_insert
    BEFORE INSERT ON task_review_advice
    WHEN EXISTS (
        SELECT 1 FROM task_review_advice
        WHERE (NEW.rowid <> -1 AND rowid = NEW.rowid)
           OR id = NEW.id
           OR model_call_id = NEW.model_call_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'task_review_advice is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_advice_positive_rowid
    AFTER INSERT ON task_review_advice
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'advice internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_model_calls_no_update
    BEFORE UPDATE ON model_calls
    WHEN EXISTS (
        SELECT 1 FROM task_review_advice
        WHERE model_call_id = OLD.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'witnessed model_call is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_model_calls_no_delete
    BEFORE DELETE ON model_calls
    WHEN EXISTS (
        SELECT 1 FROM task_review_advice
        WHERE model_call_id = OLD.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'witnessed model_call is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_model_calls_no_conflicting_insert
    BEFORE INSERT ON model_calls
    WHEN EXISTS (
        SELECT 1
        FROM task_review_advice AS advice
        JOIN model_calls AS model_call ON model_call.id = advice.model_call_id
        WHERE NEW.id <> -1 AND model_call.id = NEW.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'witnessed model_call is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_model_calls_no_conflicting_update
    BEFORE UPDATE ON model_calls
    WHEN NEW.id IS NOT OLD.id
         AND EXISTS (
             SELECT 1 FROM task_review_advice
             WHERE model_call_id = NEW.id
         )
    BEGIN
        SELECT RAISE(ABORT, 'witnessed model_call is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_model_calls_positive_rowid
    AFTER INSERT ON model_calls
    WHEN NEW.id <= 0
    BEGIN
        SELECT RAISE(ABORT, 'model call internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_pair_same_task
    BEFORE INSERT ON task_human_decisions
    WHEN NEW.paired_advice_id IS NOT NULL
         AND NOT EXISTS (
             SELECT 1 FROM task_review_advice
             WHERE id = NEW.paired_advice_id AND task_id = NEW.task_id
         )
    BEGIN
        SELECT RAISE(ABORT, 'paired advice must belong to same task');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_validate_storage
    BEFORE INSERT ON task_human_decisions
    WHEN (NEW.id IS NOT NULL AND typeof(NEW.id) <> 'text')
         OR typeof(NEW.task_id) <> 'text'
         OR typeof(NEW.paired_advice_id) NOT IN ('null', 'text')
         OR typeof(NEW.action) <> 'text'
         OR typeof(NEW.reason_code) NOT IN ('null', 'text')
         OR typeof(NEW.comment) NOT IN ('null', 'text')
         OR typeof(NEW.reviewer_username) <> 'text'
         OR typeof(NEW.reviewer_display_name) <> 'text'
         OR typeof(NEW.schema_version) <> 'integer'
         OR NOT (
             typeof(NEW.created_at) = 'text'
             AND (
                 NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'
                 OR NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
             )
             AND julianday(NEW.created_at) IS NOT NULL
         )
    BEGIN
        SELECT RAISE(ABORT, 'invalid decision storage classes or timestamp');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_waiting_review_witness
    BEFORE INSERT ON task_human_decisions
    WHEN NOT EXISTS (
             SELECT 1 FROM task_human_decisions
             WHERE id = NEW.id OR task_id = NEW.task_id
         )
         AND NOT EXISTS (
             SELECT 1 FROM tasks
             WHERE id = NEW.task_id AND status = 'waiting_review'
         )
    BEGIN
        SELECT RAISE(ABORT, 'human decision requires waiting_review task');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_no_update
    BEFORE UPDATE ON task_human_decisions
    BEGIN
        SELECT RAISE(ABORT, 'task_human_decisions is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_no_delete
    BEFORE DELETE ON task_human_decisions
    BEGIN
        SELECT RAISE(ABORT, 'task_human_decisions is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_no_conflicting_insert
    BEFORE INSERT ON task_human_decisions
    WHEN EXISTS (
        SELECT 1 FROM task_human_decisions
        WHERE (NEW.rowid <> -1 AND rowid = NEW.rowid)
           OR id = NEW.id
           OR task_id = NEW.task_id
    )
    BEGIN
        SELECT RAISE(ABORT, 'task_human_decisions is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_human_decisions_positive_rowid
    AFTER INSERT ON task_human_decisions
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'decision internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_event_witnesses_validate_insert
    BEFORE INSERT ON task_review_event_witnesses
    WHEN NEW.witness_kind IS NOT 'structured_v1'
         OR NEW.decision_id IS NULL
         OR NOT (
             typeof(NEW.created_at) = 'text'
             AND (
                 NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'
                 OR NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
             )
             AND julianday(NEW.created_at) IS NOT NULL
         )
         OR NOT EXISTS (
             SELECT 1
             FROM task_events AS review
             JOIN task_human_decisions AS decision
               ON decision.id = NEW.decision_id
              AND decision.task_id = review.task_id
             JOIN tasks AS task ON task.id = decision.task_id
             WHERE review.event_id = NEW.event_id
               AND review.id = NEW.event_internal_id
               AND review.task_id IS NEW.task_id
               AND review.agent_id IS NEW.agent_id
               AND review.event_type IS NEW.event_type
               AND review.level IS NEW.level
               AND review.message IS NEW.message
               AND review.payload_json IS NEW.payload_json
               AND review.created_at IS NEW.created_at
               AND review.agent_id IS task.agent_id
               AND review.event_type = CASE decision.action
                   WHEN 'approve' THEN 'review_approved'
                   ELSE 'review_rejected'
               END
               AND review.level = CASE decision.action
                   WHEN 'approve' THEN 'info'
                   ELSE 'warning'
               END
               AND json_type(review.payload_json, '$.decision_id') = 'text'
               AND json_extract(review.payload_json, '$.decision_id') IS decision.id
         )
    BEGIN
        SELECT RAISE(ABORT, 'invalid structured review event witness');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_event_witnesses_no_update
    BEFORE UPDATE ON task_review_event_witnesses
    BEGIN
        SELECT RAISE(ABORT, 'task_review_event_witnesses is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_event_witnesses_no_delete
    BEFORE DELETE ON task_review_event_witnesses
    BEGIN
        SELECT RAISE(ABORT, 'task_review_event_witnesses is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_event_witnesses_no_conflicting_insert
    BEFORE INSERT ON task_review_event_witnesses
    WHEN EXISTS (
        SELECT 1 FROM task_review_event_witnesses
        WHERE event_id = NEW.event_id
           OR event_internal_id = NEW.event_internal_id
           OR (
               NEW.decision_id IS NOT NULL
               AND decision_id = NEW.decision_id
           )
           OR (NEW.rowid <> -1 AND rowid = NEW.rowid)
    )
    BEGIN
        SELECT RAISE(ABORT, 'task_review_event_witnesses is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_review_event_witnesses_positive_rowid
    AFTER INSERT ON task_review_event_witnesses
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'review event witness internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_structured_review_events_decision_witness
    BEFORE INSERT ON task_events
    WHEN NEW.event_type IN ('review_approved', 'review_rejected')
         AND (
             typeof(NEW.payload_json) <> 'text'
             OR json_valid(NEW.payload_json) IS NOT 1
             OR json_type(
                 CASE WHEN json_valid(NEW.payload_json)
                      THEN NEW.payload_json ELSE '{}'
                 END
             ) IS NOT 'object'
             OR (SELECT COUNT(*) FROM json_each(NEW.payload_json)) <> 6
             OR (
                 SELECT COUNT(DISTINCT key)
                 FROM json_each(NEW.payload_json)
             ) <> 6
             OR EXISTS (
                 SELECT 1 FROM json_each(NEW.payload_json) AS field
                 WHERE field.key NOT IN (
                     'reviewer', 'reviewer_username', 'comment',
                     'decision_id', 'reason_code', 'paired_advice_id'
                 )
             )
             OR NOT EXISTS (
                 SELECT 1
                 FROM task_human_decisions AS decision
                 JOIN tasks AS task ON task.id = decision.task_id
                 WHERE decision.task_id = NEW.task_id
                   AND task.status = 'waiting_review'
                   AND NEW.agent_id IS task.agent_id
                   AND NEW.event_type = CASE decision.action
                       WHEN 'approve' THEN 'review_approved'
                       ELSE 'review_rejected'
                   END
                   AND NEW.level = CASE decision.action
                       WHEN 'approve' THEN 'info'
                       ELSE 'warning'
                   END
                   AND json_type(NEW.payload_json, '$.decision_id') = 'text'
                   AND json_extract(NEW.payload_json, '$.decision_id') IS decision.id
                   AND json_type(NEW.payload_json, '$.reviewer') = 'text'
                   AND json_extract(NEW.payload_json, '$.reviewer')
                       IS decision.reviewer_display_name
                   AND json_type(
                       NEW.payload_json, '$.reviewer_username'
                   ) = 'text'
                   AND json_extract(
                       NEW.payload_json, '$.reviewer_username'
                   ) IS decision.reviewer_username
                   AND (
                       (decision.comment IS NULL
                        AND json_type(NEW.payload_json, '$.comment') = 'null')
                       OR (decision.comment IS NOT NULL
                           AND json_type(NEW.payload_json, '$.comment') = 'text'
                           AND json_extract(NEW.payload_json, '$.comment')
                               IS decision.comment)
                   )
                   AND (
                       (decision.reason_code IS NULL
                        AND json_type(NEW.payload_json, '$.reason_code') = 'null')
                       OR (decision.reason_code IS NOT NULL
                           AND json_type(NEW.payload_json, '$.reason_code') = 'text'
                           AND json_extract(NEW.payload_json, '$.reason_code')
                               IS decision.reason_code)
                   )
                   AND (
                       (decision.paired_advice_id IS NULL
                        AND json_type(
                            NEW.payload_json, '$.paired_advice_id'
                        ) = 'null')
                       OR (decision.paired_advice_id IS NOT NULL
                           AND json_type(
                               NEW.payload_json, '$.paired_advice_id'
                           ) = 'text'
                           AND json_extract(
                               NEW.payload_json, '$.paired_advice_id'
                           ) IS decision.paired_advice_id)
                   )
             )
             OR EXISTS (
                 SELECT 1
                 FROM task_events AS existing
                 WHERE existing.event_type IN (
                     'review_approved', 'review_rejected'
                 )
                   AND json_valid(existing.payload_json) = 1
                   AND json_type(existing.payload_json) = 'object'
                   AND json_extract(existing.payload_json, '$.decision_id')
                       IS json_extract(NEW.payload_json, '$.decision_id')
             )
         )
    BEGIN
        SELECT RAISE(
            ABORT,
            'invalid or duplicate structured review event'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_structured_review_events_capture_witness
    AFTER INSERT ON task_events
    WHEN NEW.event_type IN ('review_approved', 'review_rejected')
    BEGIN
        INSERT INTO task_review_event_witnesses (
            event_id, event_internal_id, task_id, agent_id, event_type,
            level, message, payload_json, created_at, decision_id,
            witness_kind, schema_version
        ) VALUES (
            NEW.event_id, NEW.id, NEW.task_id, NEW.agent_id, NEW.event_type,
            NEW.level, NEW.message, NEW.payload_json, NEW.created_at,
            json_extract(NEW.payload_json, '$.decision_id'),
            'structured_v1', 1
        );
    END
    """,
)

_JUDGMENT_MANAGED_INDEXES = (
    "idx_task_review_advice_task_created",
    "idx_task_human_decisions_paired_advice",
)

_JUDGMENT_MANAGED_TRIGGERS = (
    "trg_task_review_advice_model_call_witness",
    "trg_task_review_advice_validate_doubts",
    "trg_task_review_advice_validate_evidence",
    "trg_task_review_advice_validate_storage",
    "trg_task_review_advice_no_update",
    "trg_task_review_advice_no_delete",
    "trg_task_review_advice_no_conflicting_insert",
    "trg_task_review_advice_positive_rowid",
    "trg_witnessed_model_calls_no_update",
    "trg_witnessed_model_calls_no_delete",
    "trg_witnessed_model_calls_no_conflicting_insert",
    "trg_witnessed_model_calls_no_conflicting_update",
    "trg_model_calls_positive_rowid",
    "trg_task_human_decisions_pair_same_task",
    "trg_task_human_decisions_validate_storage",
    "trg_task_human_decisions_waiting_review_witness",
    "trg_task_human_decisions_no_update",
    "trg_task_human_decisions_no_delete",
    "trg_task_human_decisions_no_conflicting_insert",
    "trg_task_human_decisions_positive_rowid",
    "trg_task_review_event_witnesses_validate_insert",
    "trg_task_review_event_witnesses_no_update",
    "trg_task_review_event_witnesses_no_delete",
    "trg_task_review_event_witnesses_no_conflicting_insert",
    "trg_task_review_event_witnesses_positive_rowid",
    "trg_structured_review_events_decision_witness",
    "trg_structured_review_events_capture_witness",
)

_OUTCOME_OBJECT_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_artifact_outcomes_source_created "
    "ON artifact_outcome_events(source_file_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_artifact_outcomes_source_task_created "
    "ON artifact_outcome_events(source_task_id, created_at, id)",
    "CREATE INDEX IF NOT EXISTS idx_artifact_outcomes_downstream_created "
    "ON artifact_outcome_events(downstream_task_id, created_at, id) "
    "WHERE downstream_task_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_artifact_outcomes_one_capture "
    "ON artifact_outcome_events(source_file_id) "
    "WHERE event_type = 'capture_started'",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_artifact_outcomes_one_handoff "
    "ON artifact_outcome_events(source_file_id, downstream_task_id) "
    "WHERE event_type = 'pipeline_handoff'",
    # task_events carries the exact review_approved parent of every capture.
    # These definitions intentionally duplicate the fresh-schema DDL above so
    # empty-ledger convergence can drop/recreate them, while nonempty evidence
    # is preflighted before any repair.  Keep the SQL bodies byte-equivalent
    # after whitespace normalization: outcome_schema compares exact digests.
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_events_no_update
    BEFORE UPDATE ON task_events
    BEGIN
        SELECT RAISE(ABORT, 'task_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_events_no_delete
    BEFORE DELETE ON task_events
    BEGIN
        SELECT RAISE(ABORT, 'task_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_events_no_conflicting_insert
    BEFORE INSERT ON task_events
    WHEN EXISTS (
        SELECT 1 FROM task_events
        WHERE event_id = NEW.event_id OR (NEW.id <> -1 AND id = NEW.id)
    )
    BEGIN
        SELECT RAISE(ABORT, 'task_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_task_events_positive_rowid
    AFTER INSERT ON task_events
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'task event internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_source_witness
    BEFORE INSERT ON artifact_outcome_events
    WHEN NOT EXISTS (
        SELECT 1
        FROM tasks AS source_task
        JOIN files AS source_file
          ON source_file.id = NEW.source_file_id
         AND source_file.task_id = source_task.id
         AND source_file.kind = 'output'
        JOIN task_events AS review_event
          ON review_event.event_id = NEW.review_event_id
         AND review_event.task_id = source_task.id
         AND review_event.event_type = 'review_approved'
        JOIN task_review_event_witnesses AS review_witness
          ON review_witness.event_id = review_event.event_id
         AND review_witness.event_internal_id = review_event.id
         AND review_witness.task_id = review_event.task_id
         AND review_witness.agent_id IS review_event.agent_id
         AND review_witness.event_type = review_event.event_type
         AND review_witness.level = review_event.level
         AND review_witness.message = review_event.message
         AND review_witness.payload_json = review_event.payload_json
         AND review_witness.created_at = review_event.created_at
         AND review_witness.witness_kind = 'structured_v1'
         AND review_witness.schema_version = 1
        JOIN task_human_decisions AS decision
          ON decision.id = review_witness.decision_id
         AND decision.task_id = source_task.id
         AND decision.action = 'approve'
        WHERE source_task.id = NEW.source_task_id
          AND source_task.origin = 'user'
          AND source_task.status = 'completed'
          AND NEW.source_task_witness_json IS json_object(
              'agent_id', source_task.agent_id,
              'agent_version', source_task.agent_version,
              'conversation_id', source_task.conversation_id,
              'created_at', source_task.created_at,
              'created_by', source_task.created_by,
              'created_by_username', source_task.created_by_username,
              'data_classification', source_task.data_classification,
              'depends_on', source_task.depends_on,
              'error_message', source_task.error_message,
              'finished_at', source_task.finished_at,
              'id', source_task.id,
              'input_binding', source_task.input_binding,
              'input_file_ids', source_task.input_file_ids,
              'inputs_json', source_task.inputs_json,
              'metadata_json', source_task.metadata_json,
              'name', source_task.name,
              'origin', source_task.origin,
              'output_file_ids', source_task.output_file_ids,
              'retry_of', source_task.retry_of,
              'rowid', source_task.rowid,
              'started_at', source_task.started_at,
              'status', source_task.status,
              'updated_at', source_task.updated_at
          )
          AND NEW.source_file_witness_json IS json_object(
              'classification', source_file.classification,
              'created_at', source_file.created_at,
              'filename', source_file.filename,
              'id', source_file.id,
              'kind', source_file.kind,
              'path', source_file.path,
              'rowid', source_file.rowid,
              'sha256', source_file.sha256,
              'size_bytes', source_file.size_bytes,
              'task_id', source_file.task_id,
              'uploaded_by', source_file.uploaded_by
          )
          AND json_type(
              CASE
                  WHEN json_valid(review_event.payload_json)
                  THEN review_event.payload_json ELSE '{}'
              END,
              '$.decision_id'
          ) = 'text'
          AND decision.id = json_extract(
              CASE
                  WHEN json_valid(review_event.payload_json)
                  THEN review_event.payload_json ELSE '{}'
              END,
              '$.decision_id'
          )
          AND EXISTS (
              SELECT 1
              FROM json_each(
                  CASE
                      WHEN json_valid(source_task.output_file_ids)
                       AND json_type(source_task.output_file_ids) = 'array'
                      THEN source_task.output_file_ids ELSE '[]'
                  END
              ) AS output_ref
              WHERE output_ref.type = 'text'
                AND output_ref.value = NEW.source_file_id
          )
    )
    BEGIN
        SELECT RAISE(
            ABORT,
            'outcome requires user source, authoritative output, and exact approval decision'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_validate_shape
    BEFORE INSERT ON artifact_outcome_events
    WHEN typeof(NEW.id) <> 'text'
         OR typeof(NEW.event_type) <> 'text'
         OR typeof(NEW.source_task_id) <> 'text'
         OR typeof(NEW.source_file_id) <> 'text'
         OR typeof(NEW.review_event_id) <> 'text'
         OR typeof(NEW.source_task_witness_json) <> 'text'
         OR json_valid(NEW.source_task_witness_json) IS NOT 1
         OR json_type(NEW.source_task_witness_json) IS NOT 'object'
         OR typeof(NEW.source_file_witness_json) <> 'text'
         OR json_valid(NEW.source_file_witness_json) IS NOT 1
         OR json_type(NEW.source_file_witness_json) IS NOT 'object'
         OR typeof(NEW.schema_version) <> 'integer'
         OR NEW.schema_version IS NOT 1
         OR NOT (
             typeof(NEW.created_at) = 'text'
             AND (
                 NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]+00:00'
                 OR NEW.created_at GLOB
                     '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9].[0-9][0-9][0-9][0-9][0-9][0-9]+00:00'
             )
             AND julianday(NEW.created_at) IS NOT NULL
         )
         OR NEW.event_type NOT IN (
             'capture_started', 'full_download', 'pipeline_handoff'
         )
         OR NOT (
             (
                 NEW.event_type = 'capture_started'
                 AND NEW.actor_username IS NULL
                 AND NEW.downstream_task_id IS NULL
                 AND NEW.delivered_bytes IS NULL
             )
             OR (
                 NEW.event_type = 'full_download'
                 AND typeof(NEW.actor_username) = 'text'
                 AND length(trim(NEW.actor_username, char(
                     9,10,11,12,13,28,29,30,31,32,133,160,5760,
                     8192,8193,8194,8195,8196,8197,8198,8199,8200,8201,8202,
                     8232,8233,8239,8287,12288
                 ))) > 0
                 AND NEW.downstream_task_id IS NULL
                 AND typeof(NEW.delivered_bytes) = 'integer'
                 AND NEW.delivered_bytes >= 0
             )
             OR (
                 NEW.event_type = 'pipeline_handoff'
                 AND NEW.actor_username IS NULL
                 AND typeof(NEW.downstream_task_id) = 'text'
                 AND NEW.delivered_bytes IS NULL
             )
         )
    BEGIN
        SELECT RAISE(ABORT, 'invalid outcome event shape');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_capture_precedes_flow
    BEFORE INSERT ON artifact_outcome_events
    WHEN NEW.event_type IN ('full_download', 'pipeline_handoff')
         AND NOT EXISTS (
             SELECT 1
             FROM artifact_outcome_events AS capture
             WHERE capture.event_type = 'capture_started'
               AND capture.source_task_id = NEW.source_task_id
               AND capture.source_file_id = NEW.source_file_id
               AND capture.review_event_id = NEW.review_event_id
               AND capture.source_task_witness_json IS NEW.source_task_witness_json
               AND capture.source_file_witness_json IS NEW.source_file_witness_json
         )
    BEGIN
        SELECT RAISE(ABORT, 'outcome flow requires prior capture_started witness');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_download_bytes
    BEFORE INSERT ON artifact_outcome_events
    WHEN NEW.event_type = 'full_download'
         AND NOT EXISTS (
             SELECT 1 FROM files
             WHERE id = NEW.source_file_id
               AND size_bytes = NEW.delivered_bytes
         )
    BEGIN
        SELECT RAISE(ABORT, 'full_download bytes must equal authoritative file size');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_downstream_witness
    BEFORE INSERT ON artifact_outcome_events
    WHEN NEW.event_type = 'pipeline_handoff'
         AND NOT EXISTS (
             SELECT 1
             FROM tasks AS downstream
             WHERE downstream.id = NEW.downstream_task_id
               AND downstream.origin = 'user'
               AND EXISTS (
                   SELECT 1
                   FROM json_each(
                       CASE
                           WHEN json_valid(downstream.depends_on)
                            AND json_type(downstream.depends_on) = 'array'
                           THEN downstream.depends_on ELSE '[]'
                       END
                   ) AS upstream_ref
                   WHERE upstream_ref.type = 'text'
                     AND upstream_ref.value = NEW.source_task_id
               )
               AND EXISTS (
                   SELECT 1
                   FROM json_each(
                       CASE
                           WHEN json_valid(downstream.input_file_ids)
                            AND json_type(downstream.input_file_ids) = 'array'
                           THEN downstream.input_file_ids ELSE '[]'
                       END
                   ) AS input_ref
                   WHERE input_ref.type = 'text'
                     AND input_ref.value = NEW.source_file_id
               )
         )
    BEGIN
        SELECT RAISE(
            ABORT,
            'pipeline_handoff requires exact user downstream dependency and input file'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_no_update
    BEFORE UPDATE ON artifact_outcome_events
    BEGIN
        SELECT RAISE(ABORT, 'artifact_outcome_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_no_delete
    BEFORE DELETE ON artifact_outcome_events
    BEGIN
        SELECT RAISE(ABORT, 'artifact_outcome_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_no_conflicting_insert
    BEFORE INSERT ON artifact_outcome_events
    WHEN EXISTS (
        SELECT 1
        FROM artifact_outcome_events AS existing
        WHERE existing.id = NEW.id
           OR (NEW.rowid <> -1 AND existing.rowid = NEW.rowid)
           OR (
               NEW.event_type = 'capture_started'
               AND existing.event_type = 'capture_started'
               AND existing.source_file_id = NEW.source_file_id
           )
           OR (
               NEW.event_type = 'pipeline_handoff'
               AND existing.event_type = 'pipeline_handoff'
               AND existing.source_file_id = NEW.source_file_id
               AND existing.downstream_task_id = NEW.downstream_task_id
           )
    )
    BEGIN
        SELECT RAISE(ABORT, 'artifact_outcome_events is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_artifact_outcomes_positive_rowid
    AFTER INSERT ON artifact_outcome_events
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'artifact outcome internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_files_positive_rowid
    AFTER INSERT ON files
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'file internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_tasks_positive_rowid
    AFTER INSERT ON tasks
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'task internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_files_no_update
    BEFORE UPDATE ON files
    WHEN EXISTS (
        SELECT 1 FROM artifact_outcome_events
        WHERE source_file_id = OLD.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_files_no_delete
    BEFORE DELETE ON files
    WHEN EXISTS (
        SELECT 1 FROM artifact_outcome_events
        WHERE source_file_id = OLD.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_files_no_conflicting_insert
    BEFORE INSERT ON files
    WHEN EXISTS (
        SELECT 1
        FROM files AS existing
        WHERE (
            existing.id = NEW.id
            OR (NEW.rowid <> -1 AND existing.rowid = NEW.rowid)
        )
          AND EXISTS (
              SELECT 1 FROM artifact_outcome_events
              WHERE source_file_id = existing.id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_files_no_conflicting_update
    BEFORE UPDATE OF id, rowid ON files
    WHEN EXISTS (
        SELECT 1
        FROM files AS existing
        WHERE existing.rowid <> OLD.rowid
          AND (existing.id = NEW.id OR existing.rowid = NEW.rowid)
          AND EXISTS (
              SELECT 1 FROM artifact_outcome_events
              WHERE source_file_id = existing.id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_files_no_update
    BEFORE UPDATE ON files
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS review_task
        WHERE (
            review_task.status = 'waiting_review'
            OR EXISTS (
                SELECT 1 FROM task_human_decisions AS decision
                WHERE decision.task_id = review_task.id
            )
        )
          AND EXISTS (
              SELECT 1
              FROM json_each(
                  CASE
                      WHEN json_valid(review_task.output_file_ids)
                       AND json_type(review_task.output_file_ids) = 'array'
                      THEN review_task.output_file_ids ELSE '[]'
                  END
              ) AS output_ref
              WHERE output_ref.type = 'text'
                AND output_ref.value = OLD.id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'human review package file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_files_no_delete
    BEFORE DELETE ON files
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS review_task
        WHERE (
            review_task.status = 'waiting_review'
            OR EXISTS (
                SELECT 1 FROM task_human_decisions AS decision
                WHERE decision.task_id = review_task.id
            )
        )
          AND EXISTS (
              SELECT 1
              FROM json_each(
                  CASE
                      WHEN json_valid(review_task.output_file_ids)
                       AND json_type(review_task.output_file_ids) = 'array'
                      THEN review_task.output_file_ids ELSE '[]'
                  END
              ) AS output_ref
              WHERE output_ref.type = 'text'
                AND output_ref.value = OLD.id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'human review package file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_files_no_conflicting_insert
    BEFORE INSERT ON files
    WHEN EXISTS (
        SELECT 1
        FROM files AS existing
        WHERE (
            existing.id = NEW.id
            OR (NEW.rowid <> -1 AND existing.rowid = NEW.rowid)
        )
          AND EXISTS (
              SELECT 1
              FROM tasks AS review_task
              WHERE (
                  review_task.status = 'waiting_review'
                  OR EXISTS (
                      SELECT 1 FROM task_human_decisions AS decision
                      WHERE decision.task_id = review_task.id
                  )
              )
                AND EXISTS (
                    SELECT 1
                    FROM json_each(
                        CASE
                            WHEN json_valid(review_task.output_file_ids)
                             AND json_type(review_task.output_file_ids) = 'array'
                            THEN review_task.output_file_ids ELSE '[]'
                        END
                    ) AS output_ref
                    WHERE output_ref.type = 'text'
                      AND output_ref.value = existing.id
                )
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'human review package file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_files_no_conflicting_update
    BEFORE UPDATE OF id, rowid ON files
    WHEN EXISTS (
        SELECT 1
        FROM files AS existing
        WHERE existing.rowid <> OLD.rowid
          AND (existing.id = NEW.id OR existing.rowid = NEW.rowid)
          AND EXISTS (
              SELECT 1
              FROM tasks AS review_task
              WHERE (
                  review_task.status = 'waiting_review'
                  OR EXISTS (
                      SELECT 1 FROM task_human_decisions AS decision
                      WHERE decision.task_id = review_task.id
                  )
              )
                AND EXISTS (
                    SELECT 1
                    FROM json_each(
                        CASE
                            WHEN json_valid(review_task.output_file_ids)
                             AND json_type(review_task.output_file_ids) = 'array'
                            THEN review_task.output_file_ids ELSE '[]'
                        END
                    ) AS output_ref
                    WHERE output_ref.type = 'text'
                      AND output_ref.value = existing.id
                )
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'human review package file is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_files_no_late_insert
    BEFORE INSERT ON files
    WHEN NEW.kind = 'output'
         AND EXISTS (
             SELECT 1
             FROM tasks AS review_task
             WHERE review_task.id = NEW.task_id
               AND (
                   review_task.status = 'waiting_review'
                   OR EXISTS (
                       SELECT 1 FROM task_human_decisions AS decision
                       WHERE decision.task_id = review_task.id
                   )
               )
         )
    BEGIN
        SELECT RAISE(ABORT, 'cannot add output files to a sealed review package');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_files_no_late_move
    BEFORE UPDATE OF task_id, kind ON files
    WHEN NEW.kind = 'output'
         AND EXISTS (
             SELECT 1
             FROM tasks AS review_task
             WHERE review_task.id = NEW.task_id
               AND (
                   review_task.status = 'waiting_review'
                   OR EXISTS (
                       SELECT 1 FROM task_human_decisions AS decision
                       WHERE decision.task_id = review_task.id
                   )
               )
         )
    BEGIN
        SELECT RAISE(ABORT, 'cannot move output files into a sealed review package');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_tasks_provenance_immutable
    BEFORE UPDATE ON tasks
    WHEN (
        OLD.status = 'waiting_review'
        OR NEW.status = 'waiting_review'
        OR EXISTS (
            SELECT 1 FROM task_human_decisions AS decision
            WHERE decision.task_id = OLD.id
        )
    )
    AND (
        NEW.id IS NOT OLD.id
        OR NEW.rowid IS NOT OLD.rowid
        OR NEW.agent_id IS NOT OLD.agent_id
        OR NEW.agent_version IS NOT OLD.agent_version
        OR NEW.name IS NOT OLD.name
        OR NEW.created_by IS NOT OLD.created_by
        OR NEW.created_at IS NOT OLD.created_at
        OR NEW.started_at IS NOT OLD.started_at
        OR NEW.input_file_ids IS NOT OLD.input_file_ids
        OR NEW.output_file_ids IS NOT OLD.output_file_ids
        OR NEW.inputs_json IS NOT OLD.inputs_json
        OR NEW.metadata_json IS NOT OLD.metadata_json
        OR NEW.conversation_id IS NOT OLD.conversation_id
        OR NEW.origin IS NOT OLD.origin
        OR NEW.data_classification IS NOT OLD.data_classification
        OR NEW.depends_on IS NOT OLD.depends_on
        OR NEW.input_binding IS NOT OLD.input_binding
        OR NEW.created_by_username IS NOT OLD.created_by_username
        OR NEW.retry_of IS NOT OLD.retry_of
        OR (
            OLD.status = 'waiting_review'
            AND NEW.status IS NOT OLD.status
            AND NOT EXISTS (
                SELECT 1
                FROM task_human_decisions AS decision
                WHERE decision.task_id = OLD.id
                  AND (
                      (decision.action = 'approve' AND NEW.status = 'completed')
                      OR (decision.action = 'reject' AND NEW.status = 'failed')
                  )
                  AND NEW.updated_at IS decision.created_at
                  AND NEW.finished_at IS decision.created_at
                  AND NEW.error_message IS CASE decision.action
                      WHEN 'approve' THEN NULL
                      ELSE '人工拒绝（reviewer='
                           || decision.reviewer_display_name
                           || '；reason=' || decision.reason_code || '）'
                           || CASE WHEN decision.comment IS NULL THEN ''
                                   ELSE '：' || decision.comment END
                  END
            )
        )
        OR (
            (
                NEW.updated_at IS NOT OLD.updated_at
                OR NEW.finished_at IS NOT OLD.finished_at
                OR NEW.error_message IS NOT OLD.error_message
            )
            AND NOT (
                OLD.status IS NOT 'waiting_review'
                AND NEW.status = 'waiting_review'
                AND NEW.finished_at IS OLD.finished_at
                AND NEW.error_message IS OLD.error_message
            )
            AND NOT (
                OLD.status = 'waiting_review'
                AND EXISTS (
                    SELECT 1
                    FROM task_human_decisions AS decision
                    WHERE decision.task_id = OLD.id
                      AND (
                          (decision.action = 'approve'
                           AND NEW.status = 'completed')
                          OR (decision.action = 'reject'
                              AND NEW.status = 'failed')
                      )
                      AND NEW.updated_at IS decision.created_at
                      AND NEW.finished_at IS decision.created_at
                      AND NEW.error_message IS CASE decision.action
                          WHEN 'approve' THEN NULL
                          ELSE '人工拒绝（reviewer='
                               || decision.reviewer_display_name
                               || '；reason=' || decision.reason_code || '）'
                               || CASE WHEN decision.comment IS NULL THEN ''
                                       ELSE '：' || decision.comment END
                      END
                )
            )
        )
    )
    BEGIN
        SELECT RAISE(ABORT, 'sealed review task provenance is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_terminal_tasks_output_manifest_immutable
    BEFORE UPDATE OF output_file_ids ON tasks
    WHEN (OLD.status IN ('waiting_review', 'completed', 'failed', 'cancelled')
          OR NEW.status IN ('waiting_review', 'completed', 'failed', 'cancelled'))
         AND NEW.output_file_ids IS NOT OLD.output_file_ids
    BEGIN
        SELECT RAISE(ABORT, 'sealed review or terminal task output manifest is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_terminal_tasks_identity_status_immutable
    BEFORE UPDATE OF id, status, rowid ON tasks
    WHEN (
        OLD.status IN ('completed', 'failed', 'cancelled')
        AND (
            NEW.id IS NOT OLD.id
            OR NEW.rowid IS NOT OLD.rowid
            OR NEW.status IS NOT OLD.status
        )
    )
    OR (
        NEW.status IN ('completed', 'failed', 'cancelled')
        AND (NEW.id IS NOT OLD.id OR NEW.rowid IS NOT OLD.rowid)
    )
    BEGIN
        SELECT RAISE(ABORT, 'terminal task identity and status are immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_terminal_tasks_no_delete
    BEFORE DELETE ON tasks
    WHEN OLD.status IN ('completed', 'failed', 'cancelled')
    BEGIN
        SELECT RAISE(ABORT, 'terminal task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_terminal_tasks_no_conflicting_insert
    BEFORE INSERT ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS existing
        WHERE existing.status IN ('completed', 'failed', 'cancelled')
          AND (
              existing.id = NEW.id
              OR (NEW.rowid <> -1 AND existing.rowid = NEW.rowid)
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'terminal task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_terminal_tasks_no_conflicting_update
    BEFORE UPDATE OF id, rowid ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS existing
        WHERE existing.rowid <> OLD.rowid
          AND existing.status IN ('completed', 'failed', 'cancelled')
          AND (existing.id = NEW.id OR existing.rowid = NEW.rowid)
    )
    BEGIN
        SELECT RAISE(ABORT, 'terminal task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_tasks_identity_immutable
    BEFORE UPDATE OF id, rowid ON tasks
    WHEN (OLD.status = 'waiting_review' OR NEW.status = 'waiting_review')
         AND (NEW.id IS NOT OLD.id OR NEW.rowid IS NOT OLD.rowid)
    BEGIN
        SELECT RAISE(ABORT, 'sealed review task identity is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_tasks_no_delete
    BEFORE DELETE ON tasks
    WHEN OLD.status = 'waiting_review'
    BEGIN
        SELECT RAISE(ABORT, 'sealed review task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_tasks_no_conflicting_insert
    BEFORE INSERT ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS existing
        WHERE existing.status = 'waiting_review'
          AND (
              existing.id = NEW.id
              OR (NEW.rowid <> -1 AND existing.rowid = NEW.rowid)
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'sealed review task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_review_package_tasks_no_conflicting_update
    BEFORE UPDATE OF id, rowid ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS existing
        WHERE existing.rowid <> OLD.rowid
          AND existing.status = 'waiting_review'
          AND (existing.id = NEW.id OR existing.rowid = NEW.rowid)
    )
    BEGIN
        SELECT RAISE(ABORT, 'sealed review task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_waiting_review_exit_requires_human_witness
    BEFORE UPDATE OF status ON tasks
    WHEN OLD.status = 'waiting_review'
         AND NEW.status IS NOT OLD.status
         AND NOT EXISTS (
             SELECT 1
             FROM task_human_decisions AS decision
             JOIN task_events AS review_event
               ON review_event.task_id = decision.task_id
              AND review_event.event_type = CASE decision.action
                  WHEN 'approve' THEN 'review_approved'
                  WHEN 'reject' THEN 'review_rejected'
                  ELSE ''
              END
             JOIN task_review_event_witnesses AS event_witness
               ON event_witness.event_id = review_event.event_id
              AND event_witness.event_internal_id = review_event.id
              AND event_witness.task_id = review_event.task_id
              AND event_witness.agent_id IS review_event.agent_id
              AND event_witness.event_type = review_event.event_type
              AND event_witness.level = review_event.level
              AND event_witness.message = review_event.message
              AND event_witness.payload_json = review_event.payload_json
              AND event_witness.created_at = review_event.created_at
              AND event_witness.decision_id = decision.id
              AND event_witness.witness_kind = 'structured_v1'
             WHERE decision.task_id = OLD.id
               AND (
                   (decision.action = 'approve' AND NEW.status = 'completed')
                   OR (decision.action = 'reject' AND NEW.status = 'failed')
               )
               AND json_type(
                   CASE
                       WHEN json_valid(review_event.payload_json)
                       THEN review_event.payload_json ELSE '{}'
                   END,
                   '$.decision_id'
               ) = 'text'
               AND decision.id = json_extract(
                   CASE
                       WHEN json_valid(review_event.payload_json)
                       THEN review_event.payload_json ELSE '{}'
                   END,
                   '$.decision_id'
               )
         )
    BEGIN
        SELECT RAISE(
            ABORT,
            'waiting_review exit requires exact human decision and review event'
        );
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_tasks_preserve_source
    BEFORE UPDATE ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM artifact_outcome_events AS outcome
        WHERE outcome.source_task_id = OLD.id
          AND (
              NEW.id IS NOT OLD.id
              OR NEW.rowid IS NOT OLD.rowid
              OR NEW.origin IS NOT 'user'
              OR NEW.status IS NOT 'completed'
              OR NEW.output_file_ids IS NOT OLD.output_file_ids
              OR outcome.source_task_witness_json IS NOT json_object(
                  'agent_id', NEW.agent_id,
                  'agent_version', NEW.agent_version,
                  'conversation_id', NEW.conversation_id,
                  'created_at', NEW.created_at,
                  'created_by', NEW.created_by,
                  'created_by_username', NEW.created_by_username,
                  'data_classification', NEW.data_classification,
                  'depends_on', NEW.depends_on,
                  'error_message', NEW.error_message,
                  'finished_at', NEW.finished_at,
                  'id', NEW.id,
                  'input_binding', NEW.input_binding,
                  'input_file_ids', NEW.input_file_ids,
                  'inputs_json', NEW.inputs_json,
                  'metadata_json', NEW.metadata_json,
                  'name', NEW.name,
                  'origin', NEW.origin,
                  'output_file_ids', NEW.output_file_ids,
                  'retry_of', NEW.retry_of,
                  'rowid', NEW.rowid,
                  'started_at', NEW.started_at,
                  'status', NEW.status,
                  'updated_at', NEW.updated_at
              )
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed source task provenance is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_tasks_preserve_handoff
    BEFORE UPDATE ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM artifact_outcome_events AS outcome
        WHERE outcome.event_type = 'pipeline_handoff'
          AND outcome.downstream_task_id = OLD.id
          AND (
              NEW.id IS NOT OLD.id
              OR NEW.rowid IS NOT OLD.rowid
              OR NEW.origin IS NOT 'user'
              OR NOT EXISTS (
                  SELECT 1
                  FROM json_each(
                      CASE
                          WHEN json_valid(NEW.depends_on)
                           AND json_type(NEW.depends_on) = 'array'
                          THEN NEW.depends_on ELSE '[]'
                      END
                  ) AS upstream_ref
                  WHERE upstream_ref.type = 'text'
                    AND upstream_ref.value = outcome.source_task_id
              )
              OR NOT EXISTS (
                  SELECT 1
                  FROM json_each(
                      CASE
                          WHEN json_valid(NEW.input_file_ids)
                           AND json_type(NEW.input_file_ids) = 'array'
                          THEN NEW.input_file_ids ELSE '[]'
                      END
                  ) AS input_ref
                  WHERE input_ref.type = 'text'
                    AND input_ref.value = outcome.source_file_id
              )
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed downstream handoff is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_tasks_no_delete
    BEFORE DELETE ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM artifact_outcome_events AS outcome
        WHERE outcome.source_task_id = OLD.id
           OR outcome.downstream_task_id = OLD.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_tasks_no_conflicting_insert
    BEFORE INSERT ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS existing
        WHERE (
            existing.id = NEW.id
            OR (NEW.rowid <> -1 AND existing.rowid = NEW.rowid)
        )
          AND EXISTS (
              SELECT 1
              FROM artifact_outcome_events AS outcome
              WHERE outcome.source_task_id = existing.id
                 OR outcome.downstream_task_id = existing.id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed task is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_witnessed_artifact_tasks_no_conflicting_update
    BEFORE UPDATE OF id, rowid ON tasks
    WHEN EXISTS (
        SELECT 1
        FROM tasks AS existing
        WHERE existing.rowid <> OLD.rowid
          AND (existing.id = NEW.id OR existing.rowid = NEW.rowid)
          AND EXISTS (
              SELECT 1
              FROM artifact_outcome_events AS outcome
              WHERE outcome.source_task_id = existing.id
                 OR outcome.downstream_task_id = existing.id
          )
    )
    BEGIN
        SELECT RAISE(ABORT, 'outcome-witnessed task is immutable');
    END
    """,
)

_OUTCOME_MANAGED_INDEXES = (
    "idx_artifact_outcomes_source_created",
    "idx_artifact_outcomes_source_task_created",
    "idx_artifact_outcomes_downstream_created",
    "idx_artifact_outcomes_one_capture",
    "idx_artifact_outcomes_one_handoff",
)

_OUTCOME_SHARED_PARENT_TRIGGERS = (
    "trg_task_events_no_update",
    "trg_task_events_no_delete",
    "trg_task_events_no_conflicting_insert",
    "trg_task_events_positive_rowid",
)

_OUTCOME_REVIEW_SEAL_TRIGGERS = (
    "trg_files_positive_rowid",
    "trg_tasks_positive_rowid",
    "trg_review_package_files_no_update",
    "trg_review_package_files_no_delete",
    "trg_review_package_files_no_conflicting_insert",
    "trg_review_package_files_no_conflicting_update",
    "trg_review_package_files_no_late_insert",
    "trg_review_package_files_no_late_move",
    "trg_review_package_tasks_provenance_immutable",
    "trg_terminal_tasks_output_manifest_immutable",
    "trg_terminal_tasks_identity_status_immutable",
    "trg_terminal_tasks_no_delete",
    "trg_terminal_tasks_no_conflicting_insert",
    "trg_terminal_tasks_no_conflicting_update",
    "trg_review_package_tasks_identity_immutable",
    "trg_review_package_tasks_no_delete",
    "trg_review_package_tasks_no_conflicting_insert",
    "trg_review_package_tasks_no_conflicting_update",
    "trg_waiting_review_exit_requires_human_witness",
)

# Outcome-exclusive objects are residue only when the outcome table generation
# itself exists.  The task-event append-only guards predate ADR-0036 (P2.1), so
# they are required witnesses but must never make a legitimate legacy database
# look like a half-deleted outcome schema.
_OUTCOME_MANAGED_TRIGGERS = (
    "trg_artifact_outcomes_source_witness",
    "trg_artifact_outcomes_validate_shape",
    "trg_artifact_outcomes_capture_precedes_flow",
    "trg_artifact_outcomes_download_bytes",
    "trg_artifact_outcomes_downstream_witness",
    "trg_artifact_outcomes_no_update",
    "trg_artifact_outcomes_no_delete",
    "trg_artifact_outcomes_no_conflicting_insert",
    "trg_artifact_outcomes_positive_rowid",
    "trg_witnessed_artifact_files_no_update",
    "trg_witnessed_artifact_files_no_delete",
    "trg_witnessed_artifact_files_no_conflicting_insert",
    "trg_witnessed_artifact_files_no_conflicting_update",
    *_OUTCOME_REVIEW_SEAL_TRIGGERS,
    "trg_witnessed_artifact_tasks_preserve_source",
    "trg_witnessed_artifact_tasks_preserve_handoff",
    "trg_witnessed_artifact_tasks_no_delete",
    "trg_witnessed_artifact_tasks_no_conflicting_insert",
    "trg_witnessed_artifact_tasks_no_conflicting_update",
)

_OUTCOME_REQUIRED_TRIGGERS = (
    *_OUTCOME_SHARED_PARENT_TRIGGERS,
    *_OUTCOME_MANAGED_TRIGGERS,
)

_INDEX_DDL = (
    "CREATE INDEX IF NOT EXISTS idx_task_events_task_id ON task_events(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_tool_runs_task_id ON tool_runs(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_calls_task_id ON model_calls(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_model_calls_conversation_id ON model_calls(conversation_id)",
    "CREATE INDEX IF NOT EXISTS idx_samples_task_id ON samples(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_feedback_task_id ON feedback(task_id)",
    "CREATE INDEX IF NOT EXISTS idx_conversation_messages_conversation_id "
    "ON conversation_messages(conversation_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_messages_message_id "
    "ON conversation_messages(message_id)",
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_messages_public_id_required
    BEFORE INSERT ON conversation_messages
    WHEN NEW.message_id IS NULL
         OR length(NEW.message_id) <> 36
         OR substr(NEW.message_id, 1, 4) <> 'msg_'
         OR substr(NEW.message_id, 5) GLOB '*[^0-9a-f]*'
    BEGIN
        SELECT RAISE(ABORT, 'conversation message public id is required');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_messages_no_update
    BEFORE UPDATE ON conversation_messages
    BEGIN
        SELECT RAISE(ABORT, 'conversation_messages is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_messages_no_delete
    BEFORE DELETE ON conversation_messages
    BEGIN
        SELECT RAISE(ABORT, 'conversation_messages is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_messages_no_conflicting_insert
    BEFORE INSERT ON conversation_messages
    WHEN EXISTS (
        SELECT 1 FROM conversation_messages
        WHERE message_id = NEW.message_id
           OR (NEW.id <> -1 AND id = NEW.id)
    )
    BEGIN
        SELECT RAISE(ABORT, 'conversation_messages is append-only');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_messages_positive_internal_id
    AFTER INSERT ON conversation_messages
    WHEN NEW.id <= 0
    BEGIN
        SELECT RAISE(ABORT, 'conversation message internal id must be positive');
    END
    """,
    "CREATE INDEX IF NOT EXISTS idx_conversation_questions_conversation_id "
    "ON conversation_questions(conversation_id, created_at, id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_questions_prompt_message_id "
    "ON conversation_questions(prompt_message_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_questions_one_unresolved "
    "ON conversation_questions(conversation_id, asked_to_username) "
    "WHERE closed_reason IS NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_questions_answer_message_id "
    "ON conversation_questions(answer_message_id) WHERE answer_message_id IS NOT NULL",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_conversation_questions_response_message_id "
    "ON conversation_questions(response_message_id) WHERE response_message_id IS NOT NULL",
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_public_id_required
    BEFORE INSERT ON conversation_questions
    WHEN NEW.id IS NULL
         OR length(NEW.id) <> 34
         OR substr(NEW.id, 1, 2) <> 'q_'
         OR substr(NEW.id, 3) GLOB '*[^0-9a-f]*'
    BEGIN
        SELECT RAISE(ABORT, 'conversation question public id is required');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_timestamp_canonical
    BEFORE INSERT ON conversation_questions
    WHEN length(NEW.created_at) <> 32
         OR substr(NEW.created_at, 5, 1) <> '-'
         OR substr(NEW.created_at, 8, 1) <> '-'
         OR substr(NEW.created_at, 11, 1) <> 'T'
         OR substr(NEW.created_at, 14, 1) <> ':'
         OR substr(NEW.created_at, 17, 1) <> ':'
         OR substr(NEW.created_at, 20, 1) <> '.'
         OR substr(NEW.created_at, 27, 6) <> '+00:00'
         OR (
             substr(NEW.created_at, 1, 4)
             || substr(NEW.created_at, 6, 2)
             || substr(NEW.created_at, 9, 2)
             || substr(NEW.created_at, 12, 2)
             || substr(NEW.created_at, 15, 2)
             || substr(NEW.created_at, 18, 2)
             || substr(NEW.created_at, 21, 6)
         ) GLOB '*[^0-9]*'
         OR CAST(substr(NEW.created_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
         OR CAST(substr(NEW.created_at, 6, 2) AS INTEGER) NOT BETWEEN 1 AND 12
         OR CAST(substr(NEW.created_at, 9, 2) AS INTEGER) NOT BETWEEN 1 AND
             CASE CAST(substr(NEW.created_at, 6, 2) AS INTEGER)
                 WHEN 2 THEN CASE
                     WHEN CAST(substr(NEW.created_at, 1, 4) AS INTEGER) % 400 = 0
                          OR (
                              CAST(substr(NEW.created_at, 1, 4) AS INTEGER) % 4 = 0
                              AND CAST(substr(NEW.created_at, 1, 4) AS INTEGER) % 100 <> 0
                          )
                     THEN 29 ELSE 28 END
                 WHEN 4 THEN 30
                 WHEN 6 THEN 30
                 WHEN 9 THEN 30
                 WHEN 11 THEN 30
                 ELSE 31
             END
         OR CAST(substr(NEW.created_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
         OR CAST(substr(NEW.created_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
         OR CAST(substr(NEW.created_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
         OR strftime('%Y-%m-%dT%H:%M:%S', NEW.created_at)
             IS NOT substr(NEW.created_at, 1, 19)
         OR length(NEW.expires_at) <> 32
         OR substr(NEW.expires_at, 5, 1) <> '-'
         OR substr(NEW.expires_at, 8, 1) <> '-'
         OR substr(NEW.expires_at, 11, 1) <> 'T'
         OR substr(NEW.expires_at, 14, 1) <> ':'
         OR substr(NEW.expires_at, 17, 1) <> ':'
         OR substr(NEW.expires_at, 20, 1) <> '.'
         OR substr(NEW.expires_at, 27, 6) <> '+00:00'
         OR (
             substr(NEW.expires_at, 1, 4)
             || substr(NEW.expires_at, 6, 2)
             || substr(NEW.expires_at, 9, 2)
             || substr(NEW.expires_at, 12, 2)
             || substr(NEW.expires_at, 15, 2)
             || substr(NEW.expires_at, 18, 2)
             || substr(NEW.expires_at, 21, 6)
         ) GLOB '*[^0-9]*'
         OR CAST(substr(NEW.expires_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
         OR CAST(substr(NEW.expires_at, 6, 2) AS INTEGER) NOT BETWEEN 1 AND 12
         OR CAST(substr(NEW.expires_at, 9, 2) AS INTEGER) NOT BETWEEN 1 AND
             CASE CAST(substr(NEW.expires_at, 6, 2) AS INTEGER)
                 WHEN 2 THEN CASE
                     WHEN CAST(substr(NEW.expires_at, 1, 4) AS INTEGER) % 400 = 0
                          OR (
                              CAST(substr(NEW.expires_at, 1, 4) AS INTEGER) % 4 = 0
                              AND CAST(substr(NEW.expires_at, 1, 4) AS INTEGER) % 100 <> 0
                          )
                     THEN 29 ELSE 28 END
                 WHEN 4 THEN 30
                 WHEN 6 THEN 30
                 WHEN 9 THEN 30
                 WHEN 11 THEN 30
                 ELSE 31
             END
         OR CAST(substr(NEW.expires_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
         OR CAST(substr(NEW.expires_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
         OR CAST(substr(NEW.expires_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
         OR strftime('%Y-%m-%dT%H:%M:%S', NEW.expires_at)
             IS NOT substr(NEW.expires_at, 1, 19)
    BEGIN
        SELECT RAISE(ABORT, 'question timestamp must be canonical RFC3339 UTC');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_ttl_24h
    BEFORE INSERT ON conversation_questions
    WHEN strftime('%s', NEW.created_at) IS NULL
         OR strftime('%s', NEW.expires_at) IS NULL
         OR CAST(strftime('%s', NEW.expires_at) AS INTEGER)
             - CAST(strftime('%s', NEW.created_at) AS INTEGER) <> 86400
         OR substr(NEW.expires_at, 21, 6) <> substr(NEW.created_at, 21, 6)
    BEGIN
        SELECT RAISE(ABORT, 'question TTL must be exactly 24 hours');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_owner_exact
    BEFORE INSERT ON conversation_questions
    WHEN NOT EXISTS (
        SELECT 1 FROM conversations
        WHERE id = NEW.conversation_id
          AND created_by_username = NEW.asked_to_username
    )
    BEGIN
        SELECT RAISE(ABORT, 'question owner must match conversation owner');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_initially_unresolved
    BEFORE INSERT ON conversation_questions
    WHEN NEW.closed_reason IS NOT NULL
         OR NEW.closed_at IS NOT NULL
         OR NEW.submission_id IS NOT NULL
         OR NEW.answer_json IS NOT NULL
         OR NEW.answered_by_username IS NOT NULL
         OR NEW.answer_message_id IS NOT NULL
         OR NEW.response_message_id IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'question must start unresolved');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_prompt_message
    BEFORE INSERT ON conversation_questions
    WHEN NOT EXISTS (
        SELECT 1 FROM conversation_messages
        WHERE message_id = NEW.prompt_message_id
          AND conversation_id = NEW.conversation_id
          AND role = 'assistant'
    )
    BEGIN
        SELECT RAISE(ABORT, 'question prompt message mismatch');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_spec_immutable
    BEFORE UPDATE ON conversation_questions
    WHEN NEW.id IS NOT OLD.id
         OR NEW.conversation_id IS NOT OLD.conversation_id
         OR NEW.prompt_message_id IS NOT OLD.prompt_message_id
         OR NEW.asked_to_username IS NOT OLD.asked_to_username
         OR NEW.revision IS NOT OLD.revision
         OR NEW.kind IS NOT OLD.kind
         OR NEW.prompt IS NOT OLD.prompt
         OR NEW.description IS NOT OLD.description
         OR NEW.options_json IS NOT OLD.options_json
         OR NEW.created_at IS NOT OLD.created_at
         OR NEW.expires_at IS NOT OLD.expires_at
    BEGIN
        SELECT RAISE(ABORT, 'question spec is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_rowid_immutable
    BEFORE UPDATE ON conversation_questions
    WHEN NEW.rowid IS NOT OLD.rowid
    BEGIN
        SELECT RAISE(ABORT, 'question row identity is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_positive_rowid
    AFTER INSERT ON conversation_questions
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'question internal rowid must be positive');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_resolution_once
    BEFORE UPDATE ON conversation_questions
    WHEN OLD.closed_reason IS NOT NULL
    BEGIN
        SELECT RAISE(ABORT, 'question resolution is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_answer_messages
    BEFORE UPDATE ON conversation_questions
    WHEN NEW.closed_reason = 'answered'
         AND NOT EXISTS (
             SELECT 1
             FROM conversation_messages AS prompt_message
             JOIN conversation_messages AS answer_message
               ON answer_message.message_id = NEW.answer_message_id
             JOIN conversation_messages AS response_message
               ON response_message.message_id = NEW.response_message_id
             WHERE prompt_message.message_id = NEW.prompt_message_id
               AND prompt_message.conversation_id = NEW.conversation_id
               AND prompt_message.role = 'assistant'
               AND answer_message.conversation_id = NEW.conversation_id
               AND answer_message.role = 'user'
               AND response_message.conversation_id = NEW.conversation_id
               AND response_message.role = 'assistant'
               AND prompt_message.id < answer_message.id
               AND answer_message.id < response_message.id
         )
    BEGIN
        SELECT RAISE(ABORT, 'question answer message mismatch');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_answer_before_expiry
    BEFORE UPDATE ON conversation_questions
    WHEN NEW.closed_reason = 'answered'
         AND (
             NEW.closed_at IS NULL
             OR NEW.closed_at < NEW.created_at
             OR NEW.closed_at >= NEW.expires_at
         )
    BEGIN
        SELECT RAISE(ABORT, 'question answer is expired');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_resolution_timestamp
    BEFORE UPDATE ON conversation_questions
    WHEN NEW.closed_reason IS NOT NULL
         AND (
             NEW.closed_at IS NULL
             OR length(NEW.closed_at) <> 32
             OR substr(NEW.closed_at, 5, 1) <> '-'
             OR substr(NEW.closed_at, 8, 1) <> '-'
             OR substr(NEW.closed_at, 11, 1) <> 'T'
             OR substr(NEW.closed_at, 14, 1) <> ':'
             OR substr(NEW.closed_at, 17, 1) <> ':'
             OR substr(NEW.closed_at, 20, 1) <> '.'
             OR substr(NEW.closed_at, 27, 6) <> '+00:00'
             OR (
                 substr(NEW.closed_at, 1, 4)
                 || substr(NEW.closed_at, 6, 2)
                 || substr(NEW.closed_at, 9, 2)
                 || substr(NEW.closed_at, 12, 2)
                 || substr(NEW.closed_at, 15, 2)
                 || substr(NEW.closed_at, 18, 2)
                 || substr(NEW.closed_at, 21, 6)
             ) GLOB '*[^0-9]*'
             OR CAST(substr(NEW.closed_at, 1, 4) AS INTEGER) NOT BETWEEN 1 AND 9999
             OR CAST(substr(NEW.closed_at, 6, 2) AS INTEGER) NOT BETWEEN 1 AND 12
             OR CAST(substr(NEW.closed_at, 9, 2) AS INTEGER) NOT BETWEEN 1 AND
                 CASE CAST(substr(NEW.closed_at, 6, 2) AS INTEGER)
                     WHEN 2 THEN CASE
                         WHEN CAST(substr(NEW.closed_at, 1, 4) AS INTEGER) % 400 = 0
                              OR (
                                  CAST(substr(NEW.closed_at, 1, 4) AS INTEGER) % 4 = 0
                                  AND CAST(substr(NEW.closed_at, 1, 4) AS INTEGER) % 100 <> 0
                              )
                         THEN 29 ELSE 28 END
                     WHEN 4 THEN 30
                     WHEN 6 THEN 30
                     WHEN 9 THEN 30
                     WHEN 11 THEN 30
                     ELSE 31
                 END
             OR CAST(substr(NEW.closed_at, 12, 2) AS INTEGER) NOT BETWEEN 0 AND 23
             OR CAST(substr(NEW.closed_at, 15, 2) AS INTEGER) NOT BETWEEN 0 AND 59
             OR CAST(substr(NEW.closed_at, 18, 2) AS INTEGER) NOT BETWEEN 0 AND 59
             OR strftime('%Y-%m-%dT%H:%M:%S', NEW.closed_at)
                 IS NOT substr(NEW.closed_at, 1, 19)
             OR NEW.closed_at < NEW.created_at
             OR (NEW.closed_reason = 'expired' AND NEW.closed_at <> NEW.expires_at)
             OR (NEW.closed_reason = 'superseded' AND NEW.closed_at >= NEW.expires_at)
         )
    BEGIN
        SELECT RAISE(ABORT, 'question resolution timestamp is invalid');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_no_delete
    BEFORE DELETE ON conversation_questions
    BEGIN
        SELECT RAISE(ABORT, 'conversation_questions is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_no_conflicting_insert
    BEFORE INSERT ON conversation_questions
    WHEN EXISTS (
        SELECT 1 FROM conversation_questions WHERE id = NEW.id
    )
    BEGIN
        SELECT RAISE(ABORT, 'conversation_questions is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversation_questions_no_conflicting_insert_v2
    BEFORE INSERT ON conversation_questions
    WHEN EXISTS (
        SELECT 1 FROM conversation_questions
        WHERE id = NEW.id
           OR prompt_message_id = NEW.prompt_message_id
           OR (NEW.rowid <> -1 AND rowid = NEW.rowid)
           OR (
               NEW.closed_reason IS NULL
               AND closed_reason IS NULL
               AND conversation_id = NEW.conversation_id
               AND asked_to_username = NEW.asked_to_username
           )
    )
    BEGIN
        SELECT RAISE(ABORT, 'conversation_questions is immutable');
    END
    """,
    "CREATE INDEX IF NOT EXISTS idx_conversations_created_by_username "
    "ON conversations(created_by_username)",
    # Fresh DDL has NOT NULL; the trigger is the equivalent forward-write gate
    # for supported pre-P2.3 tables whose TEXT PRIMARY KEY metadata remains
    # nullable after ALTER migrations.
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_id_required
    BEFORE INSERT ON conversations
    WHEN NEW.id IS NULL OR typeof(NEW.id) <> 'text' OR length(NEW.id) = 0
    BEGIN
        SELECT RAISE(ABORT, 'conversation id is required');
    END
    """,
    # P2.3：owner 一旦非 NULL 即不可变；NULL→非 NULL 留给未来显式 CAS-on-NULL
    # 认领 API（本切片不提供），非 NULL→另一值/NULL 均由 SQLite 纵深拒绝。
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_owner_immutable
    BEFORE UPDATE OF created_by_username ON conversations
    WHEN OLD.created_by_username IS NOT NULL
         AND NEW.created_by_username IS NOT OLD.created_by_username
    BEGIN
        SELECT RAISE(ABORT, 'conversation owner is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_no_conflicting_insert
    BEFORE INSERT ON conversations
    WHEN EXISTS (SELECT 1 FROM conversations WHERE id = NEW.id)
    BEGIN
        SELECT RAISE(ABORT, 'conversation owner is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_identity_immutable
    BEFORE UPDATE ON conversations
    WHEN NEW.id IS NOT OLD.id OR NEW.rowid IS NOT OLD.rowid
    BEGIN
        SELECT RAISE(ABORT, 'conversation identity is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_no_delete
    BEFORE DELETE ON conversations
    BEGIN
        SELECT RAISE(ABORT, 'conversation is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_no_conflicting_insert_v2
    BEFORE INSERT ON conversations
    WHEN EXISTS (
        SELECT 1 FROM conversations
        WHERE id = NEW.id OR (NEW.rowid <> -1 AND rowid = NEW.rowid)
    )
    BEGIN
        SELECT RAISE(ABORT, 'conversation identity is immutable');
    END
    """,
    """
    CREATE TRIGGER IF NOT EXISTS trg_conversations_positive_rowid
    AFTER INSERT ON conversations
    WHEN NEW.rowid <= 0
    BEGIN
        SELECT RAISE(ABORT, 'conversation internal rowid must be positive');
    END
    """,
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

# P2.3 managed schema objects are authoritative, not merely name-presence
# probes.  SQLite's IF NOT EXISTS preserves a same-name stale/no-op trigger or
# wrong-column index indefinitely, so init_db refreshes these exact objects under
# its migration write lock before replaying _INDEX_DDL.  An index recreation that
# encounters contradictory persisted rows fails startup rather than weakening a
# uniqueness/predicate contract.
_P23_MANAGED_INDEXES = (
    "idx_conversation_messages_conversation_id",
    "idx_conversation_messages_message_id",
    "idx_conversation_questions_conversation_id",
    "idx_conversation_questions_prompt_message_id",
    "idx_conversation_questions_one_unresolved",
    "idx_conversation_questions_answer_message_id",
    "idx_conversation_questions_response_message_id",
    "idx_conversations_created_by_username",
)

_P23_MANAGED_TRIGGERS = (
    "trg_conversation_messages_public_id_required",
    "trg_conversation_messages_no_update",
    "trg_conversation_messages_no_delete",
    "trg_conversation_messages_no_conflicting_insert",
    "trg_conversation_messages_positive_internal_id",
    "trg_conversation_questions_public_id_required",
    "trg_conversation_questions_timestamp_canonical",
    "trg_conversation_questions_ttl_24h",
    "trg_conversation_questions_owner_exact",
    "trg_conversation_questions_initially_unresolved",
    "trg_conversation_questions_prompt_message",
    "trg_conversation_questions_spec_immutable",
    "trg_conversation_questions_rowid_immutable",
    "trg_conversation_questions_positive_rowid",
    "trg_conversation_questions_resolution_once",
    "trg_conversation_questions_answer_messages",
    "trg_conversation_questions_answer_before_expiry",
    "trg_conversation_questions_resolution_timestamp",
    "trg_conversation_questions_no_delete",
    "trg_conversation_questions_no_conflicting_insert",
    "trg_conversation_questions_no_conflicting_insert_v2",
    "trg_conversations_id_required",
    "trg_conversations_owner_immutable",
    "trg_conversations_no_conflicting_insert",
    "trg_conversations_identity_immutable",
    "trg_conversations_no_delete",
    "trg_conversations_no_conflicting_insert_v2",
    "trg_conversations_positive_rowid",
)


# P0-B2（Codex 命中即审 P1-1）：每进程已校验过的 DB 路径 memo，避免 get_conn 每次
# 重复校验（尤其 Windows GetDriveType 系统调用）。
_VALIDATED_DB_PATHS: set[str] = set()


def _p23_sql_without_comments(sql: str) -> str | None:
    """Strip SQLite comments while preserving quoted identifiers/literals."""
    result: list[str] = []
    quote: str | None = None
    index = 0
    while index < len(sql):
        char = sql[index]
        if quote is not None:
            result.append(char)
            if char == quote:
                if index + 1 < len(sql) and sql[index + 1] == quote:
                    result.append(sql[index + 1])
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            result.append(char)
            index += 1
            continue
        if char == "[":
            quote = "]"
            result.append(char)
            index += 1
            continue
        if sql.startswith("--", index):
            newline = sql.find("\n", index + 2)
            if newline < 0:
                return "".join(result)
            result.append(" ")
            index = newline + 1
            continue
        if sql.startswith("/*", index):
            end = sql.find("*/", index + 2)
            if end < 0:
                return None
            result.append(" ")
            index = end + 2
            continue
        result.append(char)
        index += 1
    return None if quote is not None else "".join(result)


def _p23_table_definitions(sql: str) -> tuple[str, ...] | None:
    """Split CREATE TABLE's top-level definitions without parsing expressions."""
    clean = _p23_sql_without_comments(sql)
    if clean is None:
        return None
    definitions: list[str] = []
    quote: str | None = None
    depth = 0
    content_start: int | None = None
    definition_start: int | None = None
    index = 0
    while index < len(clean):
        char = clean[index]
        if quote is not None:
            if char == quote:
                if index + 1 < len(clean) and clean[index + 1] == quote:
                    index += 2
                    continue
                quote = None
            index += 1
            continue
        if char in ("'", '"', "`"):
            quote = char
            index += 1
            continue
        if char == "[":
            quote = "]"
            index += 1
            continue
        if content_start is None:
            if char == "(":
                content_start = index + 1
                definition_start = content_start
            index += 1
            continue
        if char == "(":
            depth += 1
        elif char == ")":
            if depth == 0:
                assert definition_start is not None
                tail = " ".join(clean[definition_start:index].split())
                if tail:
                    definitions.append(tail)
                # Canonical identity tables are ordinary rowid tables.  STRICT
                # and WITHOUT ROWID change type/identity behavior and cannot be
                # ignored merely because their tokens follow the closing paren.
                suffix = clean[index + 1 :].strip()
                if suffix.endswith(";"):
                    suffix = suffix[:-1].strip()
                if suffix:
                    return None
                return tuple(definitions)
            depth -= 1
        elif char == "," and depth == 0:
            assert definition_start is not None
            definition = " ".join(clean[definition_start:index].split())
            if not definition:
                return None
            definitions.append(definition)
            definition_start = index + 1
        index += 1
    return None


def _p23_definition_head(definition: str) -> tuple[str, str] | None:
    """Return a top-level definition's first SQLite identifier and remainder."""
    stripped = definition.lstrip()
    if not stripped:
        return None
    opener = stripped[0]
    if opener in ('"', "`", "["):
        closer = "]" if opener == "[" else opener
        end = stripped.find(closer, 1)
        if end < 0:
            return None
        name = stripped[1:end]
        remainder = stripped[end + 1 :].strip()
        return name, remainder
    end = 0
    while end < len(stripped) and (
        stripped[end].isalnum() or stripped[end] in ("_", "$")
    ):
        end += 1
    if end == 0:
        return None
    return stripped[:end], stripped[end:].strip()


def _p23_quoted_identifier(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _p23_required_table_shape_is_canonical(
    conn: sqlite3.Connection,
    *,
    table: str,
    allowed_definition_variants: tuple[
        tuple[tuple[str, str], ...], ...
    ],
    required_xinfo: dict[str, tuple[tuple[object, ...], ...]],
) -> bool:
    """Validate the explicit fresh/legacy column contract for a runtime table.

    Column order and clauses must match the fresh DDL or one repository-owned
    legacy ALTER history exactly.  Unknown columns and constraints fail closed
    because omitted-column inserts still evaluate their NOT NULL, default,
    generated, CHECK, and FK behavior.
    """
    table_row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone()
    if table_row is None or not isinstance(table_row[0], str):
        return False
    definitions = _p23_table_definitions(table_row[0])
    if definitions is None:
        return False

    actual_definitions: list[tuple[str, str]] = []
    for definition in definitions:
        head = _p23_definition_head(definition)
        if head is None:
            return False
        actual_definitions.append(
            (
                head[0].casefold(),
                " ".join(head[1].split()).casefold(),
            )
        )
    normalized_variants = {
        tuple(
            (name.casefold(), " ".join(clause.split()).casefold())
            for name, clause in variant
        )
        for variant in allowed_definition_variants
    }
    if tuple(actual_definitions) not in normalized_variants:
        return False

    quoted_table = _p23_quoted_identifier(table)
    required_names = {name.casefold() for name in required_xinfo}
    actual_xinfo = {
        str(row[1]): tuple(row[2:])
        for row in conn.execute(f"PRAGMA table_xinfo({quoted_table})")
    }
    if any(
        actual_xinfo.get(name) not in allowed
        for name, allowed in required_xinfo.items()
    ):
        return False
    if any(
        str(row[3]).casefold() in required_names
        for row in conn.execute(f"PRAGMA foreign_key_list({quoted_table})")
    ):
        return False

    for index_row in conn.execute(f"PRAGMA index_list({quoted_table})"):
        if int(index_row[2]) != 1:
            continue
        index_name = str(index_row[1])
        quoted_index = _p23_quoted_identifier(index_name)
        index_xinfo = list(conn.execute(f"PRAGMA index_xinfo({quoted_index})"))
        key_columns = [
            str(row[2])
            for row in index_xinfo
            if int(row[5]) == 1 and row[2] is not None
        ]
        index_sql_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'index' AND name = ?",
            (index_name,),
        ).fetchone()
        index_sql = (
            index_sql_row[0]
            if index_sql_row is not None and isinstance(index_sql_row[0], str)
            else None
        )
        if table == "conversations" and (
            index_name.startswith("sqlite_autoindex_conversations_")
            and key_columns == ["id"]
            and str(index_row[3]) == "pk"
            and int(index_row[4]) == 0
            and index_sql is None
        ):
            continue
        if table == "conversation_messages" and (
            index_name == "idx_conversation_messages_message_id"
            and key_columns == ["message_id"]
            and str(index_row[3]) == "c"
            and int(index_row[4]) == 0
        ):
            continue
        if table == "conversation_messages" and (
            index_name.startswith("sqlite_autoindex_conversation_messages_")
            and key_columns == ["message_id"]
            and str(index_row[3]) == "u"
            and int(index_row[4]) == 0
            and index_sql is None
        ):
            continue
        # Any other UNIQUE/expression/partial index changes the set of writable
        # facts, even when it mentions only a future additive column.  Later
        # phases must explicitly promote such an index into the managed set.
        return False
    return True


def _p23_identity_table_shape_witnesses(
    conn: sqlite3.Connection,
) -> dict[str, bool]:
    """Shared startup/readiness contract for the two ordered conversation tables."""
    conversation_fresh = (
        ("id", "TEXT PRIMARY KEY NOT NULL"),
        ("agent_id", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL"),
        ("created_by", "TEXT NOT NULL"),
        ("created_by_username", "TEXT"),
        ("recommendation_json", "TEXT"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
    )
    conversation_legacy = (
        ("id", "TEXT PRIMARY KEY"),
        ("agent_id", "TEXT NOT NULL"),
        ("status", "TEXT NOT NULL"),
        ("created_by", "TEXT NOT NULL"),
        ("recommendation_json", "TEXT"),
        ("created_at", "TEXT NOT NULL"),
        ("updated_at", "TEXT NOT NULL"),
        ("created_by_username", "TEXT"),
    )
    conversation_xinfo = {
        "id": (("TEXT", 0, None, 1, 0), ("TEXT", 1, None, 1, 0)),
        "agent_id": (("TEXT", 1, None, 0, 0),),
        "status": (("TEXT", 1, None, 0, 0),),
        "created_by": (("TEXT", 1, None, 0, 0),),
        "created_by_username": (("TEXT", 0, None, 0, 0),),
        "recommendation_json": (("TEXT", 0, None, 0, 0),),
        "created_at": (("TEXT", 1, None, 0, 0),),
        "updated_at": (("TEXT", 1, None, 0, 0),),
    }
    message_fresh = (
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("message_id", "TEXT NOT NULL UNIQUE"),
        ("conversation_id", "TEXT NOT NULL"),
        ("role", "TEXT NOT NULL"),
        ("content", "TEXT NOT NULL"),
        ("recommendation_json", "TEXT"),
        ("file_ids", "TEXT NOT NULL DEFAULT '[]'"),
        ("created_at", "TEXT NOT NULL"),
    )
    message_m7_legacy = (
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("conversation_id", "TEXT NOT NULL"),
        ("role", "TEXT NOT NULL"),
        ("content", "TEXT NOT NULL"),
        ("recommendation_json", "TEXT"),
        ("file_ids", "TEXT NOT NULL DEFAULT '[]'"),
        ("created_at", "TEXT NOT NULL"),
        ("message_id", "TEXT"),
    )
    message_m6_legacy = (
        ("id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
        ("conversation_id", "TEXT NOT NULL"),
        ("role", "TEXT NOT NULL"),
        ("content", "TEXT NOT NULL"),
        ("recommendation_json", "TEXT"),
        ("created_at", "TEXT NOT NULL"),
        ("file_ids", "TEXT NOT NULL DEFAULT '[]'"),
        ("message_id", "TEXT"),
    )
    message_xinfo = {
        "id": (("INTEGER", 0, None, 1, 0),),
        "message_id": (("TEXT", 0, None, 0, 0), ("TEXT", 1, None, 0, 0)),
        "conversation_id": (("TEXT", 1, None, 0, 0),),
        "role": (("TEXT", 1, None, 0, 0),),
        "content": (("TEXT", 1, None, 0, 0),),
        "recommendation_json": (("TEXT", 0, None, 0, 0),),
        "file_ids": (("TEXT", 1, "'[]'", 0, 0),),
        "created_at": (("TEXT", 1, None, 0, 0),),
    }
    return {
        "conversation_table_shape": _p23_required_table_shape_is_canonical(
            conn,
            table="conversations",
            allowed_definition_variants=(
                conversation_fresh,
                conversation_legacy,
            ),
            required_xinfo=conversation_xinfo,
        ),
        "message_table_shape": _p23_required_table_shape_is_canonical(
            conn,
            table="conversation_messages",
            allowed_definition_variants=(
                message_fresh,
                message_m7_legacy,
                message_m6_legacy,
            ),
            required_xinfo=message_xinfo,
        ),
    }


def _assert_p23_identity_table_shapes(conn: sqlite3.Connection) -> None:
    for witness, valid in _p23_identity_table_shape_witnesses(conn).items():
        if valid is not True:
            raise sqlite3.IntegrityError(f"P2.3 schema witness failed: {witness}")


def _p23_index_set_is_canonical(conn: sqlite3.Connection) -> bool:
    """Reject every unapproved explicit index on the three P2.3 tables.

    Even a non-unique expression index is write-observable: evaluating a stale
    ``json_extract``/collation/predicate can abort an otherwise legal insert.
    P2.4+ must therefore add new indexes to the managed contract explicitly.
    """
    tables = (
        "conversations",
        "conversation_messages",
        "conversation_questions",
    )
    for table in tables:
        quoted_table = _p23_quoted_identifier(table)
        for index_row in conn.execute(f"PRAGMA index_list({quoted_table})"):
            index_name = str(index_row[1])
            if index_name in _P23_MANAGED_INDEXES:
                continue
            quoted_index = _p23_quoted_identifier(index_name)
            key_columns = [
                str(row[2])
                for row in conn.execute(f"PRAGMA index_xinfo({quoted_index})")
                if int(row[5]) == 1 and row[2] is not None
            ]
            if (
                table == "conversations"
                and index_name.startswith("sqlite_autoindex_conversations_")
                and key_columns == ["id"]
                and int(index_row[2]) == 1
                and str(index_row[3]) == "pk"
                and int(index_row[4]) == 0
            ):
                continue
            if (
                table == "conversation_messages"
                and index_name.startswith(
                    "sqlite_autoindex_conversation_messages_"
                )
                and key_columns == ["message_id"]
                and int(index_row[2]) == 1
                and str(index_row[3]) == "u"
                and int(index_row[4]) == 0
            ):
                continue
            if (
                table == "conversation_questions"
                and index_name.startswith(
                    "sqlite_autoindex_conversation_questions_"
                )
                and key_columns == ["id"]
                and int(index_row[2]) == 1
                and str(index_row[3]) == "pk"
                and int(index_row[4]) == 0
            ):
                continue
            return False
    return True


def _p23_trigger_set_is_canonical(conn: sqlite3.Connection) -> bool:
    """All persisted triggers on P2.3 tables require explicit management."""
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name IN ('conversations', 'conversation_messages', "
        "'conversation_questions')"
    ).fetchall()
    return {str(row[0]) for row in rows} == set(_P23_MANAGED_TRIGGERS)


def _assert_p23_schema_object_sets(conn: sqlite3.Connection) -> None:
    if _p23_index_set_is_canonical(conn) is not True:
        raise sqlite3.IntegrityError("P2.3 schema witness failed: required_indexes")
    if _p23_trigger_set_is_canonical(conn) is not True:
        raise sqlite3.IntegrityError("P2.3 schema witness failed: required_triggers")


def _p23_public_id(value: object, prefix: str) -> bool:
    return (
        isinstance(value, str)
        and len(value) == len(prefix) + 32
        and value.startswith(prefix)
        and all(char in "0123456789abcdef" for char in value[len(prefix) :])
    )


def _p23_timestamp(value: object) -> datetime | None:
    """Parse only the canonical form accepted by Python/runtime projections."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return None
    if parsed.isoformat(timespec="microseconds") != value:
        return None
    return parsed


def _p23_text(
    value: object, *, maximum: int, nullable: bool = False
) -> bool:
    if value is None:
        return nullable
    return isinstance(value, str) and bool(value.strip()) and len(value) <= maximum


def _p23_options(options_json: object, kind: object) -> list[dict[str, object]] | None:
    if not isinstance(options_json, str):
        return None
    try:
        options = json.loads(options_json)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(options, list):
        return None
    if kind == "single_choice":
        if not 2 <= len(options) <= 6:
            return None
    elif kind == "free_text":
        if options:
            return None
    else:
        return None

    labels: set[str] = set()
    for index, option in enumerate(options, start=1):
        if not isinstance(option, dict) or set(option) != {
            "id",
            "label",
            "description",
        }:
            return None
        if option["id"] != f"option_{index}":
            return None
        if not _p23_text(option["label"], maximum=200):
            return None
        label_key = str(option["label"]).strip().casefold()
        if label_key in labels:
            return None
        labels.add(label_key)
        if not _p23_text(option["description"], maximum=500, nullable=True):
            return None
    canonical = json.dumps(
        options, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    return options if canonical == options_json else None


def _p23_answer(
    answer_json: object,
    *,
    kind: object,
    options: list[dict[str, object]],
) -> bool:
    if not isinstance(answer_json, str):
        return False
    try:
        answer = json.loads(answer_json)
    except (json.JSONDecodeError, TypeError):
        return False
    if not isinstance(answer, dict):
        return False
    if json.dumps(
        answer, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ) != answer_json:
        return False
    if answer.get("kind") == "option":
        return (
            set(answer) == {"kind", "option_id"}
            and kind == "single_choice"
            and answer.get("option_id") in {option["id"] for option in options}
        )
    if answer.get("kind") == "text":
        return set(answer) == {"kind", "text"} and _p23_text(
            answer.get("text"), maximum=4000
        )
    return False


def _assert_p23_historical_rows(conn: sqlite3.Connection) -> None:
    """Validate immutable P2.3 facts after schema convergence, without JSON1.

    Managed triggers constrain future writes but are not retroactive.  A process
    that previously ran with missing/no-op triggers may already contain poison;
    startup must fail without rewriting those facts.  Naturally expired yet still
    unresolved Questions remain valid because expiry status is a read projection.
    """
    invalid_conversation_identity = conn.execute(
        "SELECT id FROM conversations WHERE rowid <= 0 OR id IS NULL "
        "OR typeof(id) <> 'text' OR length(id) = 0 LIMIT 1"
    ).fetchone()
    if invalid_conversation_identity is not None:
        raise sqlite3.IntegrityError("conversation identity is invalid")
    duplicate_conversation_identity = conn.execute(
        "SELECT id FROM conversations GROUP BY id HAVING COUNT(*) <> 1 LIMIT 1"
    ).fetchone()
    if duplicate_conversation_identity is not None:
        raise sqlite3.IntegrityError("conversation id is not unique")
    invalid_message_identity = conn.execute(
        "SELECT id FROM conversation_messages WHERE id <= 0 LIMIT 1"
    ).fetchone()
    if invalid_message_identity is not None:
        raise sqlite3.IntegrityError("conversation message internal id is invalid")
    orphan_message = conn.execute(
        "SELECT message.id FROM conversation_messages AS message "
        "LEFT JOIN conversations AS conversation "
        "ON conversation.id = message.conversation_id "
        "WHERE conversation.id IS NULL LIMIT 1"
    ).fetchone()
    if orphan_message is not None:
        raise sqlite3.IntegrityError("conversation message owner axis is invalid")

    owners = {
        row["id"]: row["created_by_username"]
        for row in conn.execute("SELECT id, created_by_username FROM conversations")
    }
    messages = {
        row["message_id"]: (row["id"], row["conversation_id"], row["role"])
        for row in conn.execute(
            "SELECT id, message_id, conversation_id, role FROM conversation_messages"
        )
    }
    seen_answer_ids: set[str] = set()
    seen_response_ids: set[str] = set()

    for row in conn.execute("SELECT rowid AS _p23_rowid, * FROM conversation_questions"):
        def invalid(detail: str) -> None:
            raise sqlite3.IntegrityError(
                f"conversation question historical row is invalid: {detail}"
            )

        if row["_p23_rowid"] <= 0:
            invalid("internal rowid")
        if not _p23_public_id(row["id"], "q_"):
            invalid("question id")
        if not _p23_public_id(row["conversation_id"], "conv_"):
            invalid("conversation id")
        if not _p23_public_id(row["prompt_message_id"], "msg_"):
            invalid("prompt message id")
        if row["revision"] != 1:
            invalid("revision")
        if not _p23_text(row["prompt"], maximum=500):
            invalid("prompt")
        if not _p23_text(row["description"], maximum=1000, nullable=True):
            invalid("description")
        if not _p23_text(row["asked_to_username"], maximum=100):
            invalid("asked_to_username")
        if owners.get(row["conversation_id"]) != row["asked_to_username"]:
            invalid("owner link")

        prompt_message = messages.get(row["prompt_message_id"])
        if (
            prompt_message is None
            or prompt_message[1] != row["conversation_id"]
            or prompt_message[2] != "assistant"
        ):
            invalid("prompt link")

        created_at = _p23_timestamp(row["created_at"])
        expires_at = _p23_timestamp(row["expires_at"])
        if created_at is None or expires_at is None:
            invalid("timestamp")
        if expires_at - created_at != timedelta(hours=24):
            invalid("TTL")
        options = _p23_options(row["options_json"], row["kind"])
        if options is None:
            invalid("options")

        answer_fields = (
            row["submission_id"],
            row["answer_json"],
            row["answered_by_username"],
            row["answer_message_id"],
            row["response_message_id"],
        )
        closed_reason = row["closed_reason"]
        if closed_reason is None:
            if row["closed_at"] is not None or any(
                value is not None for value in answer_fields
            ):
                invalid("partial unresolved tuple")
            continue

        closed_at = _p23_timestamp(row["closed_at"])
        if closed_at is None or closed_at < created_at:
            invalid("resolution timestamp")
        if closed_reason == "expired":
            if closed_at != expires_at or any(
                value is not None for value in answer_fields
            ):
                invalid("expired tuple")
            continue
        if closed_reason == "superseded":
            if closed_at >= expires_at or any(
                value is not None for value in answer_fields
            ):
                invalid("superseded tuple")
            continue
        if closed_reason != "answered":
            invalid("closed reason")
        if closed_at >= expires_at:
            invalid("answer boundary")
        if (
            not isinstance(row["submission_id"], str)
            or not 8 <= len(row["submission_id"]) <= 128
            or row["answered_by_username"] != row["asked_to_username"]
            or not _p23_public_id(row["answer_message_id"], "msg_")
            or not _p23_public_id(row["response_message_id"], "msg_")
            or not _p23_answer(
                row["answer_json"], kind=row["kind"], options=options
            )
        ):
            invalid("answer tuple")
        if row["answer_message_id"] in seen_answer_ids:
            invalid("answer message reuse")
        if row["response_message_id"] in seen_response_ids:
            invalid("response message reuse")
        seen_answer_ids.add(row["answer_message_id"])
        seen_response_ids.add(row["response_message_id"])
        answer_message = messages.get(row["answer_message_id"])
        response_message = messages.get(row["response_message_id"])
        if (
            answer_message is None
            or response_message is None
            or answer_message[1:] != (row["conversation_id"], "user")
            or response_message[1:] != (row["conversation_id"], "assistant")
            or not prompt_message[0] < answer_message[0] < response_message[0]
        ):
            invalid("answer message order")


_DEFAULT_BUSY_TIMEOUT_MS = 5_000
_INIT_BUSY_TIMEOUT_MS = 30_000


def get_conn(db_path: str | Path) -> sqlite3.Connection:
    """打开一个 sqlite3 连接：Row 工厂 + WAL + 外键约束 + 手动事务模式。

    busy_timeout 显式设 5000ms：并发写的可用性此前隐式依赖 Python sqlite3
    默认 timeout=5.0（审计 P3——若有人改 connect 参数或依赖漂移，BEGIN IMMEDIATE
    竞争会立刻 database is locked）。显式声明使这一承载并发正确性的前提可见。
    """
    # P0-B2（Codex 命中即审 P1-1）：DB-open 单一边界强制本地盘。init_db/worker/
    # user_admin/deploy_selfcheck 全经此开库——在此拦保证任何入口都不会在网络盘上
    # sqlite3.connect（会建 WAL 文件、静默腐化）。连接前置的 mkdir 类 I/O 由各启动点
    # （main lifespan / worker）更早的 assert_local_db_path 拦；此处是覆盖全部 CLI 的
    # 单一真源。每路径每进程只校一次（memo）。
    key = str(db_path)
    if key not in _VALIDATED_DB_PATHS:
        config.assert_local_db_path(db_path)
        _VALIDATED_DB_PATHS.add(key)
    busy_timeout_ms = _DEFAULT_BUSY_TIMEOUT_MS
    conn = sqlite3.connect(
        str(db_path), isolation_level=None, timeout=busy_timeout_ms / 1000
    )
    try:
        conn.row_factory = sqlite3.Row
        # journal_mode is exceptional: on a pre-WAL database SQLite may return
        # ``database is locked`` immediately and bypass the connection's ordinary
        # busy handler.  Install the visible budget first, then retry this one
        # startup transition within the same bounded five-second window.
        conn.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
        deadline = time.monotonic() + busy_timeout_ms / 1000
        delay = 0.01
        while True:
            try:
                row = conn.execute("PRAGMA journal_mode=WAL").fetchone()
                if row is not None and str(row[0]).lower() == "wal":
                    break
                error: sqlite3.OperationalError = sqlite3.OperationalError(
                    "WAL journal mode was not enabled"
                )
            except sqlite3.OperationalError as exc:
                detail = str(exc).lower()
                if "locked" not in detail and "busy" not in detail:
                    raise
                error = exc
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise error
            time.sleep(min(delay, remaining))
            delay = min(delay * 2, 0.1)
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA recursive_triggers=ON")
        return conn
    except Exception:
        conn.close()
        raise


def _execute_script_in_transaction(
    conn: sqlite3.Connection, script: str
) -> None:
    """Execute canonical DDL without ``executescript``'s implicit COMMIT.

    ``sqlite3.Connection.executescript`` commits any active transaction before
    running.  ``init_db`` must hold one ``BEGIN IMMEDIATE`` across evidence
    preflight and schema convergence; otherwise a second initializer can
    observe the first halfway through creating the three judgment ledgers and
    misclassify that transient as deletion residue.  ``complete_statement``
    understands trigger bodies, so each canonical statement remains intact.
    """
    pending: list[str] = []
    for line in script.splitlines(keepends=True):
        pending.append(line)
        candidate = "".join(pending)
        if sqlite3.complete_statement(candidate):
            statement = candidate.strip()
            if statement:
                conn.execute(statement)
            pending.clear()
    if "".join(pending).strip():
        raise sqlite3.OperationalError("canonical DDL contains an incomplete statement")


def init_db(db_path: str | Path) -> None:
    """幂等建表：CREATE TABLE IF NOT EXISTS，可重复调用。

    另含最小幂等列迁移：CREATE TABLE IF NOT EXISTS 不会给**已存在**的表补新列，
    对存量库需 ALTER TABLE 补齐（V0.1 无迁移框架，此处按列探测，重复调用安全）。
    """
    conn = get_conn(db_path)
    try:
        # Serialize the entire evidence preflight + convergence window across
        # API/worker processes.  Deep O(N) witnesses can keep a peer beyond the
        # ordinary request-write budget, so only this lock acquisition gets a
        # larger bounded wait; restore the runtime budget immediately after the
        # lock is held.  Releasing the lock between checks would let a peer see
        # legitimate half-created schema as tamper residue.
        conn.execute(f"PRAGMA busy_timeout={_INIT_BUSY_TIMEOUT_MS}")
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"PRAGMA busy_timeout={_DEFAULT_BUSY_TIMEOUT_MS}")
        # 在任何 CREATE/收敛动作之前先看现场：若已有任一非空判断账本，则三张
        # 表和全部 canonical 对象必须原本就在位。否则 `_DDL` 补一张被删的表、
        # 或后文重建 no-op trigger 后再报绿，会掩盖历史保护窗已经断裂的事实。
        judgment_table_names = (
            "task_review_advice",
            "task_human_decisions",
            "task_review_event_witnesses",
        )
        existing_judgment_tables = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name IN (?, ?, ?)",
                judgment_table_names,
            )
        }
        review_event_witness_table_existed = (
            "task_review_event_witnesses" in existing_judgment_tables
        )
        judgment_managed_object_names = (
            *_JUDGMENT_MANAGED_TRIGGERS,
            *_JUDGMENT_MANAGED_INDEXES,
        )
        object_placeholders = ",".join(
            "?" for _ in judgment_managed_object_names
        )
        existing_judgment_objects = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type IN ('trigger', 'index') "
                f"AND name IN ({object_placeholders})",
                judgment_managed_object_names,
            )
        }
        # 一旦任一受管表/对象存在，说明判断账本代际已经开始落地。此时缺少任一
        # 物理账本可能意味着整表证据被删；不得让 `_DDL` 静默补回一张空表。
        judgment_schema_residue = bool(
            existing_judgment_tables or existing_judgment_objects
        )
        if (
            judgment_schema_residue
            and existing_judgment_tables != set(judgment_table_names)
        ):
            raise sqlite3.IntegrityError(
                "judgment schema residue is missing a required table"
            )
        judgment_was_nonempty = any(
            conn.execute(
                f"SELECT EXISTS(SELECT 1 FROM {table_name} LIMIT 1)"
            ).fetchone()[0]
            == 1
            for table_name in existing_judgment_tables
        )
        if judgment_was_nonempty:
            from .review_schema import assert_judgment_schema

            assert_judgment_schema(conn)
        # Outcome ledger is likewise evidence-bearing once the first cohort
        # marker exists.  A missing managed guard on a nonempty ledger means the
        # historical protection window is unknowable; never silently recreate
        # the guard and report green.  Empty/new ledgers may converge below.
        outcome_table_exists = conn.execute(
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'artifact_outcome_events'"
        ).fetchone() is not None
        outcome_managed_names = (
            *_OUTCOME_MANAGED_TRIGGERS,
            *_OUTCOME_MANAGED_INDEXES,
        )
        outcome_object_placeholders = ",".join(
            "?" for _ in outcome_managed_names
        )
        existing_outcome_objects = {
            str(row[0])
            for row in conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type IN ('trigger', 'index') "
                f"AND name IN ({outcome_object_placeholders})",
                outcome_managed_names,
            )
        }
        outcome_was_nonempty = bool(
            outcome_table_exists
            and conn.execute(
                "SELECT EXISTS(SELECT 1 FROM artifact_outcome_events LIMIT 1)"
            ).fetchone()[0]
            == 1
        )
        if not outcome_table_exists and existing_outcome_objects:
            raise sqlite3.IntegrityError(
                "outcome schema residue exists without artifact_outcome_events table"
            )
        if (
            outcome_was_nonempty
            and existing_outcome_objects != set(outcome_managed_names)
        ):
            raise sqlite3.IntegrityError(
                "nonempty outcome ledger is missing a managed append-only witness"
            )
        if outcome_was_nonempty:
            from .outcome_schema import assert_outcome_schema

            assert_outcome_schema(conn)
        # Once this schema generation has begun protecting any event/review/
        # terminal evidence, an empty outcome ledger is not permission to wash
        # a missing or no-op review seal back to green.  A genuine pre-ADR-0036
        # legacy database has no outcome table and may converge once; every
        # subsequent startup must preserve the exact protection window.
        task_events_has_rows = bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'task_events'"
            ).fetchone()
            and conn.execute(
                "SELECT EXISTS(SELECT 1 FROM task_events LIMIT 1)"
            ).fetchone()[0]
            == 1
        )
        decisions_have_rows = bool(
            "task_human_decisions" in existing_judgment_tables
            and conn.execute(
                "SELECT EXISTS(SELECT 1 FROM task_human_decisions LIMIT 1)"
            ).fetchone()[0]
            == 1
        )
        sealed_task_has_rows = bool(
            conn.execute(
                "SELECT 1 FROM sqlite_master "
                "WHERE type = 'table' AND name = 'tasks'"
            ).fetchone()
            and conn.execute(
                "SELECT EXISTS(SELECT 1 FROM tasks "
                "WHERE status IN ('waiting_review','completed','failed','cancelled') LIMIT 1)"
            ).fetchone()[0]
            == 1
        )
        review_seal_has_evidence = bool(
            outcome_table_exists
            and (task_events_has_rows or decisions_have_rows or sealed_task_has_rows)
        )
        if review_seal_has_evidence and not outcome_was_nonempty:
            from .outcome_schema import review_seal_triggers_are_canonical

            if review_seal_triggers_are_canonical(conn) is not True:
                raise sqlite3.IntegrityError(
                    "review seal evidence lacks exact append-only witnesses"
                )
        # ADR-0036 v5 adds signed task/file snapshots to every ledger row.
        # SQLite cannot add the nullable columns and recover the canonical
        # CREATE TABLE digest in place.  Rebuild only an empty pre-v5 ledger;
        # a nonempty ledger was already required to pass the exact current
        # witness above and therefore fails closed instead of being rewritten.
        if outcome_table_exists and not outcome_was_nonempty:
            outcome_columns = {
                str(row[1])
                for row in conn.execute(
                    "PRAGMA table_xinfo(artifact_outcome_events)"
                )
            }
            snapshot_columns = {
                "source_task_witness_json",
                "source_file_witness_json",
            }
            if not snapshot_columns.issubset(outcome_columns):
                if review_seal_has_evidence:
                    raise sqlite3.IntegrityError(
                        "pre-snapshot outcome ledger with review evidence "
                        "requires manual migration"
                    )
                for trigger_name in _OUTCOME_MANAGED_TRIGGERS:
                    conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
                for index_name in _OUTCOME_MANAGED_INDEXES:
                    conn.execute(f"DROP INDEX IF EXISTS {index_name}")
                conn.execute("DROP TABLE artifact_outcome_events")
        _execute_script_in_transaction(conn, _DDL)
        # First strict-generation install seals every pre-existing review event
        # byte-for-byte before runtime review triggers are installed.  Existing
        # events without an exact decision remain explicitly legacy; they are
        # preserved for historical K1 compatibility but never promoted into a
        # structured decision.  On subsequent startups the table already
        # exists, so missing/tampered witness rows are not backfilled away.
        if not review_event_witness_table_existed:
            conn.execute(
                """
                INSERT INTO task_review_event_witnesses (
                    event_id, event_internal_id, task_id, agent_id, event_type,
                    level, message, payload_json, created_at, decision_id,
                    witness_kind, schema_version
                )
                SELECT
                    review.event_id,
                    review.id,
                    review.task_id,
                    review.agent_id,
                    review.event_type,
                    review.level,
                    review.message,
                    review.payload_json,
                    review.created_at,
                    CASE WHEN decision.id IS NULL THEN NULL ELSE decision.id END,
                    CASE WHEN decision.id IS NULL
                         THEN 'legacy_pre_instrumentation'
                         ELSE 'structured_v1'
                    END,
                    1
                FROM task_events AS review
                LEFT JOIN task_human_decisions AS decision
                  ON decision.task_id = review.task_id
                 AND json_valid(review.payload_json) = 1
                 AND json_type(review.payload_json) = 'object'
                 AND json_type(review.payload_json, '$.decision_id') = 'text'
                 AND json_extract(review.payload_json, '$.decision_id') = decision.id
                 AND review.event_type = CASE decision.action
                     WHEN 'approve' THEN 'review_approved'
                     ELSE 'review_rejected'
                 END
                WHERE review.event_type IN ('review_approved', 'review_rejected')
                """
            )
        # 迁移 #1（ADR-0013）：model_calls.conversation_id——导引会话的模型调用归因。
        # 并发启动安全（Codex R1-P1）：API 进程与 Job Runner 进程都在启动时调
        # init_db，对 pre-ADR-0013 存量库，无锁的 check-then-ALTER 会让双方同时
        # 观察到「列缺失」，输家撞 duplicate column name 直接启动失败。改为先
        # BEGIN IMMEDIATE 拿写锁、锁内复查——锁内读到的列集即权威，赢家先完成
        # 迁移则此处如实跳过。
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
            # 迁移 #15（P2.3）：conversation_messages.message_id——公开稳定引用轴。
            # fresh DDL 为 NOT NULL；legacy SQLite 无法原位补 NOT NULL，故写锁内补
            # nullable 列并逐行生成 msg_<32hex>，随后 unique index + insert trigger
            # 共同保证新写必填且不可替换。重复/并发 init 只填 NULL，不改稳定 id。
            msg_cols_v15 = {
                row[1] for row in conn.execute("PRAGMA table_info(conversation_messages)")
            }
            if "message_id" not in msg_cols_v15:
                conn.execute(
                    "ALTER TABLE conversation_messages ADD COLUMN message_id TEXT"
                )
            legacy_message_rows = conn.execute(
                "SELECT id FROM conversation_messages "
                "WHERE message_id IS NULL OR message_id = '' ORDER BY id"
            ).fetchall()
            for row in legacy_message_rows:
                conn.execute(
                    "UPDATE conversation_messages SET message_id = ? WHERE id = ?",
                    (f"msg_{uuid.uuid4().hex}", row[0]),
                )
            # Partial/tampered P2.3 databases may already have a nonempty public
            # id that the legacy backfill must never bless or rewrite.  Validate
            # every persisted value after NULL/empty backfill and fail startup on
            # the first poison row; fixed lowercase IDs remain byte-for-byte stable.
            invalid_message_id = conn.execute(
                "SELECT id FROM conversation_messages "
                "WHERE message_id IS NULL "
                "OR length(message_id) <> 36 "
                "OR substr(message_id, 1, 4) <> 'msg_' "
                "OR substr(message_id, 5) GLOB '*[^0-9a-f]*' "
                "LIMIT 1"
            ).fetchone()
            if invalid_message_id is not None:
                raise sqlite3.IntegrityError(
                    "conversation message public id is invalid"
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
            # 迁移 #11（T2/#5）：eval_runs.snapshot_handle——run 绑定其冻结快照句柄。存量 run
            # 无快照=NULL（执行侧回退活磁盘，向后兼容）。同写锁内探测补列。原 feat 分支标 #10，
            # 合并（→ main）时 #10 已被协作运行时 forge 的 depends_on/input_binding 占用，顺延 #11。
            eval_cols = {row[1] for row in conn.execute("PRAGMA table_info(eval_runs)")}
            if "snapshot_handle" not in eval_cols:
                conn.execute("ALTER TABLE eval_runs ADD COLUMN snapshot_handle TEXT")
            # 迁移 #12（评审 N4b）：tasks.retry_of——「复制为新任务」血缘注记。可空：
            # 存量/非重跑任务 NULL。纯元数据（见 DDL 注释），无需回填、无 worker 行为
            # 变化（不 bump WORKER_GENERATION：旧 worker 忽略此列零语义损失）。同写锁
            # 内探测补列，口径同前十一迁移。
            task_cols_v12 = {row[1] for row in conn.execute("PRAGMA table_info(tasks)")}
            if "retry_of" not in task_cols_v12:
                conn.execute("ALTER TABLE tasks ADD COLUMN retry_of TEXT")
            # 迁移 #14（P2.3）：conversations.created_by_username——会话稳定 owner。
            # nullable/无 DEFAULT：存量行保留 NULL，绝不从可撞名 created_by 反推；
            # 普通用户查询只按 exact username，故 legacy NULL 天然不可见、不可引用。
            conversation_cols_v14 = {
                row[1] for row in conn.execute("PRAGMA table_info(conversations)")
            }
            if "created_by_username" not in conversation_cols_v14:
                conn.execute(
                    "ALTER TABLE conversations ADD COLUMN created_by_username TEXT"
                )
            # 非空判断账本已经承载不可回溯证据。若启动前其受管 trigger/index
            # 缺失或被替成 no-op，历史期间是否发生过 UPDATE/DELETE/REPLACE 已不可知；
            # 此时自动“修好再报绿”会制造假绿。只允许空账本自动收敛；非空账本先
            # 按当前 canonical contract 完整见证，失败即停机等待取证/人工迁移。
            judgment_has_rows = any(
                conn.execute(
                    f"SELECT EXISTS(SELECT 1 FROM {table_name} LIMIT 1)"
                ).fetchone()[0]
                == 1
                for table_name in (
                    "task_review_advice",
                    "task_human_decisions",
                    "task_review_event_witnesses",
                )
            )
            if judgment_has_rows and review_event_witness_table_existed:
                from .review_schema import assert_judgment_schema

                assert_judgment_schema(conn)
            # Converge every P2.3 managed object, not just missing names.  This
            # repairs stale/no-op trigger bodies and wrong-column/predicate indexes
            # on restart.  All names are static module constants; the write lock
            # prevents another initializer from observing the refresh window.
            for trigger_name in _P23_MANAGED_TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
            for index_name in _P23_MANAGED_INDEXES:
                conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            for trigger_name in _JUDGMENT_MANAGED_TRIGGERS:
                conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
            for index_name in _JUDGMENT_MANAGED_INDEXES:
                conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            outcome_has_rows = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM artifact_outcome_events LIMIT 1)"
            ).fetchone()[0] == 1
            if not outcome_has_rows:
                for trigger_name in _OUTCOME_REQUIRED_TRIGGERS:
                    conn.execute(f"DROP TRIGGER IF EXISTS {trigger_name}")
                for index_name in _OUTCOME_MANAGED_INDEXES:
                    conn.execute(f"DROP INDEX IF EXISTS {index_name}")
            # 索引必须在存量列迁移完成后创建，否则旧库尚无 conversation_id 时
            # 会在建表脚本阶段直接失败。与迁移共用写锁，重复启动亦幂等。
            for statement in _INDEX_DDL:
                conn.execute(statement)
            for statement in _JUDGMENT_OBJECT_DDL:
                conn.execute(statement)
            for statement in _OUTCOME_OBJECT_DDL:
                conn.execute(statement)
            from .outcome_schema import assert_outcome_schema

            assert_outcome_schema(conn)
            _assert_p23_identity_table_shapes(conn)
            _assert_p23_schema_object_sets(conn)
            _assert_p23_historical_rows(conn)
            # Shared startup/readiness/deploy witness: a same-column loose table
            # or same-name stale object is not an acceptable partial migration.
            # Import locally to keep db.py <-> p23_schema canonical derivation
            # acyclic at module load time.
            from .p23_schema import assert_p23_schema

            assert_p23_schema(conn)
            # 判断账本与 P2.3 一样按完整 SQL 语义见证；同名 no-op trigger
            # 或宽松 lookalike table 都不能被启动路径误报为可信。
            from .review_schema import assert_judgment_schema

            assert_judgment_schema(conn)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
