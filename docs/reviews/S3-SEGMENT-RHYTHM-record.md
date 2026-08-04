# 切片 3 实施记录：长会话阅读节奏（方案 B，wayfinder #31）

> 基线：origin/main @ d354079（含 PR #24/#34 待合并面）· 分支 `qw/segment-rhythm-v1`
> owner 比选（#27 prototype）：方案 B = 工作段分隔 + 时间戳降噪 + 历史段折叠。
> 证据：`docs/reviews/craft-shots/s3-*.png`（before/after × 亮暗 × 1440/375/reduce）。

## 改动面

1. **段界纯函数** `workSegments`（conversationPlans.js）：与附件路由
   `currentWorkSegmentFiles` 共用 `terminalKindOf`（refuse/qa 三终点同源谓词），
   任务创建戳投影规则同附件路由（createdAt 严格大于边界戳开新段；缺时序保守跳过）。
   视觉分段与附件归属永不漂移。node 单测 8 组（frontend/tests/work_segments_ui.test.mjs）。
2. **GuidePage 模板**：消息循环改 template 包裹；段头（ordinal>0）= 中段默认折
   「▸ N 轮往来 · 工作段 K（HH:MM）」button（单向展开，display 语义保留 DOM）/
   当前段与展开段=发丝线分隔小字；首段不抬头。bubble-row 增 `seg-folded` 条件类。
3. **时间戳降噪**：段界消息 `.bubble-time.is-boundary` 常显，其余保持 hover-only
  （现状本就 hover-only，本切片补的是段界常显锚）。
4. **折叠态**：`unfoldedSegments` ref(Set)，换会话在既有串行导航事务里清零
   （禁裸 watch route.query.c——源码护网断言）。
5. **豁免红线（#25）**：首段/当前段永不折；首条 .user-bubble、最新 .plan-card/.ai-body、
   待核条不折；guide_batch_integrity 字面注释切片边界未动。

## 探针与 tamper

- batch_g S3a–S3d：中段默认折（fold 行含轮往来、中段泡在 DOM 不可见）/ 单向展开后
  可见+分隔线在场 / 段界时间戳常显且非段界 hover-only / 首段当前段豁免。
- 造段手法如实留痕：同 agent 二次开工被 `planHasTasks` 拦是产品语义，不硬造；
  第二边界用 guide 级 refuse 终点（stub 增「超出已审定」分支，_validate_refuse
  三必填字段齐备——reason/residual_problems/reframe 缺一即被 _ClarificationNeeded
  作废，此为诚实拒绝纪律的免费见证）。
- tamper：`s3-seg-cut`（段头不渲染）/`s3-fold-cut`（默认折叠恒假），预期红 FAIL S3a。

## 验证

- node --test 239/239（+8 新）；batch_g 52/52；craft 121/121；
  隔离副本 verify_all EXIT=0（见提交后回执）。
- bundle 预算不变（主入口 gzip ≈135.1KB）。

## 施工踩坑留痕

- 隔离副本 rsync 会把产品树陈旧 dist 盖掉副本新构建——manifest 指向旧 chunk 致
  「假阴性/假阳性」；e2e 复跑前必须确认 dist 与源码同代（本会话一次返工根因）。
- `.open-plan-btn` first 会误点已开工卡的「进入协作工作台」导航离页——按名字点
  「按方案开工」。

## retro 队列

- 首段过长（>10 轮）时是否也允许折叠（当前豁免）——观察项。
- 折叠行是否补「展开后自动滚到段首」——观察项。
