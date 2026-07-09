#!/usr/bin/env bash
# 启动 Vue 前端 dev server（M2 实现）。
# 端口 8621，/api 代理到后端 127.0.0.1:8620（见 frontend/vite.config.js）。
set -euo pipefail
cd "$(dirname "$0")/../frontend"

if [ ! -d node_modules ]; then
  echo "node_modules 缺失：先执行  cd frontend && npm install"
  exit 1
fi

exec npm run dev
