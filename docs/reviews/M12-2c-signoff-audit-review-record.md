# M12-2c 治理签发审计（review_task 落 audit.log）· 审查档案

> 延续 M12-2（ADR-0023）审计轴。M12-2 审计了登录/登出/敏感下载 403，**漏了平台
> 最安全承重的动作**：人工放行/拒绝任务（review_task）——「人是唯一签发者」红线的
> 落点。此前该签发只落应用层 task_event（可随业务库改写），无篡改抗性的 audit.log 轨。

## 一、改动（三文件，disjoint 于 hold 分支的 monitor 内容门区域）

1. **logging_setup.py**：`_AUDIT_ALLOWED_FIELDS` 增 `task_id`/`created_by`/`self_review`
   三字段（皆 opaque/非 secret/非 per-request 自由文本，可安全入白名单）。
2. **api/tasks.py**：`review_task` 在状态转移**真正 commit 之后**（IllegalTransitionError
   已在前面转 409，此处签发已生效）发 `audit_event("task_review", actor=<签发者唯一
   username>, outcome=approved|rejected, task_id, created_by, self_review)`。
3. **tests/test_logging_audit.py**：+2 witness（批准=self_review True / 非创建者拒绝=
   self_review False + reject comment 自由文本**绝不入 audit.log**）。

## 二、诚实边界（刻意不越权）

- **self_review 是可见性提示，非强制门**：基于 `display_name` 比对（tasks.created_by
  存的是创建者显示名，非 username；显示名非唯一）。**不做禁自审 403**——硬性职责分离
  需先补 `created_by_username` 身份列 + owner 定策略（角色轴，task #17 递延）。本轮只
  给「谁签发了谁创建的任务 + 近似自审标记」的**审计可见性**，把强制留给 owner。
- 与 M12-4「reviewer≠creator」的关系：本轮兑现其**可见性**子集（审计留痕），不兑现
  **强制**子集（禁自审=改签发工作流语义，需 owner 拍是否允许单人操作者自审）。

## 三、自证

- **8 audit 测试全绿**（6 既有 + 2 新签发）；全量 **619 passed** 零回归。
- **tamper 咬合**：把 review_task 的 audit_event 调用换 no-op → 两条签发审计测试
  立即 RED；复原全绿。证审计发射是被测的真行为，非假信心。
- **自由文本隔离 witness**：reject 传 `comment="不合格-secret-xyz"` → 断言该串**不在**
  audit.log（comment 非白名单被 drop）——证白名单机制挡住经审计路径的自由文本回流。

## 四、Codex 异源治理审（86gs gpt-5.6-sol ultra）

触发＝「命中即审」安全边界：改动触及**审计安全控制（字段白名单）+ 授权签发端点**。

**R0 = APPROVE，0 finding**（86gs gpt-5.6-sol ultra，定向 exec 审干净暂存 diff，
避开无关 PNG 噪声）。审方逐条独立确认：
1. 白名单安全：task_id=服务端生成、self_review=强制 bool、created_by 来自认证账户
   而非 review 请求体；json.dumps 防 CR/LF 日志注入。
2. reject 的 `comment` 未传给 audit_event → 不入审计；即便未来误传也因不在白名单被 drop。
3. self_review 非强身份判定、明确标注基于非唯一 display_name 的近似提示、未参与授权/
   403 强制门 → 不构成放行绕过。
4. actor=会话唯一 username；outcome 与 Literal["approve","reject"] 正确映射 approved/rejected。
5. set_task_status 返回前显式 COMMIT、失败回滚抛出 → 审计只在成功迁移后发射，绝不记
   未生效/并发失败的签发。

未发现可利用的 fail-open / 异常吞没 / review_task 行为回归。`git diff --cached --check`
通过。（审方只读环境未跑 pytest；本地 619 passed + tamper 咬合已由主控自证。）

## 五、reconcile 提示

本轮改 api/tasks.py 的 `review_task` 函数 + 顶部 import `audit_event`；hold 分支
（monitor-taint）改的是 tasks.py 的**详情端点内容门**（list_task_tool_runs 等）+ import
`_task_data_classification`——两处函数/import 行不同，hold 分支合流时预期可自动合并，
仅需确认两条 import 并存。
