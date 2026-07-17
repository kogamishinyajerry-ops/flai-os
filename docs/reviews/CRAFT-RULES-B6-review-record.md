# 批次六 craft 深化 · 评审记录

> 范围契约：docs/design/UI-DESKTOP-CRAFT.md §十五。基线 origin/main 7007445
> （批五收口）。验证链 = tamper 咬合（6/6，见 CRAFT-RULES-B6-tamper-log.md）
> → verify_all 全量门 → 3-lens 对抗审（sonnet ×3 只读）→ Codex 治理审
> （native 20x Pro，cap=3）→ 过审合并 push（常设授权）。

## 一 · 改动面

| 类 | 文件 | 内容 |
|---|---|---|
| 产品 | frontend/src/router/index.js | B6-2 roving focus：afterEach 页面真重挂（pageKey‖path）→ nextTick+rAF 焦点交 .app-main；首载跳过 |
| 产品 | frontend/src/App.vue | main tabindex="-1" + .app-main:focus outline 归零（程序化焦点不进 Tab 序） |
| 产品 | frontend/src/utils/format.js | B6-5 taskElapsedMs 诚实端锚：工作态集合才挂 now；waiting_review 无 finished_at → null |
| 产品 | frontend/src/views/TodayPage.vue | 注释对齐（待签行不显时长） |
| oracle | frontend/tests/format_elapsed.test.mjs | 新 4 例（waiting_review 例 pre-fix 红=oracle 先行） |
| oracle | frontend/e2e/craft_desktop_acceptance.py | +4：⑮ Fitts census / ⑯ dock 遮挡审计 / ⑮′ 上传分阶段活体 / ⑭C4′ 重设计（强加 enter-active 类）；⑭C6″/⑭C6‴ 断言有意识收紧（焦点必落 app-main） |
| oracle | frontend/e2e/m10_governance_acceptance.py | +2：⑩ 入队后轮询失败不诱导重复入队 / ⑩' 行内重试恢复 |
| 工装 | scripts/tamper_replay.sh | B6-6：隔离 worktree tamper 重放（批五 §八 retro 兑现），BITE-MISS 即 exit 1 |
| 规格 | docs/design/UI-DESKTOP-CRAFT.md | §十五（含反采纳留痕三则） |

## 二 · tamper 总账

6/6 咬合（TB3 两级：粗暴被上游兜死+温和达 ⑯；TB6 首跑揭穿 ⑭C4′ 稳态读数
假绿 → 探针重设计后必咬）。逐字存档：CRAFT-RULES-B6-tamper-log.md。

## 三 · 套件计数

- craft：108/108（复位绿位确认）
- m10：14/14（首过）
- node：29/29（含新 format_elapsed 4 例）
- verify_all：EXIT=0，`[失败]（无）`，全套 e2e 绿（含 craft 108/108 · m10 14/14
  · inline-summon 14/14 · batch A-D 等），tamper 轮复位后跑。

## 四 · 3-lens 对抗审裁决

三路 sonnet Explore 只读并行（正确性 / oracle 咬合 / a11y·规格诚实）。
逐条 grounded 复核后裁决（审查方也会 over-claim——每条先亲验再落地）：

| # | lens | 级 | finding | 裁决 |
|---|---|---|---|---|
| 1 | oracle | P2 | replay 脚本 `FAIL ⑩` 是 ⑩/⑩' 共同前缀，⑩' 独立 flake 会误报 BITE-OK | **采纳**：长前缀「FAIL ⑩入队」锚死 |
| 2 | oracle | P2 | ⑭C4′ 强加类无 try/finally，中途抛会把 enter-active 留在 DOM 污染后续 | **采纳**：JS 内 try/finally 摘类 |
| 3 | oracle | P2 | ⑯ 夹具翻任务状态不回滚——维护期地雷（当前无活性假绿，亲核属实） | **采纳**：记 id+原状态，枚举毕显式还原 |
| 4 | oracle | 局限 | elementFromPoint 单点中心采样漏部分遮挡（假阴性面） | **注释如实声明 + retro**（多点采样） |
| 5 | oracle | P3 | ⑮ 未建模 user-agent control 豁免（方向=过咬不漏咬，安全侧） | **注释声明**，不阻塞 |
| 6 | oracle | ✓ | m10 ⑩ route 注册同步先于 click，无竞态窗口；⑮′ cleanup 完备（推断安全） | 无动作 |
| 7 | correctness | P3 | roving 无「焦点在输入框则让位」守卫——今天全仓无 mount 期 autofocus，不咬 | **retro**（潜伏陷阱非现役 bug） |
| 8 | correctness | P3 | .app-main outline:none 无视觉信号——tabindex=-1 不进 Tab 序非 WCAG 2.4.7 违规，模式固有 | 记录，无动作 |
| 9 | correctness | ✓ | keyOf 同源 / TASK_WORK_STATES 与后端十态机+runner 集合精确对齐 / 6 消费者逐一不回归（含 DeliveryCard 省参数为死代码路径、新码反而更稳） | 无动作 |
| 10 | a11y | P2 | 无 route-change 播报——focus-only 非完整 WAI 方案（读屏只报 landmark） | **采纳**：.sr-announcer aria-live + afterEach 同拍写「已切换到＋页名」+ ⑭C6⁗ 探针（oracle 先行红 108/109 ann='' → 落码绿） |
| 11 | a11y | P2 | preventScroll 放弃滚动复位且无 scrollBehavior——新页停在旧滚动位 | **采纳**：scrollBehavior（回顶/savedPosition/同 pageKey 不动）；探针缺位如实标注留 retro |
| 12 | a11y | P3 | 同 pageKey 导航焦点零管理（非本批回归） | **retro** |
| 13 | a11y | ✓ | 三系统焦点互斥（QS/SC/roving）无回环打架（closeForNavigation 纪律）；spec B6-5 陈述无漂移；待签行时长移除=精度换诚实、代价已被文档承认 | 无动作；B6-2 措辞精确化已并入 spec |

采纳修复的再验证：⑭C6⁗ oracle 先行红→绿；oracle 三 P2 修复随绿跑回归
（⑯ 回滚夹具、⑭C4′ finally 在完好代码路径上行为不变）。

## 四-b · replay 脚本独立验证（B6-6 验收）

基 44ca543 隔离 worktree 全量 7 处（批五 3 + 批六 4）：`REPLAY ALL BITES OK`，
每处 BITE-OK 逐字命中预期 FAIL 行；未知名入参 fail-loud exit 2；worktree
trap 清理核验为空。首跑暴露两处 bash 3.2 兼容缺陷（declare -A / 多字节紧邻
展开吞字节）→ 修复于 d51b3c4，验证在修复版上重跑。时长佐证：10 分钟实跑
（主树 craft 单跑 ~96s × 7 + build，吻合，非秒退假绿）。

## 五 · Codex 治理审

### R0（审 44ca543+d51b3c4，native 20x Pro，read-only）：CHANGES_REQUIRED，3×P2 无 P1

| # | 级 | finding | 处置（全部 verbatim 落地，修复批 cea0075——amend 后终值，替代记录初稿所引 6db94a3） |
|---|---|---|---|
| 1 | P2 | router afterEach 未检查第三参 failure——被取消/中止的导航仍改 title、抢焦、播报未到达页 | 修 `(to, from, failure) => { if (failure) return; ... }`；新增 ⑭C7 探针（确定性夹具：hold 住 /me 懒加载 chunk→「对话」导航胜出→释放 chunk 让被取消导航结算）。**oracle 先行红逐字命中**：`title='我的贡献 · FLAi-OS' ann='已切换到我的贡献'`（109/110）→ 修复后 110/110 |
| 2 | P2 | ⑮ census 选择器漏 `[tabindex≥0]` 纯键盘目标——spec 声明与实现漂移，无 role 自定义目标整类逃逸 | 选择器扩 `a[href]`+`[tabindex]`+`native‖tabIndex>=0` 过滤；现状零新违规；**TB7 tamper 实证**：注入 10×10 `tabindex=0` span（crowded）→ ⑮ 红三页点名 `span.(10x10)` |
| 3 | P2 | replay 脚本 `‖ true` 吞退出码 + 无 clean baseline——既有红可被误归因成咬合 | baseline 前置（clean HEAD 两套件必须 RC=0+ALL GREEN 才准开咬）+ 咬合三条件（非零 RC + 精确 FAIL 行 + FAILED 汇总必达） |

R0 修复批验证：craft 110/110，verify_all 第三轮 EXIT=0 `[失败]（无）`。

R0 过程两处工程故障如实留痕：①首启 codex 进程挂死于模型列表刷新
（`failed to refresh available models` 循环，94 分钟无输出）——精准 kill
本会话 3 个 PID 后重启，重启轮 155k tokens 正常收敛。②本 §五 与 tamper log
的 R1 段落初稿曾被清理 PNG 抖动的 `git checkout -- docs/reviews` 误抹
（未提交 md 与 PNG 同目录连坐）——按 cp 备份纪律缺失自省，重写后 amend 收口。

### R1（审 cea0075）：CHANGES_REQUIRED——R0 三条 2 RESOLVED + 1 PARTIAL，新 1P2+2P3

| # | 级 | finding | 处置（全部 verbatim 落地） |
|---|---|---|---|
| 1 | PARTIAL→P2 | ⑭C7 固定 300/600ms 代替同步——忙机下 c7_held 可能为空或 chunk 未完成，旧实现也可能以「对话」残留态假绿 | 条件轮询 c7_held 非空（空则 assert fail-loud）+ `expect_request_finished` 同步 chunk 真实完成 + 双 rAF 后取 oracle；收紧后 craft 110/110 |
| 2 | P3 | baseline 裸 build 在 set -e 下失败会绕过 BASELINE-RED 分支 | `if ! (build)` 显式包壳，落 BASELINE-RED 带归因 |
| 3 | P3 | 记录引用 amend 前对象 6db94a3（无分支包含，新 clone 无法定位） | 改引 cea0075 并注明替代关系 |

### replay 集换血（新三条件的直接后果，如实留痕）

硬化后首轮验证 `timeout-cut` BITE-MISS——其咬合形态=FAIL ⑭C1 后下游崩溃
（批五存档如此），与「必达 FAILED 汇总」契约不相容。初判按契约优先处置：撤出
重放集换入批五 T3 降级条阉割（degrade-cut），7/7 验证通过——**此处置被 R2
否决，见下**。

### R2（审 e90f7ee）：CHANGES_REQUIRED——R1 三条全 RESOLVED，新 1P2

R1 #1/#2/#3 均判 RESOLVED（⑭C7 条件轮询+request_finished+双 rAF；baseline
build 包壳；记录引用 cea0075）。

新 [P2]：timeout-cut 撤出违反 canonical spec——spec §十五明确要求「超时撤除」
入重放集，脚本先行移除而未 amend 规格=治理漂移；「degrade-cut 可新增，不可
静默替换」。**采纳其首选修法（verbatim 例外收口，不再走一轮）**：
- 根因修：⑭C2 重试点击限时包 try（红而不崩）——⑭C1 红时 .today-retry 不存在，
  裸 click 30s TimeoutError 曾崩掉整套件；包裹后套件必达 FAILED 汇总，
  timeout-cut 满足干净咬合三条件，恢复入重放集；
- degrade-cut 按裁定改列「新增」；重放集=8 处，spec §十五 B6-6 同步 amend；
- 验证：craft 110/110（包裹后绿位无误红）+ 8 处全量重放（见下）。

### 终局（edea627）

基 edea627 全量重放：双套件 BASELINE-GREEN + **8/8 BITE-OK**（census/timeout/
degrade/reduce/roving/fitts/dialog/portal，三条件全举证；timeout-cut 红而不崩
达汇总——根因修实证）。craft 110/110 ×2（⑭C2 包裹与 ⑭C7 收紧后各一轮）。
verify_all 第三轮（EXIT=0）后仅动 craft e2e/replay 脚本/docs，产品代码零变更
——以 craft 双绿位为收口证据，如实声明未跑第四轮全量。

**治理链闭环声明**：tamper 7 处（TB1-TB7，含两次揭穿探针自身假绿）+ replay
8/8 独立可复跑 + verify_all ×3 EXIT=0 + 3-lens 13 findings 裁决 + Codex
R0→R1→R2（P1=0 全程，R2 剩余 P2 verbatim 落地）。按 standing 授权合并 push。
