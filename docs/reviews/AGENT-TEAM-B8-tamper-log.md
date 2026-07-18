# 批八 teams 实体 tamper 咬合日志（AGENT-TEAM-B8）

> 执行会话投毒实录（2026-07-18，工作树 flai-os-inline-wt，基线 commit c11accc）。
> 可复跑版本已登记 `scripts/tamper_replay.sh`（b8-gate-cut / b8-after-cut /
> b8-order-cut / b8-withheld-cut，三条件干净咬合契约同批六：非零退出码 +
> 精确预期 FAIL 行 + 正常到达 FAILED 汇总）。被测套件 =
> `frontend/e2e/batch_h_teams_acceptance.py`（clean 基线 26/26 绿先行）。

## TB1 · summon 对账 G1-G4 判定短路（b8-gate-cut）

- 投毒：`backend/app/api/teams.py` G1-G4 收集后的 `if errors:` raise →
  `if errors and False:`（G5 的 raise 同文——以 patch 内后随注释「# seq 升序
  重排」锚死唯一性，块内局部替换）。
- 预期红的选择依据：run_batch_creation 复检面盖 在场/下线/interactive，
  **不盖版本漂移**——gate 砍除后 O4a（0.x-minor 漂移应 422）确定性放行 200。
- 实测：`FAIL O4a 0.x-minor 漂移→422 指名`，RC=1，达 FAILED 汇总 ✅ 咬合。

## TB2 · after→依赖边映射断开（b8-after-cut）

- 投毒：summon 映射 `after=[pos_of_seq[d] for d in m["after"] if d in pos_of_seq]`
  → `after=[]`。
- 预期：O3b（乱序提交依赖边仍正确）必红；UI 链 O3d/O3e 连锁红。
- 实测：`FAIL O3b 乱序提交依赖边仍正确`，RC=1，达 FAILED 汇总 ✅ 咬合。
- 附注：e2e 的 ui_down 匹配带 default None（依赖边缺失 → O3d/O3e 红而不崩），
  这是本 tamper 能干净到达 FAILED 汇总的前提（批六㊲/批七 TB1 同款教训，
  本批在 S4 落套件时先行加固，独立重放一次过）。

## TB3 · seq 升序重排改直译提交序（b8-order-cut）

- 投毒：`ordered_seqs = sorted(member_by_seq)` → `[it.seq for it in body.items]`
  （auditor F3 契约拆除：信任客户端提交序）。
- 预期：O3b 的逆 seq 序提交下，下游成员先入列 → after 映射成前向引用 →
  batch 静态校验 422 → 同一响应上的 O4b（patch 漂移放行 200+warnings）先红。
- 实测：`FAIL O4b patch 漂移放行`，RC=1，达 FAILED 汇总 ✅ 咬合。
- 附注：UI 面板按 seq 升序提交，直译序恰与升序重合——UI 路径不受此毒影响，
  咬合完全由 API 逆序探针提供（这正是 O3b 设计逆序提交的原因）。

## TB4 · withheld 判据拆除（b8-withheld-cut）

- 投毒：`frontend/src/stores/taskEvidence.js`
  `entry.withheld = (files || []).some(受限 JSON 判据)` → `entry.withheld = false;`。
- 预期：O6c（TaskDetail 依据段「按密级隐藏」遮蔽标记在场）必红；O6a（零受限
  下载）与 O6d（无编造计数）不受影响仍绿——单点干净咬合。
- 实测：`FAIL O6c 依据段遮蔽标记在场`，RC=1，达 FAILED 汇总 ✅ 咬合。

## 独立重放（基 HEAD worktree）

- 2026-07-18，基线 c11accc：`bash scripts/tamper_replay.sh b8-gate-cut
  b8-after-cut b8-order-cut b8-withheld-cut` → **BITE-OK 4/4，REPLAY-EXIT=0**，
  基线先行 26/26 全绿（日志：BASELINE-GREEN + REPLAY ALL BITES OK）。
- 同日全量 gate：`bash scripts/verify_all.sh` EXIT=0（1054 pytest + 19 e2e
  套件含 batch_h，失败（无））。
- Codex R0 修复轮后（基线 240c378，含 SchemaForm 面板重构 + material_errors
  分流 + after= 行缩进变化）：4 case 复放 **BITE-OK 4/4，REPLAY-EXIT=0**——
  b8-after-cut 锚点已随 try 块缩进同步，b8-gate-cut 在 material_errors 独立
  列表下咬合不变（gate errors 死变量不混流）。同轮 verify_all EXIT=0
  （1057 pytest）。
