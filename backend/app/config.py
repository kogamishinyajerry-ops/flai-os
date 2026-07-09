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
# M2：前端构建产物目录。存在则由 FastAPI 静态托管（内网 Windows 部署免 node），
# 不存在（纯后端/开发期走 vite proxy）则静态路由整体不注册。
FRONTEND_DIST_DIR = REPO_ROOT / "frontend" / "dist"

DB_PATH = Path(os.environ.get("FLAI_DB_PATH", str(DATA_DIR / "flai_os.db")))
BACKEND_PORT = int(os.environ.get("FLAI_BACKEND_PORT", "8620"))


def ensure_dirs() -> None:
    """确保运行期所需的真实目录存在（仅供 app 启动路径调用，测试不应调用本函数）。"""
    for d in (DATA_DIR, UPLOADS_DIR, TASK_RUNS_DIR):
        d.mkdir(parents=True, exist_ok=True)
