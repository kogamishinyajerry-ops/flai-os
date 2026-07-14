"""FLAi-OS 后端全局路径与端口配置。

只提供**默认值**：所有存储层/注册表类与函数都必须接受显式路径参数，
不允许在业务逻辑内部直接读这里的常量去访问 data/ 真实目录——
测试永远传 tmp_path，不碰真实 data/（任务书 §13.3 纪律②）。
"""

from __future__ import annotations

import os
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

# 异步评测队列并发配额（T1，GH #2）：worker 同时最多认领执行的 eval-run 数上限，
# 超出的排队最终执行（非拒绝）。轻内核默认 2（case 数小、无 Redis/Celery）；
# 内网可 export FLAI_EVAL_QUOTA 调整。下限夹 1（0/负会永久卡住队列）。
DEFAULT_EVAL_QUOTA = max(1, int(os.environ.get("FLAI_EVAL_QUOTA", "2")))

# worker 代际字符串（ADR-0021/Codex R2 审 P2）：放在纯 stdlib 的 config，
# 让部署自检探针（deploy_selfcheck.py，号称免应用依赖）导入它时不连带拉
# jobs.runner→storage.repos→jsonschema。**改派生语义的里程碑同步 bump**——
# ADR-0024 加工具污点轴（文件∨知识∨工具三轴）+ ADR-0025 改「执行期落库不可变
# 任务级分级」（Codex R1-B）：旧 worker（两轴/read 期重派生代码）与新 worker 不可
# 混跑——旧 worker 不落 data_classification、monitor 产物洗成 internal 外泄。代际值
# 变=部署门代际检查逼 worker 重启到新代码。
WORKER_GENERATION = "m12-immutable-classification"

# ADR-0022：监控接入生成器承重核（sim-live-hub `tools/adapter_gen.py`）所在仓根。
# monitor_adapter_recon 工具经此子进程调核起草 adapter 草案；未配置=核不可达=工具
# fail-closed（绝不猜路径）。默认 None：本机开发/内网按实况 export FLAI_MONITOR_CORE_DIR。
MONITOR_CORE_DIR = os.environ.get("FLAI_MONITOR_CORE_DIR") or None


def ensure_dirs() -> None:
    """确保运行期所需的真实目录存在（仅供 app 启动路径调用，测试不应调用本函数）。"""
    for d in (DATA_DIR, UPLOADS_DIR, TASK_RUNS_DIR, KNOWLEDGE_DIR):
        d.mkdir(parents=True, exist_ok=True)
