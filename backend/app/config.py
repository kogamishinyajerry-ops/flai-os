"""FLAi-OS 后端全局路径与端口配置。

只提供**默认值**：所有存储层/注册表类与函数都必须接受显式路径参数，
不允许在业务逻辑内部直接读这里的常量去访问 data/ 真实目录——
测试永远传 tmp_path，不碰真实 data/（任务书 §13.3 纪律②）。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# 仓库根目录：backend/app/config.py -> parents[0]=app parents[1]=backend parents[2]=仓根
REPO_ROOT = Path(__file__).resolve().parents[2]

AGENTS_DIR = REPO_ROOT / "agents"
TOOLS_DIR = REPO_ROOT / "tools_impl"
CONTRACTS_DIR = REPO_ROOT / "contracts"
DATA_DIR = REPO_ROOT / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
TASK_RUNS_DIR = DATA_DIR / "task_runs"
# ADR-0015：Knowledge Scope 根目录（data/knowledge/<scope_id>/scope.yaml + 源文件）。
# data/vector_store/ 保持占位不占用——BM25 file_dir scope 与未来向量检索分居。
KNOWLEDGE_DIR = DATA_DIR / "knowledge"
# M2：前端构建产物目录。存在则由 FastAPI 静态托管（内网 Windows 部署免 node），
# 不存在（纯后端/开发期走 vite proxy）则静态路由整体不注册。
FRONTEND_DIST_DIR = REPO_ROOT / "frontend" / "dist"

DB_PATH = Path(os.environ.get("FLAI_DB_PATH", str(DATA_DIR / "flai_os.db")))
BACKEND_PORT = int(os.environ.get("FLAI_BACKEND_PORT", "8620"))

# P0-B3（导入准入门，docs/PRODUCTION-READINESS-PROGRAM.md）：模型网关 HTTP 超时可配，
# 替换 gateway 原硬编码 60s。主入口对话/导引全走 reasoning profile，内网大模型长推理
# p99 可能 >60s；硬编码 60 会令每人首条消息 503（最伤采纳信心的 day-one 崩溃）。默认
# 120s 保守值；内网按实测 p99 export FLAI_LLM_TIMEOUT_S。下限夹 1s（0/负会令请求立即
# 超时永远失败）。
LLM_TIMEOUT_S = max(1.0, float(os.environ.get("FLAI_LLM_TIMEOUT_S", "120")))

# 单次模型调用的最大尝试数（gateway 重试轮）——**墙钟派生的 SSOT**（gateway._post 的
# `for attempt in range(...)` 直读本值，见 model_gateway/gateway.py）。墙钟必须覆盖每次调用
# 的全部尝试（都超时=最坏 LLM_TIMEOUT_S × 尝试数），否则合法重试会被 reaper 假杀。下限夹 1。
LLM_MAX_ATTEMPTS_PER_CALL = max(1, int(os.environ.get("FLAI_LLM_MAX_ATTEMPTS", "2")))

# Gate2-T1-M1（Codex R1-P1-b 生命周期修）：单个任务在一次执行里可能**串行**发起多次模型调用
# （如 knowledge_qa_agent 按 input maxItems 逐问检索+生成，每问一次 chat）。墙钟派生若只算「单次
# 最长工具调用」会漏掉这条串行 LLM 生命周期——8 问的合法任务最坏 8×(LLM_TIMEOUT_S×尝试数) 远超
# 只含单工具预算的旧墙钟，会被 reaper 假杀（Codex 逮的正是此）。本常量=墙钟派生假设的**单任务
# 最大串行 LLM 调用数上界**（default 12，覆盖现役最深的 8 问 agent 并留 50% 余量）。任一 agent
# 的实际串行调用数超过本值时，operator 须 export FLAI_MAX_LLM_CALLS_PER_TASK 上调，否则该 agent
# 的合法长执行会被墙钟假杀。下限夹 1。
MAX_SEQUENTIAL_LLM_CALLS_PER_TASK = max(
    1, int(os.environ.get("FLAI_MAX_LLM_CALLS_PER_TASK", "12"))
)

# 单任务最大合法 LLM 生命周期预算（秒）=单次调用最坏耗时（超时×尝试数）× 最大串行调用数。
# 墙钟派生把它加进「工具预算 + 生成余量」之上，**结构性保证墙钟 ≥ 任何 agent 的最大合法生命
# 周期**（工具编排 + 串行 LLM 循环都不会被假杀，Codex R1-P1-b）。
DEFAULT_LLM_LIFECYCLE_BUDGET_S = (
    LLM_TIMEOUT_S * LLM_MAX_ATTEMPTS_PER_CALL * MAX_SEQUENTIAL_LLM_CALLS_PER_TASK
)

# 异步评测队列并发配额（T1，GH #2）：worker 同时最多认领执行的 eval-run 数上限，
# 超出的排队最终执行（非拒绝）。轻内核默认 2（case 数小、无 Redis/Celery）；
# 内网可 export FLAI_EVAL_QUOTA 调整。下限夹 1（0/负会永久卡住队列）。
DEFAULT_EVAL_QUOTA = max(1, int(os.environ.get("FLAI_EVAL_QUOTA", "2")))

# Gate2-T1-M1（per-task 墙钟 reaper · owner Q1 裁定重构为宽墙钟挂死兜底）：单个任务执行的
# 墙钟上限秒。JobRunner 单串行 worker 主循环在 daemon 线程内跑 execute() 并 join(本值)——超时
# 即放弃等待、把任务从执行态置 failed 留痕，worker 立即认领下一条（一条挂死任务不再永久冻结
# 整条队列）。
#
# ★owner Q1：墙钟**不再是快回收旋钮**（旧默认 180s < cfd_solve_launch 工具预算 360s，会把合法
# 长任务假杀）。改为**动态派生**并**保证墙钟 ≥ 任何合法工具预算**：真实 worker 在 runner 启动
# 处读工具注册表全部 runtime.timeout_seconds 取 max，经 derive_task_wall_timeout_s() 兜底
# （+生成余量、硬地板、env 覆盖只能上抬不能下压到工具预算以下）。config 此处只留 env 覆盖 +
# 兜底常量 + 纯派生函数（无 tool_registry 可读时的 TASK_WALL_TIMEOUT_S 兜底默认）。
#
# env 覆盖语义变更（fail-safe）：FLAI_TASK_WALL_TIMEOUT_S 只能把墙钟**上抬**（owner 有意给长
# 任务更多余量），绝不能下压到工具预算以下——否则又回到「合法工具被假杀」。故 derive 用 max()
# 夹逼：env 覆盖 < max_tool_budget 时 env 被兜底忽略、runner 启动 log 警告（不 fail）。
# 诚实边界：被放弃的执行线程 Python 无法强杀（ADR-0008 决策3），残余产物靠进程重启
# recover_interrupted_tasks 回收。
TASK_WALL_TIMEOUT_ENV_OVERRIDE: float | None = (
    max(1.0, float(os.environ["FLAI_TASK_WALL_TIMEOUT_S"]))
    if os.environ.get("FLAI_TASK_WALL_TIMEOUT_S") is not None
    else None
)
# 生成余量：在最大工具预算之上再留一段给编排/LLM 生成/落库等工具外开销（默认 300s）。
TASK_WALL_TIMEOUT_GENERATION_MARGIN_S = max(
    1.0, float(os.environ.get("FLAI_TASK_WALL_MARGIN_S", "300"))
)
# 硬地板：即便工具预算很小，墙钟也不低于此值（默认 600s，防挂死任务被过快回收）。
TASK_WALL_TIMEOUT_FLOOR_S = max(1.0, float(os.environ.get("FLAI_TASK_WALL_FLOOR_S", "600")))


def derive_task_wall_timeout_s(
    max_tool_budget_s: float, max_llm_lifecycle_s: float = 0.0
) -> float:
    """据「工具注册表最大 runtime.timeout_seconds」+「单任务最大串行 LLM 生命周期」派生 per-task
    墙钟（纯函数，可单测/tamper）。

    墙钟 = max(工具预算 + LLM 生命周期 + 生成余量, 硬地板, env 覆盖)。**结构性保证墙钟 ≥
    max_tool_budget + max_llm_lifecycle**（余量非负）——既覆盖单次最长工具（cfd_solve_launch=360s），
    又覆盖串行多次模型调用的合法长任务（knowledge_qa 8 问，Codex R1-P1-b）。两项**相加**而非取
    max：一个任务可能既编排工具又串行调模型，加总是安全上界（宁墙钟宽、绝不假杀合法任务）。
    env 覆盖只入 max() 候选=只能上抬，绝不下压到预算以下（fail-safe，owner Q1）。
    """
    budget_based = (
        max(0.0, max_tool_budget_s)
        + max(0.0, max_llm_lifecycle_s)
        + TASK_WALL_TIMEOUT_GENERATION_MARGIN_S
    )
    candidates = [budget_based, TASK_WALL_TIMEOUT_FLOOR_S]
    if TASK_WALL_TIMEOUT_ENV_OVERRIDE is not None:
        candidates.append(TASK_WALL_TIMEOUT_ENV_OVERRIDE)
    return max(candidates)


# 兜底默认（无 tool_registry 可读时用；真实 worker 在 runner 启动处按 registry 派生覆盖）。
# = derive(工具预算 0, 默认 LLM 生命周期)——即便无工具预算也覆盖最大串行 LLM 生命周期（Codex
# R1-P1-b：fallback 不能退回只含地板的旧值，否则无 tool_registry 路径下 8 问 agent 仍被假杀）。
TASK_WALL_TIMEOUT_S = derive_task_wall_timeout_s(0.0, DEFAULT_LLM_LIFECYCLE_BUDGET_S)

# Gate2-T1-M2（worker 可观测 · owner Q2「运行态龄期→degraded」的正确实现，Codex R1-P1-c 修）：
# 最老 queued 任务龄期超过本阈值 → /api/readyz body 的 **degraded 观测标记**置真（HTTP 仍 200，
# **不再 503**）。★Codex R1-P1-c 逮的根因：单串行 worker 健康 drain 合法 backlog 时，排在后面的
# 任务 queued 龄期会自然增长（合法长任务在前面跑），绝对龄期→503 会把健康 worker 误判 down、触发
# 外部重启中断合法长任务。故解耦：**503 只留给心跳死（进程真 down，M2† fail-closed）**；队列/运行态
# 龄期是**可观测 degraded 软信号**（200 + body degraded=true），供 operator dashboard/告警，绝不
# 参与 HTTP 就绪 gate。挂死任务的真正兜底=宽墙钟 reaper（回收后队列自愈），非 readyz 503。
# 默认 600s（> max_tool_budget 360s 避免正常排队即标 degraded）。内网按真实排队 p99 export
# FLAI_QUEUE_STALL_THRESHOLD_S。下限夹 1s（0/负会令任何非空队列瞬间标 degraded=噪声）。
QUEUE_STALL_THRESHOLD_S = max(1.0, float(os.environ.get("FLAI_QUEUE_STALL_THRESHOLD_S", "600")))

# Gate2-T1-A1（运行态龄期观测信号 · 补 loop-auditor 孤立挂死盲点，Codex R1-P1-c 修）：最老
# **执行态**任务（validating/running/parsing/analyzing）龄期超过本阈值 → /api/readyz body 的
# **degraded 观测标记**置真（HTTP 仍 200，**不再 503**，同 QUEUE_STALL 的解耦理由）。「孤立挂死
# 任务冻结单串行 worker」这一失败模式，心跳看不见（daemon 仍新鲜）、queued 龄期也看不见（队列空）
# ——运行态龄期能把它以 degraded 软信号暴露给 operator，但**绝不能凭它 503**：单串行 worker 上，
# 一条合法长任务（8 问 knowledge_qa 最坏 >1900s）与一条挂死任务在龄期上无法区分，凭龄期 503 会
# 假杀合法长任务（Codex R1-P1-c）。真正兜底=宽墙钟 reaper（覆盖最大合法生命周期后回收）。默认
# 600s 仅作 degraded 标记阈（保守早提示，不误 503）。内网按真实执行 p99 export
# FLAI_RUNNING_TASK_STALL_THRESHOLD_S。下限夹 1s（0/负会令任何执行中任务瞬间标 degraded=噪声）。
RUNNING_TASK_STALL_THRESHOLD_S = max(
    1.0, float(os.environ.get("FLAI_RUNNING_TASK_STALL_THRESHOLD_S", "600"))
)

# worker 代际字符串（ADR-0021/Codex R2 审 P2）：放在纯 stdlib 的 config，
# 让部署自检探针（deploy_selfcheck.py，号称免应用依赖）导入它时不连带拉
# jobs.runner→storage.repos→jsonschema。**改派生语义的里程碑同步 bump**——
# ADR-0024 加工具污点轴（文件∨知识∨工具三轴）+ ADR-0025 改「执行期落库不可变
# 任务级分级」（Codex R1-B）：旧 worker（两轴/read 期重派生代码）与新 worker 不可
# 混跑——旧 worker 不落 data_classification、monitor 产物洗成 internal 外泄。代际值
# 变=部署门代际检查逼 worker 重启到新代码。
# 协作运行时（Codex 增量2审 P1）：worker run_forever 每轮新增 resolve_dependencies_once
# ——**这是 worker 行为变更**。若 API 前滚而 worker 滞留旧 commit，旧 worker 从不跑
# resolver，所有带 depends_on 的任务永滞 created 且部署自检误绿。故 bump 代际逼 worker
# 重启到含 resolver 的新代码，否则部署门 check_worker_generation 拦下。
# T1（GH #2，Codex R1 审 P1）：worker 新增必需行为——驱动评测异步队列（EvalRunner）。
# 旧 worker 无此代码时仍产新鲜心跳骗过 deploy_selfcheck，却从不消费 eval_runs，令每个
# 202 入队响应永久停 queued。故随此必需 worker 行为 bump 代际，逼 worker 重启到新代码。
# T2（GH #5，Codex R0 审 P1）：worker 新增必需行为——认领带 snapshot_handle 的 run 时须
# 材化冻结快照执行（读快照非活磁盘）。T1 worker 无此分支会忽略 handle、按活磁盘执行，
# 「评的就是晋升的那版」不可变保证在分离部署窗口内静默失效，而心跳仍新鲜。故随此协议
# 变更 bump 代际，配合 health.eval_snapshot_axis（API 侧见证）双向逼两端重启到新代码。
# T1/T2 分支与协作运行时分支各自独立 bump 代际；合并（feat/eval-async-queue → main）后
# worker 同时具备 resolver + EvalRunner + 快照认领三项新行为，代际值须区别于两条父线
# 各自的值——任一侧滞留旧码（缺 resolver 或缺快照认领）都要被 check_worker_generation 拦下。
# P0-B3（导入准入门，Codex 命中即审 P1-2）：模型网关超时从硬编码 60s 改为可配
# FLAI_LLM_TIMEOUT_S——**worker 可见行为变更**（worker 跑的 job 调 gateway._post）。
# 旧 worker 留 60s 却写同代际会骗过 deploy_selfcheck.check_worker_generation（误绿），
# 故 bump 逼 worker 重启到读 env 的新代码。
# Gate2-T1-M1（per-task 墙钟 reaper）：worker 新增必需行为——run_once 在 daemon 线程内跑
# execute() 并 join(派生墙钟)，超时置 failed 留痕。旧 worker 无 reaper 分支时，一条挂死任务
# 永久冻结整条队列而心跳仍新鲜。故随此必需 worker 行为 bump 代际，逼 worker 重启到含 reaper
# 的新代码，否则部署门 check_worker_generation 拦下。
# Gate2-T1-M1 R2（Codex R1 命中即审修，worker 可见行为变更）：①墙钟派生纳入串行 LLM 生命周期
# （derive 加 max_llm_lifecycle，8 问 agent 不再假杀，P1-b）②发布走 claim_publish_transition
# 原子认领终态（僵尸线程不污染已 reaped 任务，P1-a）③thread.start 失败即置 failed（不搁浅，P2）。
# 旧 worker 缺这三项：墙钟太短假杀合法长任务 / 僵尸线程写脏产物样本 / claim 后搁浅。故 bump
# 代际逼 worker 重启到 R2 新代码。（readyz 龄期已解耦为 200-degraded 观测标记、不再 503，见
# QUEUE_STALL/RUNNING_TASK_STALL；这是 API 侧行为，随 API 前滚。）
WORKER_GENERATION = "collab-resolver+t2-eval-snapshot+b3-llm-timeout+m1-reaper+r1fix-lifecycle-atomic"

# ADR-0022：监控接入生成器承重核（sim-live-hub `tools/adapter_gen.py`）所在仓根。
# monitor_adapter_recon 工具经此子进程调核起草 adapter 草案；未配置=核不可达=工具
# fail-closed（绝不猜路径）。默认 None：本机开发/内网按实况 export FLAI_MONITOR_CORE_DIR。
MONITOR_CORE_DIR = os.environ.get("FLAI_MONITOR_CORE_DIR") or None


def assert_local_db_path(db_path: Path | str) -> None:
    """P0-B2（导入准入门）：DB 必须落本地固定盘，否则启动 fail-closed 拒绝。

    SQLite WAL 在网络盘（UNC/映射盘）上会静默腐化（README/DEPLOYMENT-SUPERVISION
    明列），而 Windows 企业默认常把数据重定向到映射盘。别赌运维读到那行文档表格——
    启动期主动拦，错误方向是多拦（fail-closed 可接受）。

    拦已知网络盘形态（best-effort）：
    - UNC 路径（``\\\\host\\share`` 或 ``//host/share``）：跨平台可判、可测。
    - Windows 映射网络盘（盘符 GetDriveType==DRIVE_REMOTE）：仅 win32 可判；非 Windows
      跳过（诚实占位，本机不可测；残余靠 DEPLOYMENT-SUPERVISION 文档兜）。
    """
    raw = str(db_path)
    norm = raw.replace("\\", "/")
    if norm.startswith("//"):
        raise ValueError(
            f"FLAI_DB_PATH 指向网络共享（UNC）路径：{raw!r}——SQLite WAL 在网络盘上会"
            "静默腐化，必须落本地固定盘（P0-B2 fail-closed 拒启）"
        )
    if sys.platform == "win32":
        import ctypes  # 局部 import：非 Windows 平台绝不触碰

        drive = os.path.splitdrive(os.path.abspath(raw))[0]  # e.g. 'Z:'
        if drive:
            _DRIVE_REMOTE = 4
            if ctypes.windll.kernel32.GetDriveTypeW(f"{drive}\\") == _DRIVE_REMOTE:
                raise ValueError(
                    f"FLAI_DB_PATH 指向映射网络盘 {drive}（DRIVE_REMOTE）：{raw!r}——"
                    "SQLite WAL 会静默腐化，必须落本地固定盘（P0-B2 fail-closed 拒启）"
                )


def ensure_dirs() -> None:
    """确保运行期所需的真实目录存在（仅供 app 启动路径调用，测试不应调用本函数）。"""
    for d in (DATA_DIR, UPLOADS_DIR, TASK_RUNS_DIR, KNOWLEDGE_DIR):
        d.mkdir(parents=True, exist_ok=True)
