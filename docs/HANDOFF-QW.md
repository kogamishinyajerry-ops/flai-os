# FLAi-OS 接手 Handoff（Qwen 批 → Kimi-K3，2026-08-04）

> 写给下一位开发者：本文是 Qwen 批工作的交接事实清单。判定以仓内 SSOT 与真实验证日志为准。
> 规划方法：mattpocock/skills wayfinder（GitHub tracker 化）——map=#32，纪律：plan, don't do；
> refer by name；每会话至多闭一张非 research 票；HITL 票不替 owner 代答。

## 基线与在审

- origin/main @ `d354079`（含切片 1 + codex 修复）。**三 PR 在审，合并均需 owner 确认**：
  - **PR #34** 退役批（IntentGlyph/empty-log 退役 + 密级 pill 收 title）+ a11y 修复
    （敏感行 agent-name tabindex+aria-label，codex P2，线程已 resolve）；
  - **PR #35** 切片 3 长会话阅读节奏方案 B（workSegments 段分隔/中段折叠/段界时间戳）；
  - **PR #37** 通识叙事通道第四姿态 + 对抗性 eval + 本 handoff + 审计栈 launcher。
- 合并顺序任一；#35/#37 在 tamper_replay 与 HANDOFF-K3 有轻量重叠，冲突手解。
- 合并后从最新 main 切新分支，不续用 qw/* 旧分支。

## 必读（按序）

1. `docs/00_FLAi-OS_Constitution.md`；2. `docs/HANDOFF-K3.md`（基线数字见其验证节，含切片 3 分支面）；
3. `docs/NEXT-STEPS-ONTOLOGY.md`；4. `docs/adr/ADR-0033`、`ADR-0039`；
5. `docs/design/UI-PARADIGM.md` + `UI-DESKTOP-CRAFT.md`；
6. `docs/reviews/BATCH0-AGENT-SHELL-AUDIT.md`（P0/P1/P2 与裁决留痕 SSOT）；
7. `docs/reviews/S3-SEGMENT-RHYTHM-record.md`；8. wayfinder map #32（gh issue view 32）。

## wayfinder map #32 状态

- closed：#25/#26（research）、#27（prototype=方案 B）、#29（退役）、#31（切片 3）、#33（通识通道）。
- frontier：**#36（地板句松弛，owner 新指令，最高优先）**、#28（侧栏标题二层缓存 P1-1）、
  #30（今日页/任务台合并，owner 已裁）。
- out of scope：会话隔离实施（草案=BATCH0 报告 §4，exact-owner 404 塌缩，无跨用户场景已确认）、
  NEXT-STEPS 本体切片、薄沙箱（ADR-0039）、离线打包 M4、真实 LLM 内网复验。

## owner 新指令（#36，最高优先）

「过于强调工程严格和准确性标记，导致反复显示『以上为通识参考解释，非本型号工程结论；
工程判断以确定性工具与人签为准』之类标语，毫无意义——**只要在最终批准或重要授权的时候
显示就行**。」

施工面：① guide prompt 删逐答强制地板句（第四姿态与边界红线保留：直答不得含工程数值结论/
合格性判定/签发口径）；② 诚实标记归位批准/授权面（人签卡/VerificationCard 加一行，先核 e2e
锚原子同批）；③ 契约测试源码锚同步（backend/tests/test_guide_auto_routing_contract.py
的两个 #33 测试）；④ eval case_002 的 floor_sentence_present 改注授权面或移除。
**防过正红线**：松弛的是通识免责声明频率，不是宪法诚实纪律——mock=true、未验证标注、
人签面诚实地板一律不得弱化；信任色锁五槽不增不改。

## 验证基线（2026-08-04 实测，main 在动以你实测为准）

pytest **1787 passed/2 skipped**；node **239**；E2E **21 套**；Craft **121**；Batch-G **52**
（#34 合入后 +1）；Batch-H **26**；bundle 主入口 gzip ≈135.1KB。
命令：隔离副本 `rsync -a --exclude='.git' --exclude='node_modules' <repo>/ /private/tmp/<copy>/`
后 `UV_OFFLINE=1 bash scripts/verify_all.sh`，EXIT=0 必需；**e2e 禁在产品树直跑**（写 docs/reviews）。

## 体验栈（UI 切片 before/after 基线，重启即失）

launcher 已入库 `scripts/audit_stack_launcher.py`（stub 关键词：报错/慢/思考/拒绝/超出已审定/计划；
常规轮多样回应）。`cd /tmp/flai-audit-stack && UV_OFFLINE=1 uv run --no-project --with fastapi
--with uvicorn --with jsonschema --with pyyaml --with python-multipart --with "pydantic>2"
--with httpx --with jieba --with openpyxl python <repo>/scripts/audit_stack_launcher.py`；
前端 `npm run dev -- --port 5202`；账户 `tester/Tester#2026`、`audit/Audit#2026`。

## 坑位清单（实测教训）

- `.composer-input` 是 el-input 外壳，真 textarea 在内层；el-drawer 关闭后节点留 DOM 隐藏
  （断言 state=hidden 非 detached）；StatusCenter Esc 层层退出需焦点先在 sc-shell 内。
- `planHasTasks` 按全会话 agent 拦同 agent 二次开工（产品语义，e2e 造段走 refuse 终点）；
  `_validate_refuse` 三必填 reason/residual_problems/reframe 缺一作废；
  GuidePage 禁裸 `watch(route.query.c)`（源码护网断言）。
- rsync 会用产品树陈旧 dist 盖掉副本新构建（manifest 指旧 chunk 致假阴/假阳）——e2e 复跑前
  确认 dist 与源码同代；/tmp 栈 kill 须 uv+python 双杀；nohup 用 `env VAR=1` 前缀；
  stub 关键词与消息须逐字子串匹配；stub 单模板复述会被 owner 误判产品 bug。
- codex bot 意见质量高（两轮全命中真问题），PR 线程须全 resolve 才许合并。

## 待裁决/跟踪（移交）

- #34/#35/#37 合并确认（owner 已准 push/PR，合并另确）；
- #30  mini-spec（合并后今日页分组形态、任务台深链发现性线索）；
- retro：首段过长是否可折、折叠展开滚段首、dock 审计多点采样、scrollBehavior 独立探针、
  焦点在输入框时 roving 让位、窄屏 dock 带布局、E3 门禁（NEXT-STEPS §4.4）。
