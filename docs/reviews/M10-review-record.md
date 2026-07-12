# M10 治理闭环「样本→评测→晋升」对抗审记录

> 触发：owner「回到 FLAi-OS 核心开发，寻找下一个重大升级方向」→ AskUserQuestion
> 四选一拍板「样本→评测→晋升学习闭环」。设计契约=docs/adr/ADR-0018（R1）。

## 设计审（实现前，loop-auditor）

判定 **BLOCK** → D1-D6/D8 grounded 复核属实全采纳，修订为 ADR R1 后动工：

| # | Finding | 处置 |
|---|---------|------|
| D1 | 晋升条件1可空洞满足（1 个 happy-path case 即"有评测集"） | 条件1 增强：approved ≥3 且必含 status_is failed 失败路径 case |
| D2 | checks 无内容指纹——同版本号删/改软 checks 后旧全绿证据仍"匹配" | eval_runs.eval_cases_digest（approved 内容 sha256），晋升时重算比对，不一致=证据过期拒 |
| D3 | 未知 check kind 判定方向未声明 | 明文 fail-closed：未识别 kind/必填字段缺失 → case **failed**（非 skipped） |
| D4 | 晋升 5-way AND 门 3/5 conjunct 无负例 witness | 红线清单补齐条件1/3/4 负例 |
| D5 | worker 隔离（全文最重结构性承诺）无 witness | 补隔离三 witness：claim 不选 eval / eval 不落样 / 默认视图不含 eval |
| D6 | confirmations 非 bool 未单独点名（本仓 truthiness 事故同族） | 拆三具名负例：缺失/false/非 bool（"true"/1） |
| D7 | **FLAG**：正例固化把 approve「放行」升格为「逐字段金标准」 | **主控裁决采纳 draft-curation**：固化生成 curation=draft，不执行不计数单列，策展改 approved 才生效（fail-safe 膨胀方向，供 owner 复核） |
| D8 | 背景失准：registry 只查目录存在不查非空 | ADR 背景段修正+注明门内自判原因 |

## 实现分工（谁写另一方审）

- **主控亲写**：db.py（迁移#4 tasks.origin + eval_runs/promotions 表）、repos.py
  （claim origin 过滤/claim_task/eval_runs/promotions/get_sample）、runtime.py
  双落样点 origin 白名单、governance/{eval_runner,promotion,curation}.py、
  api/governance.py、六 agent case checks 块、hello 失败路径双 case、
  m10_governance_acceptance.py e2e、contracts/task.schema.json origin 演进。
- **Codex lane A（写，主控亲核）**：backend/tests/test_m10_governance.py（ADR 红线逐条）。
- **Codex lane B（写，主控亲核）**：AgentPortal 治理面板 + StatusCenter 固化入口。
- **Codex lane C（异源审）**：晋升门属安全 gate 家族，命中即审同步阻塞。

## Codex 异源审 R0（CHANGES_REQUIRED，17 findings）→ R1 处置

安全边界审同步阻塞。逐条 grounded 复核后分三类处置：

**立修（R1 批，主控亲写）**：
| # | Finding | 修复 |
|---|---------|------|
| P1-2 | 晋升重扫绕过 knowledge 对账（scope 违规 agent 被复活） | _rescan_with_reconcile 复刻装配序（reconcile 先于 sync） |
| P1-3 | yaml/registry/DB/审计非原子提交 | 补偿式回滚：原文内存持有，提交段异常恢复磁盘+重扫+校验 L1 落定 |
| P1-4 | 证据只绑 case 原文不绑被测对象 | digest 扩展=case+引用输入文件实体+包核心五文件 |
| P1-5 | 产物断言裸读 path 绕过完整性闸 | 三类 check 全走 open_verified_file（根圈定+sha256+拒 symlink）+task_id/kind 过滤 |
| P1-6 | 晋升 TOCTOU/并发双 L0 判定 | _PROMOTION_LOCK 全程持锁+锁内重读；后到者见 L1 被拒 |
| P2-7 | 坏配置炸穿 runner 留僵尸 running；eq 布尔==1 | 外层 try→status='error'；单 case 全包；gte/lte 期望非数值=配置错；eq 类型先拒 |
| P2-8 | curation 非精确 draft 一律当 approved（fail-open） | 三值严判，其余值→broken→failed |
| P2-9 | 固化编号/幂等并发竞争覆盖 | _CURATION_LOCK+open('x') 独占创建 |
| P2-10 | 同步 eval 无资源边界 | per-agent single-flight（EvalBusy→409）；配额/deadline 列限制 |
| P2-13 | 晋升不写 changelog 违反 docs/02 | 结构化条目与 yaml 同回滚域 |
| P3-14/15/16/17 | origin 白名单/claim_task 镜像条件/yaml 手术 newline 保真/FE 续体守卫/e2e ③ 平凡绿 | 全修 |

**判架构边界如实声明（ADR 已声明限制段明文）**：P1-1 磁盘直改 yaml=平台外域
（V0.1 无鉴权，能改 yaml 者亦能改门代码，防线=git 审查+部署包只读）；
P2-11 固化通道仅覆盖 requires_human_review 型（sample 级认可 API 递延）；
P2-12 origin 契约同仓同步演进（循 ADR-0016 先例）。

**Codex lane A 诚实报差 2 条已裁**：fixed_at 补实现；ADR 固化 checks 措辞改
artifact_exists（比自动编 eq 金标准更 grounded，与 D7 原则一致）。

## R1 复审（F1-F4）→ R2 终审（round cap 3 用尽）

R1 复审仍 CHANGES_REQUIRED（F1 scan 非原子发布 / F2 回滚三缺口 / F3 digest
未绑实际引用+执行窗 / F4 eval task 非终态孤儿），四条 grounded 复核全属实，
全修+5 条故障注入回归。R2 终审判 F4 RESOLVED、F1/F2/F3 residual：

- F2/F3 残余=机械补口，verbatim 例外直接落地：终点复核收进 fail-closed
  （rehash 抛错→run status='error' 非 500 僵尸）、F2 测试直查 agents 表、
  custom schema 共存形态测试（registry 钉死默认名在场、runtime 读配置名——
  改 custom 逃旧指纹的真实攻击形态被咬）、ADR 明文两处残余窗口。
- **F1 残余主控终裁与审方相左（双记录）**：adopt 三赋值+跨调用混合快照。
  grounded 复核：violator 在新旧两份 _agents 中均不存在（启动即注销、影子
  重扫同过对账），部分发布只可能 dict/dir 同键错配且路径恒同——R2 声称的
  P1 场景（违规复活）已被测试证伪，残余判 P3：发布序加固（_agents 收尾）+
  ADR 声明，快照句柄 API 进 V0.2 retro 队列。owner 若采审方判级可另启批次。

## 验证

- 后端 smoke 全链一次通；
- 全量 pytest **569/569**（530 存量+32 治理测+5 故障注入+2 R2 残余口）；
- m10 e2e **12/12**（含收紧后的 ③）；verify_all 九步门全绿（终跑见 log）；
- tamper 双伤实证（cp 备份法）：削 digest 比对→晋升测试红；削 claim origin
  过滤→worker 隔离测试红；还原双绿。

## 遗留

- P1-1 运行时 attestation 推导（registry 启动核对 promotions 记录）——递延判缓；
- sample 级认可 API（打开 requires_review=false 型固化通道）——V0.2；
- eval 异步队列+配额/deadline；跨进程锁；tool/model/scope 级 manifest——V0.2；
- L1→L2/L3（专家签字人工域）；反例固化人工定口径通道——V0.2。
