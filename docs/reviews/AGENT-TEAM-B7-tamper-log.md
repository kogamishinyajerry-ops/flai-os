# 批七编队投影 tamper 咬合日志（AGENT-TEAM-B7）

> 执行会话逐处投毒实录（2026-07-17，工作树 flai-os-inline-wt）。可复跑版本已登记
> `scripts/tamper_replay.sh`（b7-after-cut / b7-hollow-pulse / b7-fake-settle /
> b7-gate-cut，三条件干净咬合契约同批六）。被测套件 =
> `frontend/e2e/batch_g_squad_acceptance.py`（clean 基线 42/42 绿先行）。

## TB1 · after→depends_on 映射断开（b7-after-cut）

- 投毒：`backend/app/api/tasks.py` batch 事务内 `deps = [task_ids[d] for d in item.after]` → `deps = []`。
- 预期：O1c（下游滞留 created 且 depends_on 映射为真 task_id）必红。
- 实测：`FAIL O1c … {"status": "created", "depends_on": []}` ✅ 咬合。
- 附注：首轮独立重放 BITE-MISS——断依赖后等待相整体缺失，O2 的 expect 直接崩、
  套件未达 FAILED 汇总（crash-type fail ≠ 干净咬合，批六㊲同款）。修复=O2 块
  try 探测红而不崩（commit「S4a′」），复放 BITE-OK。

## TB2 · 空心灯强加 is-pulsing（b7-hollow-pulse）

- 投毒：GuidePage 灯类绑定 `isWorkState(...)` → `|| memberPhaseOf(a) === 'waiting_upstream'`。
- 预期：O2a（空心灯无 is-pulsing）必红。
- 实测：`FAIL O2a 空心灯在场且无 is-pulsing`（伴随 O3 echoCount=0 连锁红）✅ 咬合。

## TB3 · 收束假绿强改「全部完成」（b7-fake-settle）

- 投毒：squad.js 收束判据 `settled === true && waitingReview === 0` → `completed > 0`，
  文案改「全部完成」。
- 预期：O7 族必红。
- 实测：`FAIL O7c/O7d/O7e/O7f` 四连红（待签相被冒充成全部完成，amber 段消失）✅ 咬合。

## TB4 · 密级 gate 判定短路（b7-gate-cut）

- 投毒：classification_gate.py `agent_clearance_allows` 的 rank 比较 → `allowed = True`。
- 预期：O4a（单建 400）/ O4b（batch 422 零写入）必红。
- 实测：`FAIL O4a …status queued`（sensitive 材料直通建成任务）+
  `FAIL O4b … status=200 delta=2`（整批落库）✅ 双路咬合。

## 独立重放（基 HEAD worktree）

- 批五/六存量 8 case：S3 新基线（6262d73）BITE-OK 8/8，基线先行全绿（O12 收口）。
- 批七 4 case：S4a′ 硬化后复放——结果见本文件同目录 review-record §Codex 前置。
