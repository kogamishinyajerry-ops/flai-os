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

run_suite() { # $1=e2e 脚本相对路径；结果落全局 OUT/RC——不吞退出码（Codex R0 审 P2）
  set +e
  OUT="$( (cd "$WT" && uv run "${UV_ARGS[@]}" python "$1" 2>&1) )"
  RC=$?
  set -e
}

green_of() { # 套件各自的全绿汇总行
  case "$1" in
    *m10*) echo 'M10 ACCEPTANCE ALL GREEN' ;;
    *) echo 'CRAFT DESKTOP ALL GREEN' ;;
  esac
}

failsum_of() { # 套件各自的 FAILED 汇总行（须真到达汇总，中途崩不算干净咬合）
  case "$1" in
    *m10*) echo 'M10 ACCEPTANCE FAILED' ;;
    *) echo 'CRAFT DESKTOP FAILED' ;;
  esac
}

baseline() { # $1=套件；clean HEAD 必须全绿——否则既有红会被误归因成 tamper 咬合
  echo "== baseline: $1 =="
  (cd "$WT/frontend" && npm run build >/dev/null 2>&1)
  run_suite "$1"
  if [ "$RC" -eq 0 ] && grep -qF "$(green_of "$1")" <<<"$OUT"; then
    echo "BASELINE-GREEN: $1"
  else
    echo "BASELINE-RED: ${1} —— clean HEAD 不绿（RC=${RC}），replay 前提不成立"
    echo "$OUT" | tail -8
    exit 1
  fi
}

replay() { # $1=名 $2=套件 $3=预期 FAIL grep（fixed string） $4=python patch 源码
  local name="$1" suite="$2" expect="$3" patch="$4"
  echo "== replay: $name =="
  (cd "$WT" && python3 -c "$patch")
  (cd "$WT/frontend" && npm run build >/dev/null 2>&1)
  run_suite "$suite"
  # 咬合三条件同时成立（Codex R0 审 P2）：非零退出码 + 精确预期 FAIL 行 +
  # 正常到达 FAILED 汇总（排除中途崩溃被当成咬合）。
  if [ "$RC" -ne 0 ] && grep -qF "$expect" <<<"$OUT" && grep -qF "$(failsum_of "$suite")" <<<"$OUT"; then
    echo "BITE-OK: ${name}（预期红命中：${expect}；RC=${RC}；已达 FAILED 汇总）"
  else
    echo "BITE-MISS: ${name} —— 三条件（非零退出/预期 FAIL 行/FAILED 汇总）未同时成立（RC=${RC}）"
    echo "$OUT" | tail -8
    exit 1
  fi
  (cd "$WT" && git checkout -- .)
}

CRAFT=frontend/e2e/craft_desktop_acceptance.py
M10=frontend/e2e/m10_governance_acceptance.py

# macOS 自带 bash 3.2 无关联数组——case 查表零依赖。
# EXPECT 消歧纪律：'FAIL ⑩' 是 ⑩ 与 ⑩' 两行共同前缀，⑩' 独立 flake 会误报
# BITE-OK（3-lens oracle 审 P2）——一律长前缀/直嵌 prime 字符锚死。
suite_of() {
  case "$1" in
    portal-dup-enqueue) echo "$M10" ;;
    *) echo "$CRAFT" ;;
  esac
}

expect_of() {
  case "$1" in
    census-redye)       echo 'FAIL ⑭C3' ;;
    timeout-cut)        echo 'FAIL ⑭C1' ;;
    reduce-sidebar)     echo 'FAIL ⑭C4 ' ;;
    roving-cut)         echo 'FAIL ⑭C6″' ;;
    fitts-shrink)       echo 'FAIL ⑮ ' ;;
    dialog-reduce-cut)  echo 'FAIL ⑭C4′' ;;
    portal-dup-enqueue) echo 'FAIL ⑩入队' ;;
    *) echo "" ;;
  esac
}

patch_of() {
  case "$1" in
    # ── 批次五核心 ──
    census-redye) cat <<'PY'
p="frontend/src/App.vue"; s=open(p).read()
i=s.rindex("</style>"); assert i>0
open(p,"w").write(s[:i]+".nav-link, .today-section-head { color: var(--clay) !important; }\n"+s[i:])
PY
      ;;
    timeout-cut) cat <<'PY'
p="frontend/src/api/client.js"; s=open(p).read()
t="setTimeout(() => controller.abort(), timeoutMs)"; assert t in s
open(p,"w").write(s.replace(t,"setTimeout(() => {}, timeoutMs)"))
PY
      ;;
    reduce-sidebar) cat <<'PY'
p="frontend/src/App.vue"; s=open(p).read()
t=".sidebar { transition: none !important; }"; assert t in s
open(p,"w").write(s.replace(t,""))
PY
      ;;
    # ── 批次六 ──
    roving-cut) cat <<'PY'
p="frontend/src/router/index.js"; s=open(p).read()
t="document.querySelector(\".app-main\")"; assert t in s
open(p,"w").write(s.replace(t,"document.querySelector(\".app-main-x\")"))
PY
      ;;
    fitts-shrink) cat <<'PY'
p="frontend/src/App.vue"; s=open(p).read()
i=s.rindex("</style>"); assert i>0
open(p,"w").write(s[:i]+".sb-foot-btn { flex: 0 0 auto !important; width: 10px !important; height: 10px !important; padding: 0 !important; }\n"+s[i:])
PY
      ;;
    dialog-reduce-cut) cat <<'PY'
p="frontend/src/App.vue"; s=open(p).read()
t=",\n  .el-overlay-dialog,\n  .el-dialog {"; assert t in s
open(p,"w").write(s.replace(t," {"))
PY
      ;;
    portal-dup-enqueue) cat <<'PY'
p="frontend/src/views/AgentPortal.vue"; s=open(p).read()
t=":disabled=\"latestRunInFlight\"\n"; assert t in s
open(p,"w").write(s.replace(t,""))
PY
      ;;
  esac
}

ALL="census-redye timeout-cut reduce-sidebar roving-cut fitts-shrink dialog-reduce-cut portal-dup-enqueue"
NAMES="${*:-$ALL}"

# 先验名合法性 + 汇总用到的套件，各跑一次 clean baseline（全绿才准开咬）。
NEED_CRAFT=0
NEED_M10=0
for n in $NAMES; do
  [ -n "$(expect_of "$n")" ] || { echo "未知 replay 名：${n}（可用：${ALL}）"; exit 2; }
  case "$(suite_of "$n")" in
    *m10*) NEED_M10=1 ;;
    *) NEED_CRAFT=1 ;;
  esac
done
if [ "$NEED_CRAFT" -eq 1 ]; then baseline "$CRAFT"; fi
if [ "$NEED_M10" -eq 1 ]; then baseline "$M10"; fi

COUNT=0
for n in $NAMES; do
  replay "$n" "$(suite_of "$n")" "$(expect_of "$n")" "$(patch_of "$n")"
  COUNT=$((COUNT + 1))
done
echo "REPLAY ALL BITES OK（$COUNT 处全部预期红命中，基线先行全绿）"
