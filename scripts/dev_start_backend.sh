#!/usr/bin/env bash
# 启动 FastAPI 后端(uvicorn backend.app.main) —— M1 实现（见 docs/01_Overall_Architecture.md 里程碑表）。
set -euo pipefail

# 脚本可能从任意目录调用，先切到仓根（scripts/ 的上一级）。
cd "$(dirname "${BASH_SOURCE[0]}")/.."

PORT="${FLAI_BACKEND_PORT:-8620}"

echo "启动 FLAi-OS 后端：uvicorn backend.app.main:app --port ${PORT}"
echo "依赖缺失？先装：pip install fastapi uvicorn jsonschema pyyaml python-multipart httpx openpyxl 'pydantic>2'"

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project \
    --with fastapi --with uvicorn --with jsonschema --with pyyaml \
    --with python-multipart --with httpx --with openpyxl --with jieba --with "pydantic>2" \
    -- python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}"
else
  exec python -m uvicorn backend.app.main:app --host 0.0.0.0 --port "${PORT}"
fi
