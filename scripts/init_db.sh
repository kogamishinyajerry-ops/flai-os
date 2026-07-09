#!/usr/bin/env bash
# 初始化 SQLite 数据库表 —— M1 实现（见 docs/01_Overall_Architecture.md 里程碑表）。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "初始化 FLAi-OS SQLite 数据库（幂等，可重复执行）..."

PY_CMD='
from backend.app import config
from backend.app.storage.db import init_db
config.ensure_dirs()
init_db(config.DB_PATH)
print(f"已初始化：{config.DB_PATH}")
'

if command -v uv >/dev/null 2>&1; then
  uv run --no-project --with jsonschema --with pyyaml -- python -c "${PY_CMD}"
else
  python -c "${PY_CMD}"
fi
