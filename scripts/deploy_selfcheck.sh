#!/usr/bin/env bash
# 部署自检门（M11-C2）：包装 deploy_selfcheck.py，纯 stdlib 免依赖安装。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

exec python3 scripts/deploy_selfcheck.py "$@"
