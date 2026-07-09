# M1 收口审查记录（可追溯存档）

> 目的：反方审查的**原始发现**必须落盘可独立核验，不能只剩实现方自撰的 ADR 总结
> （loop-auditor 收口审计 d4 维度提示）。本文件只记录、不改写：处置结果以
> ADR-0009 与 commit 为准。

## R1 反方审查（异构 subagent，2026-07-08，结论 CHANGES_REQUIRED）

| # | 级别 | 发现 | 处置 |
|---|------|------|------|
| 1 | P1 | `files.py` 上传 filename 未净化，`../../evil.txt` 实测可写 uploads 之外任意路径 | 修（净化+resolve 纵深防御+witness×3） |
| 2 | P1 | `POST /api/tasks` 响应含 `inputs`，实测违反 task.schema.json（additionalProperties:false） | 修（schema 补 `inputs`，ADR-0009-1） |
| 3 | P1 | 事件响应泄漏 sqlite 自增 `id`，实测违反 event.schema.json | 修（`_decode_event` 剔除，ADR-0009-2） |
| 4 | P2 | created→queued 与 queued→validating 两次迁移无对应事件 | 修（双态见证+docs/05 两处文档化原子例外） |
| 5 | P2 | JobRunner 无顶层兜底；`set_task_status` 读改写无事务，cancel 竞态可杀死轮询 | 修（BEGIN IMMEDIATE+双层兜底+竞态/通用异常两 witness） |
| 6 | P2 | 上传无大小限制，磁盘可撑爆 | 修（FLAI_MAX_UPLOAD_MB 默认 100，超限 413 清残留） |
| 7 | P2 | agent.schema.json 承诺「trial 及以上禁 TBD（Registry 校验）」但未落地 | 修（`_load_one` 校验+正反 witness） |
| 8 | P3 | 测试缺口×4（缺 agent_id 422 / 非法枚举 / 磁盘缺失下载 / 缺失 file 引用静默跳过） | 修（补测试；缺失引用改发 warning 事件） |

修复自证：施工方对 files.py / registry.py / runner.py 三处做 tamper 回退并单跑
对应测试确认变红后还原（其陈述）；主控亲验 160 绿+代码抽检+真进程冒烟 7/7。

## loop-auditor 收口审计（2026-07-09，10 维 scorecard 17/20）

结论：核心闭环证据扎实、160/160 账实对齐；**窄口径 BLOCK** 仅针对
「全部修复经 tamper 自证咬合」这一收口断言——两处宣称有咬合实无 witness：

1. `files.py` resolve 第二层为纵深防御，POSIX 上无自然触发路径，删掉它原测试
   仍全绿 → 后补「模拟净化层失效」独立 witness（test_api.py），ADR-0009-4
   措辞同步降级为诚实版。
2. `runner.py` 通用 `except Exception` 兜底分支零测试 → 后补 `_ExplodingRuntime`
   witness（test_job_runner.py）。

两项补齐后按其裁定转 APPROVE。结构性残差（V0.1 已声明范围收缩，不修）：
无 CI/测试结果签名机制，「全绿」防篡改依赖人工核验——TrustGate 类机制
按 ADR-0007/0008 明确不入 V0.1。

## 86gs 治理审（异源 Codex，命中即审：未受信外部输入解析）

结论见本文件后续追记或对应 commit message。
