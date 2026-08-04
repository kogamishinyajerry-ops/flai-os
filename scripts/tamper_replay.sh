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
#   可用名：census-redye timeout-cut degrade-cut reduce-sidebar roving-cut fitts-shrink
#           dialog-reduce-cut portal-dup-enqueue
#           b7-after-cut b7-hollow-pulse b7-fake-settle b7-gate-cut（批七编队投影）
#           b8-gate-cut b8-after-cut b8-order-cut b8-withheld-cut（批八 teams 实体）
#           s1-face-cut s1-zero-cut（批 0 切片 1：编队行可见面/时长零值豁口）
#           s1-a11y-cut（PR#34 a11y：非敏感行零焦点停点无回归面）
#           s3-seg-cut s3-fold-cut（切片 3：段头渲染/中段默认折叠）
# 约 5-6 分钟/处（build+整套 craft e2e）；portal-dup-enqueue 跑 m10 套件较快；
# b7-* 跑 batch_g 套件（~3 分钟/处）。
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
    *batch_g*) echo 'BATCH-G SQUAD ALL GREEN' ;;
    *batch_h*) echo 'BATCH-H TEAMS ALL GREEN' ;;
    *) echo 'CRAFT DESKTOP ALL GREEN' ;;
  esac
}

failsum_of() { # 套件各自的 FAILED 汇总行（须真到达汇总，中途崩不算干净咬合）
  case "$1" in
    *m10*) echo 'M10 ACCEPTANCE FAILED' ;;
    *batch_g*) echo 'BATCH-G SQUAD FAILED' ;;
    *batch_h*) echo 'BATCH-H TEAMS FAILED' ;;
    *) echo 'CRAFT DESKTOP FAILED' ;;
  esac
}

baseline() { # $1=套件；clean HEAD 必须全绿——否则既有红会被误归因成 tamper 咬合
  echo "== baseline: $1 =="
  # build 显式包住（Codex R1 审 P3）：set -e 下裸 build 失败会绕过 BASELINE-RED
  # 分支，只留一个无法归因的裸 exit 1。
  if ! (cd "$WT/frontend" && npm run build >/dev/null 2>&1); then
    echo "BASELINE-RED: ${1} —— build 失败（node_modules 缺失或构建错误）"
    exit 1
  fi
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
BATCHG=frontend/e2e/batch_g_squad_acceptance.py
BATCHH=frontend/e2e/batch_h_teams_acceptance.py

# macOS 自带 bash 3.2 无关联数组——case 查表零依赖。
# EXPECT 消歧纪律：'FAIL ⑩' 是 ⑩ 与 ⑩' 两行共同前缀，⑩' 独立 flake 会误报
# BITE-OK（3-lens oracle 审 P2）——一律长前缀/直嵌 prime 字符锚死。
suite_of() {
  case "$1" in
    portal-dup-enqueue) echo "$M10" ;;
    b7-*) echo "$BATCHG" ;;
    b8-*) echo "$BATCHH" ;;
    s1-face-cut) echo "$BATCHG" ;;
    s1-a11y-cut) echo "$BATCHG" ;;
    s3-seg-cut) echo "$BATCHG" ;;
    s3-fold-cut) echo "$BATCHG" ;;
    *) echo "$CRAFT" ;;
  esac
}

expect_of() {
  case "$1" in
    census-redye)       echo 'FAIL ⑭C3' ;;
    timeout-cut)        echo 'FAIL ⑭C1' ;;
    degrade-cut)        echo 'FAIL ⑭C2 ' ;;
    reduce-sidebar)     echo 'FAIL ⑭C4 ' ;;
    roving-cut)         echo 'FAIL ⑭C6″' ;;
    fitts-shrink)       echo 'FAIL ⑮ ' ;;
    dialog-reduce-cut)  echo 'FAIL ⑭C4′' ;;
    portal-dup-enqueue) echo 'FAIL ⑩入队' ;;
    b7-after-cut)       echo 'FAIL O1c' ;;
    b7-hollow-pulse)    echo 'FAIL O2a' ;;
    b7-fake-settle)     echo 'FAIL O7e' ;;
    b7-gate-cut)        echo 'FAIL O4a' ;;
    # b8：O4a=版本漂移是 summon gate 独有校验（batch 复检面只盖 在场/下线/
    # interactive）——gate 砍除后确定性放行 200。长前缀锚死消歧。
    b8-gate-cut)        echo 'FAIL O4a 0.x-minor' ;;
    b8-after-cut)       echo 'FAIL O3b 乱序提交依赖边仍正确' ;;
    b8-order-cut)       echo 'FAIL O4b patch 漂移放行' ;;
    b8-withheld-cut)    echo 'FAIL O6c 依据段遮蔽标记在场' ;;
    # 批 0 切片 1：长前缀锚死（S1a 与 S1b/S1c 不互为前缀；⑰S1 独立编号无串号面）。
    s1-face-cut)        echo 'FAIL S1a' ;;
    s1-zero-cut)        echo 'FAIL ⑰S1' ;;
    s1-a11y-cut)        echo 'FAIL S1g' ;;
    s3-seg-cut)         echo 'FAIL S3a' ;;
    s3-fold-cut)        echo 'FAIL S3a' ;;
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
    # 批五 T2 超时撤除（Codex R2 审 P2 恢复）：⑭C2 重试点击已限时包 try（红而
    # 不崩），套件在此 tamper 下也能达 FAILED 汇总，满足干净咬合三条件。
    timeout-cut) cat <<'PY'
p="frontend/src/api/client.js"; s=open(p).read()
t="setTimeout(() => controller.abort(), timeoutMs)"; assert t in s
open(p,"w").write(s.replace(t,"setTimeout(() => {}, timeoutMs)"))
PY
      ;;
    # 批五 T3 降级条阉割（新增，非替换——Codex R2 审裁定 degrade-cut 可新增
    # 不可静默替换 timeout-cut）。
    degrade-cut) cat <<'PY'
p="frontend/src/components/QuickSwitcher.vue"; s=open(p).read()
t="fetchDegraded.value = failed > 0;"; assert t in s
open(p,"w").write(s.replace(t,"fetchDegraded.value = false;"))
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
    # ── 批七编队投影（本轮执行会话已逐处实证咬合，此处登记为可复跑证据）──
    b7-after-cut) cat <<'PY'
p="backend/app/api/tasks.py"; s=open(p).read()
t="                deps = [task_ids[d] for d in item.after]\n                repos.create_task("
assert t in s
open(p,"w").write(s.replace(t,"                deps = []\n                repos.create_task("))
PY
      ;;
    b7-hollow-pulse) cat <<'PY'
p="frontend/src/views/GuidePage.vue"; s=open(p).read()
t="'is-pulsing': agentTaskInfo(a) && isWorkState(agentTaskInfo(a).latest.status),"
assert s.count(t)==1
open(p,"w").write(s.replace(t,"'is-pulsing': agentTaskInfo(a) && (isWorkState(agentTaskInfo(a).latest.status) || memberPhaseOf(a) === 'waiting_upstream'),"))
PY
      ;;
    b7-fake-settle) cat <<'PY'
p="frontend/src/utils/squad.js"; s=open(p).read()
t="if (counts.settled === true && counts.waitingReview === 0) {"
assert s.count(t)==1
open(p,"w").write(s.replace(t,"if (counts.completed > 0) {"))
PY
      ;;
    b7-gate-cut) cat <<'PY'
p="backend/app/api/classification_gate.py"; s=open(p).read()
t="""    allowed = (
        _CLEARANCE_RANK.get(material_level, 2)
        <= _CLEARANCE_RANK.get(agent_max, 0)
    )"""
assert t in s
open(p,"w").write(s.replace(t,"    allowed = True"))
PY
      ;;
    # ── 批八 teams 实体（e2e 头部契约声明的四处投毒，登记为可复跑证据）──
    # gate-cut：只砍 G1-G4 收集后的 raise（G5 的 raise 同文——以后随注释锚死
    # 唯一性），块内局部替换 if errors: → if errors and False:。
    b8-gate-cut) cat <<'PY'
p="backend/app/api/teams.py"; s=open(p).read()
t='''        if errors:
            raise HTTPException(
                status_code=422,
                detail={"message": "召集未发起（对账不过，整单拒发）", "summon_errors": errors},
            )

        # seq 升序重排'''
assert s.count(t)==1
open(p,"w").write(s.replace(t,t.replace("if errors:","if errors and False:",1)))
PY
      ;;
    b8-after-cut) cat <<'PY'
p="backend/app/api/teams.py"; s=open(p).read()
t='                        after=[pos_of_seq[d] for d in m["after"] if d in pos_of_seq],'
assert s.count(t)==1
open(p,"w").write(s.replace(t,"                        after=[],"))
PY
      ;;
    b8-order-cut) cat <<'PY'
p="backend/app/api/teams.py"; s=open(p).read()
t="        ordered_seqs = sorted(member_by_seq)"
assert s.count(t)==1
open(p,"w").write(s.replace(t,"        ordered_seqs = [it.seq for it in body.items]"))
PY
      ;;
    b8-withheld-cut) cat <<'PY'
p="frontend/src/stores/taskEvidence.js"; s=open(p).read()
t=r'''      entry.withheld = (files || []).some(
        (f) => /\.json$/i.test(f.filename || "") && f.data_classification !== "internal"
      );'''
assert s.count(t)==1
open(p,"w").write(s.replace(t,"      entry.withheld = false;"))
PY
      ;;
    # ── 批 0 切片 1（P0-1/时长零值豁口）──
    # face-cut：可见面编队行类名改死 → S1 探针整组红（状态回退进隐藏面）。
    s1-face-cut) cat <<'PY'
p="frontend/src/views/GuidePage.vue"; s=open(p).read()
t='class="sa-squad-line sa-squad-face"'; assert s.count(t)==1
open(p,"w").write(s.replace(t,'class="sa-squad-line sa-squad-face-cut-x"'))
PY
      ;;
    # zero-cut：时长零值豁口恒假 → 「0 秒」回屏，⑰S1 必咬。
    s1-zero-cut) cat <<'PY'
p="frontend/src/components/WorkLog.vue"; s=open(p).read()
t="const durZero = elapsedMs.value !== null && elapsedMs.value < 1000;"; assert s.count(t)==1
open(p,"w").write(s.replace(t,"const durZero = false;"))
PY
      ;;
    # ── 切片 3 ──
    # seg-cut：段头整体不渲染 → fold 行消失，S3a 必咬。
    s3-seg-cut) cat <<'PY'
p="frontend/src/views/GuidePage.vue"; s=open(p).read()
t='<div v-if="segStartOf(idx) && segStartOf(idx).ordinal > 0" class="seg-head">'; assert s.count(t)==1
open(p,"w").write(s.replace(t,'<div v-if="false" class="seg-head">'))
PY
      ;;
    # fold-cut：中段默认折叠恒假 → 中段泡常显，S3a 必咬。
    s3-fold-cut) cat <<'PY'
p="frontend/src/views/GuidePage.vue"; s=open(p).read()
t="return isMiddleOrdinal(ordinal) && !unfoldedSegments.value.has(ordinal);"; assert s.count(t)==1
open(p,"w").write(s.replace(t,"return false;"))
PY
      ;;
    # a11y-cut：敏感条件 tabindex 改无条件 → 非敏感行也长焦点停点，S1g 必咬。
    s1-a11y-cut) cat <<'PY'
p="frontend/src/views/GuidePage.vue"; s=open(p).read()
t=':tabindex="clearanceOf(a) === \'sensitive\' ? 0 : undefined"'; assert s.count(t)==1
open(p,"w").write(s.replace(t,':tabindex="0"'))
PY
      ;;
  esac
}

ALL="census-redye timeout-cut degrade-cut reduce-sidebar roving-cut fitts-shrink dialog-reduce-cut portal-dup-enqueue b7-after-cut b7-hollow-pulse b7-fake-settle b7-gate-cut b8-gate-cut b8-after-cut b8-order-cut b8-withheld-cut s1-face-cut s1-zero-cut s1-a11y-cut s3-seg-cut s3-fold-cut"
NAMES="${*:-$ALL}"

# 先验名合法性 + 汇总用到的套件，各跑一次 clean baseline（全绿才准开咬）。
NEED_CRAFT=0
NEED_M10=0
NEED_BATCHG=0
NEED_BATCHH=0
for n in $NAMES; do
  [ -n "$(expect_of "$n")" ] || { echo "未知 replay 名：${n}（可用：${ALL}）"; exit 2; }
  case "$(suite_of "$n")" in
    *m10*) NEED_M10=1 ;;
    *batch_g*) NEED_BATCHG=1 ;;
    *batch_h*) NEED_BATCHH=1 ;;
    *) NEED_CRAFT=1 ;;
  esac
done
if [ "$NEED_CRAFT" -eq 1 ]; then baseline "$CRAFT"; fi
if [ "$NEED_M10" -eq 1 ]; then baseline "$M10"; fi
if [ "$NEED_BATCHG" -eq 1 ]; then baseline "$BATCHG"; fi
if [ "$NEED_BATCHH" -eq 1 ]; then baseline "$BATCHH"; fi

COUNT=0
for n in $NAMES; do
  replay "$n" "$(suite_of "$n")" "$(expect_of "$n")" "$(patch_of "$n")"
  COUNT=$((COUNT + 1))
done
echo "REPLAY ALL BITES OK（$COUNT 处全部预期红命中，基线先行全绿）"
