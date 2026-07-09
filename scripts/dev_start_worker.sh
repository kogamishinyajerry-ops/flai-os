#!/usr/bin/env bash
# 启动 Job Runner 轮询进程 —— M1 实现（见 docs/01_Overall_Architecture.md 里程碑表）。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "启动 FLAi-OS Job Runner：python -m backend.app.jobs.runner"
echo "依赖缺失？先装：pip install fastapi jsonschema pyyaml httpx 'pydantic>2'"

if command -v uv >/dev/null 2>&1; then
  exec uv run --no-project \
    --with fastapi --with jsonschema --with pyyaml --with httpx --with "pydantic>2" \
    -- python -m backend.app.jobs.runner
else
  exec python -m backend.app.jobs.runner
fi
