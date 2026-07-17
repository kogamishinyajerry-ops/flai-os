#!/usr/bin/env bash
# tamper_replay.sh —— 批次五 §八 retro / 批次六 B6-6：tamper 咬合独立重放。
#
# 动机：tamper 日志（docs/reviews/CRAFT-RULES-B*-tamper-log.md）是执行会话的
# 逐字存档，非可复跑证据。本脚本在隔离 git worktree（基 HEAD）里逐处投毒→
# rebuild→跑套件→断言预期 FAIL 行出现→复位，把「咬合力」变成任何人可一键
# 重验的谓词。任一处预期红未出现（套件反而绿/FAIL 行缺失）即整体 exit 1
# ——replay 自身 fail-closed。
#
# 用法：bash scripts/tamper_replay.sh [replay 名 ...]   # 缺省=全部
#   可用名：census-redye timeout-cut reduce-sidebar roving-cut fitts-shrink
#           dialog-reduce-cut portal-dup-enqueue
# 约 5-6 分钟/处（build+整套 craft e2e）；portal-dup-enqueue 跑 m10 套件较快。
#
# 边界（如实声明）：
# - 重放基 HEAD：未提交的工作区改动不在被测范围（这是特性——replay 证的是
#   已封存代码的咬合，不是脏树）。patch 落空（目标代码不在 HEAD）会被 python
#   assert 咬住并 exit 1，绝不静默跳过。
# - node_modules 以符号链接借用主工作树（worktree 不重装依赖）；若主树依赖
#   缺失，build 步会自然失败。
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WT="$(mktemp -d)/replay-wt"
UV_ARGS=(--no-project --with playwright --with uvicorn --with pytest --with pytest-xdist
  --with jsonschema --with pyyaml --with fastapi --with httpx --with python-multipart
  --with "pydantic>2" --with jieba --with openpyxl)

git -C "$ROOT" worktree add --detach "$WT" HEAD >/dev/null
cleanup() { git -C "$ROOT" worktree remove --force "$WT" >/dev/null 2>&1 || true; }
trap cleanup EXIT
ln -s "$ROOT/frontend/node_modules" "$WT/frontend/node_modules"

run_suite() { # $1=e2e 脚本相对路径；输出落 stdout，永不因套件红中断脚本流
  (cd "$WT" && uv run "${UV_ARGS[@]}" python "$1" 2>&1) || true
}

replay() { # $1=名 $2=套件 $3=预期 FAIL grep（fixed string） $4=python patch 源码
  local name="$1" suite="$2" expect="$3" patch="$4"
  echo "== replay: $name =="
  (cd "$WT" && python3 -c "$patch")
  (cd "$WT/frontend" && npm run build >/dev/null 2>&1)
  local out
  out="$(run_suite "$suite")"
  if grep -qF "$expect" <<<"$out"; then
    echo "BITE-OK: $name（预期红命中：$expect）"
  else
    echo "BITE-MISS: $name —— 预期 FAIL 行未出现，tamper 未被咬住（假绿嫌疑）"
    echo "$out" | tail -8
    exit 1
  fi
  (cd "$WT" && git checkout -- .)
}

CRAFT=frontend/e2e/craft_desktop_acceptance.py
M10=frontend/e2e/m10_governance_acceptance.py

declare -A SUITE EXPECT PATCH

# ── 批次五核心 ──────────────────────────────────────────────────────────
SUITE[census-redye]=$CRAFT
EXPECT[census-redye]='FAIL ⑭C3'
PATCH[census-redye]='
p="frontend/src/App.vue"; s=open(p).read()
i=s.rindex("</style>"); assert i>0
open(p,"w").write(s[:i]+".nav-link, .today-section-head { color: var(--clay) !important; }\n"+s[i:])'

SUITE[timeout-cut]=$CRAFT
EXPECT[timeout-cut]='FAIL ⑭C1'
PATCH[timeout-cut]='
p="frontend/src/api/client.js"; s=open(p).read()
t="setTimeout(() => controller.abort(), timeoutMs)"; assert t in s
open(p,"w").write(s.replace(t,"setTimeout(() => {}, timeoutMs)"))'

SUITE[reduce-sidebar]=$CRAFT
EXPECT[reduce-sidebar]='FAIL ⑭C4 '
PATCH[reduce-sidebar]='
p="frontend/src/App.vue"; s=open(p).read()
t=".sidebar { transition: none !important; }"; assert t in s
open(p,"w").write(s.replace(t,""))'

# ── 批次六 ─────────────────────────────────────────────────────────────
SUITE[roving-cut]=$CRAFT
EXPECT[roving-cut]='FAIL ⑭C6″'
PATCH[roving-cut]='
p="frontend/src/router/index.js"; s=open(p).read()
t="document.querySelector(\".app-main\")"; assert t in s
open(p,"w").write(s.replace(t,"document.querySelector(\".app-main-x\")"))'

SUITE[fitts-shrink]=$CRAFT
EXPECT[fitts-shrink]='FAIL ⑮ '
PATCH[fitts-shrink]='
p="frontend/src/App.vue"; s=open(p).read()
i=s.rindex("</style>"); assert i>0
open(p,"w").write(s[:i]+".sb-foot-btn { flex: 0 0 auto !important; width: 10px !important; height: 10px !important; padding: 0 !important; }\n"+s[i:])'

SUITE[dialog-reduce-cut]=$CRAFT
EXPECT[dialog-reduce-cut]='FAIL ⑭C4′'
PATCH[dialog-reduce-cut]='
p="frontend/src/App.vue"; s=open(p).read()
t=",\n  .el-overlay-dialog,\n  .el-dialog {"; assert t in s
open(p,"w").write(s.replace(t," {"))'

SUITE[portal-dup-enqueue]=$M10
# 「⑩入队」长前缀锚死消歧：'FAIL ⑩' 是 ⑩ 与 ⑩' 两行共同前缀，⑩' 独立
# flake 也会误报 BITE-OK（3-lens oracle 审 P2）。
EXPECT[portal-dup-enqueue]='FAIL ⑩入队'
PATCH[portal-dup-enqueue]='
p="frontend/src/views/AgentPortal.vue"; s=open(p).read()
t=":disabled=\"latestRunInFlight\"\n"; assert t in s
open(p,"w").write(s.replace(t,""))'

ALL=(census-redye timeout-cut reduce-sidebar roving-cut fitts-shrink dialog-reduce-cut portal-dup-enqueue)
NAMES=("${@:-${ALL[@]}}")
for n in "${NAMES[@]}"; do
  [[ -n "${SUITE[$n]:-}" ]] || { echo "未知 replay 名：$n（可用：${ALL[*]}）"; exit 2; }
  replay "$n" "${SUITE[$n]}" "${EXPECT[$n]}" "${PATCH[$n]}"
done
echo "REPLAY ALL BITES OK（${#NAMES[@]} 处全部预期红命中）"
