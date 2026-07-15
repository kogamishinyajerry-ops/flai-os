# ADR-0028:需求接件评估 Agent(家底感知 + 待办队列)

- 状态:Accepted
- 日期:2026-07-15
- 关联:docs/08 共建手册(需求模板/路由四问)· ADR-0017(fence 防注入与
  「语料外不作答」先例)· ADR-0024(工具污点声明)· 宪法第五/六/十条

## 背景

平台负责人在 2026-07 部门问卷分析中跑通了一套需求评估工作流:接需求 →
对照已有资产盘点 → 确定性工时账 + 覆盖判定 → 档期建议 → 留存待办。owner
裁决:这套工作流是平台缺失的「感官」——内网部署后同事持续提新需求,平台
必须自己接得住(评估),且评估结果要能被管理(不因搁置几天而遗忘)。

## 决策

1. **形态 = Agent Package(非平台核改动)**:`agents/requirement_intake_agent/`
   + `tools_impl/asset_catalog/`,`git diff backend/app` 为空——封板判据①
   证明的生长路径,路由四问第 3 问的正面答案。
2. **资产清单 SSOT = `data/assets/assets.yaml`**(新数据区):评估的家底感知
   数据源,status 五态(live/validated/demo/scaffold/planned)+ honest_note
   强制。**default-deny:清单外资产视为不存在**——宁可漏报被人工纠正,不可
   让 LLM 凭记忆编家底。清单由人维护,评估卡透出版期供核对新鲜度。
3. **三层分工**:确定性层(工时口径常量/安全处置线/关键词初筛/队列写入)全
   代码;模型层只写六节评估叙述草稿,且只能引用初筛候选集;裁决层=人
   (requires_human_review=true + 评估卡水印)。工时口径与 2026-07 问卷估算
   法同源,改口径=改语义,须升版本。
4. **待办队列 = `data/requirement_backlog/backlog.jsonl`**(新数据区,运行时
   生成不入库):append-only 事件流(assessed 由 Agent 写;status_change 由
   人经 `scripts/backlog_cli.py` 写,强制 `--by` 具名)。读取按行序 fold,
   状态机 assessed→queued→in_progress→delivered(parked/rejected 旁路)。
   选 JSONL 而非扩 SQLite 表:零内核改动、审计可回放、内网 Windows 可 grep;
   单 worker 轮询模型下 append 无并发写。若未来多 worker,此决策必须重议。
5. **fail-closed 双区分**:「清单不可读」→ 任务诚实 failed(绝不无家底盲评),
   「清单里没有」→ 零命中如实标注按需新建评估;安全等级缺失 → 按未定级=
   A 级纪律处置线。失败任务不落待办登记(半成品档案是队列污染)。

## 替代方案(否决理由)

- **MCP server / 外网侧 skill**:评估能力留在外网助手侧,内网平台无感官,
  不满足 owner 的部署诉求。
- **扩 Task Center 当队列**:需求生命周期(评估/排产/搁置/交付)≠任务生命
  周期(一次运行),硬塞会污染任务状态机十态不变量,且触平台核。
- **LLM 输出结构化 JSON 进队列**:把 GLM 的 JSON 可靠性押进关键路径;现设计
  结构化字段全部来自确定性代码,LLM 只产人读叙述,解析失败面为零。

## 影响与风险

- 评估质量上限=清单新鲜度:资产落地/状态跃迁不更新清单会漏判——运维纪律
  写入 assets.yaml 文件头与 Agent README;评估卡带版期供人肉核对。
- 关键词子串初筛召回有限(无中文分词依赖是刻意取舍):漏筛资产会被 LLM 层
  「只能引用候选集」纪律连带漏判——缓解:top_k=6 + keywords 由人按误漏case
  持续增补;语义检索升级留待内网 embedding 服务就绪后另议。
- 新增两个数据区(data/assets 入库、data/requirement_backlog 运行时生成),
  备份策略沿用 data/ 现行约定。
