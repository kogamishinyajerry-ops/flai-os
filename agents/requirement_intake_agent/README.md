# requirement_intake_agent —— 需求接件评估(家底感知 + 待办登记)

> 一句话:同事提新需求,平台对照资产清单评估「家底接不接得住」,产出评估卡草稿并登记待办队列;立项裁决永远在人。ADR-0028。

## 是什么 / 不是什么

| 是什么 | 不是什么 |
|---|---|
| docs/08「需求提交模板+路由四问」的软件化 | 自动立项系统(裁决在平台负责人) |
| 确定性工时账+资产初筛+LLM 评估叙述草稿 | 让 LLM 打分拍板(数字全部代码算) |
| 待办队列登记器(防"放两天就忘") | 项目管理系统(状态流转靠人用 CLI) |
| guide_agent 的互补(评估「要不要立新项」) | guide_agent 的替代(guide 分诊「用哪个已有 Agent」) |

## 数据流

```
需求单(input_schema,对齐 docs/08 模板)
  ↓
确定性账:工时估算(问卷口径)+ 安全处置线(A级/未定级→签批留人,fail-closed)
  ↓
asset_catalog 工具:data/assets/assets.yaml 确定性关键词初筛 top-6
  │   清单不可读 → 诚实 failed(绝不无家底盲评)
  ↓
LLM(profile=reasoning):六节评估叙述草稿
  │   只能引用 <<ASSETS>> 块内资产;fence + 中和防注入;空内容 → failed
  ↓
assessment_card.md(水印+确定性账+初筛表+AI 草稿)+ assessment.json
  ↓
data/requirement_backlog/backlog.jsonl 登记(按 rid 幂等)
  ↓
任务停 waiting_review —— 平台负责人签核 = 接件评估的人工裁决
```

## 待办队列怎么用

```bash
python scripts/backlog_cli.py list                 # 全部需求(状态/省时/龄期)
python scripts/backlog_cli.py list --status assessed
python scripts/backlog_cli.py show <rid>
python scripts/backlog_cli.py set-status <rid> queued --by 严冬杰 --note "排进2月档"
```

状态机:`assessed → queued / parked / rejected;queued → in_progress → delivered`。
队列文件是 append-only 事件流(assessed 行 + status_change 行),审计可回放;
`FLAI_REQ_BACKLOG_DIR` 环境变量可重定向目录(测试隔离用)。

## 维护要点

- **资产清单是评估质量的天花板**:新资产落地/状态跃迁必须更新
  `data/assets/assets.yaml`(status 如实,honest_note 写清不能说成什么),
  否则评估会漏判/误判。评估卡透出清单版期供人核对新鲜度。
- 工时口径常量(`_DURATION_HOURS/_FREQ_PER_YEAR/_REPLACE_RATIO`)与 2026-07
  部门问卷估算法同源;改口径=改评估语义,须升版本记 changelog。
- prompt.md 是行为契约:六节结构与五条铁律被评估卡消费,改动必升版本。

## 边界(与 agent.yaml limitations 一致)

评估卡是草稿非决定;清单外资产按不存在处理;缺 duration/frequency 不猜数;
A 级/未定级一律"辅助检索+草稿生成,签批留人";不自动排产不自动通知。
