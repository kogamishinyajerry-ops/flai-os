#!/usr/bin/env bash
# 一键执行前端构建、后端全量测试与五组浏览器验收；任一步失败立即汇总退出。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

COMPLETED_STEPS=()
FAILED_STEPS=()

print_summary() {
  echo
  echo "验证步骤汇总："
  if ((${#COMPLETED_STEPS[@]})); then
    for step in "${COMPLETED_STEPS[@]}"; do
      echo "- [完成] ${step}"
    done
  else
    echo "- [完成] （无）"
  fi
  if ((${#FAILED_STEPS[@]})); then
    for step in "${FAILED_STEPS[@]}"; do
      echo "- [失败] ${step}"
    done
  else
    echo "- [失败] （无）"
  fi
}

run_step() {
  local name="$1"
  shift
  echo
  echo "开始：${name}"
  if "$@"; then
    COMPLETED_STEPS+=("${name}")
    echo "完成：${name}"
  else
    local exit_code=$?
    FAILED_STEPS+=("${name}（退出码 ${exit_code}）")
    print_summary
    exit "${exit_code}"
  fi
}

build_frontend() {
  (cd frontend && npm run build)
}

run_step "① frontend npm run build" build_frontend

# 不限定路径：跑满 pyproject testpaths（tests/ + tools_impl/ + backend/tests），
# 只跑 backend/tests 会漏掉契约与工具包测试（Codex 互审 P2）。
run_step "② 全量 pytest -n auto（三个 testpaths）" \
  uv run --no-project \
    --with pytest --with pytest-xdist --with jsonschema --with pyyaml \
    --with fastapi --with httpx --with python-multipart --with "pydantic>2" \
    --with jieba --with openpyxl \
    python -m pytest -q -n auto

# node --test 若显式给目录参数（如 `tests/`）,本机 node v24 会把该参数当 CJS
# entry module 解析而非测试目录,报 MODULE_NOT_FOUND；不带路径参数走默认发现
# （test/、tests/、**/*.test.{js,mjs,cjs}）才能正确扫到 frontend/tests/。
test_frontend_core() {
  (cd frontend && node --test)
}

run_step "①b 前端纯函数核 node --test" test_frontend_core

E2E_SCRIPTS=(
  "frontend/e2e/m2_acceptance.py"
  "frontend/e2e/m6_guide_acceptance.py"
  "frontend/e2e/m8_collab_chain_acceptance.py"
  "frontend/e2e/m8_guide_orchestrator_acceptance.py"
  "frontend/e2e/m8_workbench_acceptance.py"
  "frontend/e2e/m9_guide_loop_acceptance.py"
  "frontend/e2e/m10_governance_acceptance.py"
  "frontend/e2e/m11_auth_acceptance.py"
  "frontend/e2e/cfd_flow_acceptance.py"
  "frontend/e2e/batch_a_livefeed_acceptance.py"
  "frontend/e2e/batch_b_today_acceptance.py"
  "frontend/e2e/batch_c_rewards_acceptance.py"
  "frontend/e2e/batch_d_visual_acceptance.py"
)

for script in "${E2E_SCRIPTS[@]}"; do
  run_step "③ E2E ${script}" \
    uv run --no-project \
      --with playwright --with uvicorn --with pytest --with pytest-xdist \
      --with jsonschema --with pyyaml --with fastapi --with httpx \
      --with python-multipart --with "pydantic>2" --with jieba --with openpyxl \
      python "${script}"
done

print_summary
