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

# 异步评测队列并发配额（T1，GH #2）：worker 同时最多认领执行的 eval-run 数上限，
# 超出的排队最终执行（非拒绝）。轻内核默认 2（case 数小、无 Redis/Celery）；
# 内网可 export FLAI_EVAL_QUOTA 调整。下限夹 1（0/负会永久卡住队列）。
DEFAULT_EVAL_QUOTA = max(1, int(os.environ.get("FLAI_EVAL_QUOTA", "2")))

# ADR-0036 API 代际。布尔 axis 只能区分“接过/没接过”功能，无法阻止初版
# outcome API 在 DB 已迁到收紧版后继续存活并以旧的 post-send cohort 发现逻辑漏过
# 部署门。精确字符串同时覆盖 request-entry snapshot、decision-bound capture、
# review seal、逐 review-event exact bytes/internal-id witness、独立事件形态/SQLite
# storage-class/canonical-UTC 重验、父级 rowid+updated_at signed snapshot、判断轴合取
# 与每轮 live deep provenance。
OUTCOME_TELEMETRY_GENERATION = "adr36-signed-review-event-canonical-time-v8"

# P2.8 API/schema generation.  The value deliberately carries the current
# trust boundary: the Open Design producer remains disabled and emits
# sensitive/unattested candidates, so live admission is blocked until the
# deferred role/declassification axis exists.  This witnesses code parity; it
# is not a production-readiness claim.
DESIGN_PROMOTION_GENERATION = "p28-disabled-sensitive-trial-v1"

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
# 批八（Codex R0 P1）：runtime._execute 新增执行期 disabled 兜底——worker 可见
# 行为变更（缺此分支的旧 worker 会硬跑已禁用 agent 的滞留任务），bump 逼重启。
# ADR-0036：resolver 的 enqueue 事务新增 exact pipeline_handoff 结果见证。旧 worker
# 虽能继续入队，却不会写 flow ledger，会让 API/DB 新代际在真实使用中静默漏数；
# 因而必须 bump，readyz/deploy_selfcheck 以心跳代际拒绝混版。
WORKER_GENERATION = (
    "collab-resolver+t2-eval-snapshot+b3-llm-timeout+b8-disabled-gate"
    "+adr36-outcome-flow"
)

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
