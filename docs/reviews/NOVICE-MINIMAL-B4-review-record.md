# 批次四评审档案：新人极简批（Q1-Q5）

> 契约：`docs/design/UI-DESKTOP-CRAFT.md` §十一-§十三。范本=ChatGPT.app ×
> Claude Desktop 语法（不换皮）。grounding=六路只读扫描（Workflow b4-ground-sweep，
> 6 agent 全回：位点/锚点/风险穷举）+ 主控亲读全部改动文件。
> 治理链：craft 探针扩批 → tamper → 3-lens → Codex 治理审（native Pro
> sol-ultra，cap 3）→ 过审合并 push（standing 授权）。

## 一、改动面

| 文件 | 项 | 内容 |
|---|---|---|
| `utils/format.js` | Q1 | `taskDisplayName(task, agentNames)` 三级诚实降级 SSOT（任务名→注册表显示名→id 切片；空任务/缺 id=「—」） |
| `stores/agentNames.js`（新） | Q1 | 模块级名册懒加载单例：一次 `listAgents()`，失败静默 map 空 → 消费方回退 id 切片，绝不编名字；inflight 防抖可重试 |
| `StatusCenter.vue` | Q1/Q2/Q3 | peek 标题+三组行主名走 SSOT；待签组头零计数豁口；脚注压缩为「口径：最近 100 条任务窗口，窗口外不虚报。」 |
| `TodayPage.vue` | Q1/Q2/Q3 | 行主名×2；三组头零计数豁口；Agent 动态双空态合并一行；团队总量零值格不渲染（`data-stat` 语义锚+全 0 收一行）+「按仓内固化文件计」降 title；`today-subhead-note` 退役（口径只留页脚一行） |
| `MePage.vue` | Q1/Q2/Q3 | 行主名走 SSOT（原裸 agent_id）；四格 tile 零值不渲染（`data-stat`，未加载保「—」四格）；反馈 0 条收一行空态（近似口径注只随计数出现，全文进 title）；团队总量行零值项不渲染；诚实缺口条压一行（「人是唯一签发者」保留） |
| `TaskConsole.vue` | Q1/Q2 | 左栏两处行主名走 SSOT；「最近任务」零计数豁口；全句诚实脚注保留（m8 锚面） |
| `DeliveryCard.vue` | Q1 | 主名走 SSOT；根节点加 `data-task-id`（e2e 定位改走属性，不再依赖裸 id 字面） |
| `WorkbenchSession.vue` | Q1 | roster 内/外两处 chip 主名统一走 SSOT（原两处 fallback 语义不对称）；`.chip-name` 补 ellipsis 截断 |
| `QuickSwitcher.vue` | Q1 | 任务标题走 SSOT，映射来自面板自有 agents 拉取（零新增网络调用） |
| `StatusDock.vue` | Q1 | 签发提醒 toast 称呼走 SSOT（原 fallback 全量裸 id） |
| `AgentPortal.vue` | Q4 | 页头图例句撤下（释义已全在徽章 title，L0「勿依赖其结论」在 maturityTip）；cat-bar 退役；类型/成熟度/id·版本合并一行次级 meta（id 字面保持可见 DOM——m10 has_text 锚）；「不适用范围」披露与 CTA 不动 |
| `WorkLog.vue` | Q5 | 聚合 mono 计数行（rawLine）删除——原始 token 的检视面=展开态时间轴逐条 `.event-type-raw`（信息不减，重复形态减一）；折叠态=人话扫读面 |
| `GuidePage.vue` | Q3 | plan-note 政策段两句压一行（红线字面「亲手提交」「签发权」逐字保留，m6 ③ 锚） |

e2e 原子同批：
- `m2_acceptance.py` ④/附加批准断言加 WorkLog 展开守卫（幂等：已展开不点）
- `batch_b_today_acceptance.py` ②④ 交付卡定位改 `data-task-id`；③ 位置对表重写为语义对表（API>0 ⇒ 恰 1 格逐字相等；==0 ⇒ 格不渲染——比旧断言多验零值分支）
- `batch_c_rewards_acceptance.py` ③ `.me-stat:last-child` → `[data-stat="total_created"]`（位置定位失义）
- `m10_governance_acceptance.py` 注释校正（定位命中 `.sc-item-sub` 裸 agent_id，不受主名影响）
- `craft_desktop_acceptance.py`：③ 冷态块重写（空态行数 3+动态团队分支/文案 4 段/零计数组头/团队零值格语义对表/口径唯一）；② num-token 探针迁 ⑩c（冷态无实例）；新增 ⑪a-⑪f（/me 四格+反馈零值、行主名人话、名册缺位诚实回退 route-abort 实证、名册恢复对照+非零计数不误伤、门户最小化+L0 title 诚实提示、折叠无 token/展开有 token）
- `tests/format_display.test.mjs`：+2 块（taskDisplayName 三级降级/空值象限），node 18→20

## 二、验证证据

- 前端 build 绿（改动后首验）；node 单测 **20/20**（18→20，+taskDisplayName 两块）。
- craft 套件 **81/81 ALL GREEN**（65→81，⑪a-⑪f + ③ 重写 + ② 迁移一次通过）。
- 受影响套件逐一单跑全绿：m2 **9/9** · m6 **14/14** · batch_b **10/10** ·
  batch_c **13/13** · m8_workbench **11/11** · m10 **12/12**。
- `verify_all.sh` 全量 **EXIT=0**：**989 pytest** + node 20 + **17 套 e2e ALL
  GREEN**（含未单跑的 m8_collab 7/7、m8_orchestrator 4/4、m9 9/9、m11 5/5、
  cfd_flow 7/7、batch_a 7/7、batch_d 13/13、eval×2、inline_summon 14/14）。
- 3-lens 修复批后复验：build 绿 + craft **81/81**（⑪Q3/⑪Q4 断言随修升级）+
  m6 **14/14**（plan-note 新句）；**终树 verify_all 再全量 EXIT=0**（989 pytest
  + 17 套失败无）——两次全量夹住 3-lens 修复，中间态不背书。
- 新截图：`craft-shots/statuscenter_human_names_light.png`（行级人话称呼）、
  `craft-shots/worklog_collapsed_human_light.png`（折叠态无 token）；
  `today_empty_light.png` 随 ③ 重写重截。
- tamper 战役（6 处，cp 备份+cmp 校验还原，每处 craft 全跑）：

| # | 破坏 | 期望咬合探针 | 结果 |
|---|---|---|---|
| T1 | 状态中心行名回种裸 id（×3 处） | ⑪Q1 行主名=显示名 | ✅ 恰 1 红（证据：行显 task_db07e14…） |
| T2 | 名册缺位时编造「Agent xxx」名 | ⑪Q1 诚实回退 id 切片 | ✅ 恰 1 红（证据：行显「Agent hello_agent」被逮） |
| T3 | 今日页待签组头恒拼「· N」 | ③ 零值组头无「· 0」 | ✅ 恰 1 红（证据：「✍ 待你签发 · 0」） |
| T4 | 团队总量零值格恒渲染 | ③ 零值格语义对表 | ✅ 恰 1 红（api=0 ui=shown ×3 被逮；冷库 curated=31 两分支实证） |
| T5 | 折叠态泄漏原始 token 行 | ⑪Q5 折叠态无 token | ✅ 恰 1 红 |
| T6 | 门户图例句回种 | ⑪Q4 图例撤下 | ✅ 恰 1 红 |

六轮全部**恰 1 红零旁伤**，还原逐一 cmp 校验，尾部 rebuild 复位。
**战役血训（已修正后取证）**：e2e 打的是 FastAPI 托管的 dist 静态产物——
tamper 改 src 不 rebuild = 六轮测同一个干净 bundle 全绿（首轮战役作废重跑）。
tamper 的生效路径必须亲证：破坏必须真实进入被测制品。

## 三、3-lens 对抗审（sonnet·high ×3：可用性/红线诚实/回归——11 findings 全裁决）

**采纳并修（6）**：
1. **[回归 P2·high] Agent 动态重构把「今日最活跃」误嵌 promotionsError 的
   v-else 连坐隐藏**（真回归，晋升 API 出错时本应独立可见的本地活跃数据被藏）
   → 活跃块拆出错误分支独立渲染；合并空态仅在「无错且双空」收敛。
2. **[可用性 P2·high] 同 Agent 多缺名任务行文本逐字相同，契约承诺的「时钟」
   消歧未全面兑现** → TodayPage 两组 sub / TaskConsole 两组 sub /
   WorkbenchSession 两处 chip（新增 .chip-time）/ ⌘K 任务副行 全部补
   formatClockCompact 紧凑时钟（useTodayKey 响应式日界 SSOT）。
3. **[诚实 P2] 状态中心口径句压缩丢「计数与清单」双重范围声明** →
   补回「计数与清单均来自…」（craft ⑪Q3 断言字面原子同批改）。
4. **[诚实 P3] 零值过滤 `>0` 把「字段缺失/非数字」与「确为 0」混为一谈** →
   三处 computed 收紧为「仅 ===0 隐藏」，非数字保格显「—」（数据不可用≠0）。
5. **[诚实 P2] L0「勿依赖其结论」降为 title 后可发现性不足** → 徽章
   cursor:help + 虚线下划线 affordance；craft ⑪e 升级为 title 字面+help 光标双断言。
6. **[诚实 P3] plan-note 把「开工/放行」两动作混进「提交」一个动词** →
   「开工由你亲手提交，产物放行由你批准」（红线子串不动）。

**有据反采纳（3）**：
- 「待我跟进=0 应显示正向文案」——格级零隐藏与 StatusDock 待签 pill 零隐藏
  同律（corpus cd-bg-tasks-panel 语法）；今日页「待你签发」是页面主 CTA
  **版块**（版块恒在+插画空态），版块级与格级语法本就不同，不引入第三种形态。
- 「名册回退名加斜体/前缀区分来源」——注册表名就是「该 Agent 的一次运行」的
  诚实称呼，非冒充任务名；新视觉语法的噪音>收益，可区分性由 meta 时钟承担（已修）。
- 「rawLine 应移入而非删除」——聚合计数与头行「N 条事件」+展开逐条 raw 重复，
  裁决退役；spec §十二 Q5 措辞已对齐。

**接受留痕（2）**：otherTasks chip 在名册缺位极端态回退 id 切片（比旧 agent_id
更不可读但更诚实唯一，且属降级路径）；agentNames 失败重试=每消费面挂载一次
（有界、无轮询风暴），craft ⑪c 已实证诚实回退，重试频率上界未专项断言（retro 池）。

## 四、Codex 治理审

（回填）

## 五、反采纳与边界（本批不做的决定）

- **不换皮**：三明治深框/近单色是范本的品牌身份，FLAi-OS 暖白+clay 家族轴已裁决——复刻语法不复刻皮肤。
- **不翻双 Surface 案**：owner 现行裁决维持。
- **首跑三步卡与四意图卡重叠**（Q6 走查主候选）：OnboardingCard 是新手首跑批（N 系列）owner 驱动的刚交付物且可「不再显示」，合并/删减属方向裁决 → 交 owner，不在本批擅动。
- **签发面「批准即代表你背书」两处重复**（StatusCenter peek / TaskDetail）：签发上下文的诚实地板各自独立成立，不去重。
- **FeedbackPage 选择器前缀裸 id**：选择器场景「按 id 精确选中」是合理用途（检视面），保留。
- **WorkbenchSession sess-foot 政策行**：含红线字面且已是单行，不再压缩。
