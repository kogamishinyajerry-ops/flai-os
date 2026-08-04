# FLAi-OS 接手 Handoff(Kimi-K3 批次,2026-07-31)

> 写给下一位开发者(GPT 5.6 sol 或其他):本文是 Kimi-K3 系列工作的交接事实清单。
> 判定依据以仓内 SSOT 与真实验证日志为准,不以前序会话记忆为准。

## 基线

- 仓库:`kogamishinyajerry-ops/flai-os`。本文撰写时 K3 基线为 `origin/main` @ `7122330`;**此后 codex 已合入 PR #18(CI 必需检查)/ #19(V1 源码就绪门禁,`5bf7be1`),请以 `git fetch && git rev-parse origin/main` 动态解析的最新 tip 为准**,不要按 `7122330` 复现验证。
- 请从最新 `main` 切新分支;`kimi-k3/ui-depth-polish-eac5896` 已全量合并(PR #15/#16/#17),使命完成。
- 项目规则:仓内权威源为 `docs/00_FLAi-OS_Constitution.md`(宪法)与 `docs/adr/`(决策史,36 篇,最新 ADR-0037);原始项目另有 `../flai-os/AGENTS.md`,但那是**兄弟仓本地文件、不在本仓**, clone 本仓后不可直接打开。设计 SSOT:`docs/design/UI-PARADIGM.md`、`docs/design/UI-DESKTOP-CRAFT.md`。

## main 新增能力(本轮三个 PR)

1. **PR #15**(基线 `eac5896` + 4 提交):门户能力地图关系行、治理弹窗闭环序号流与评测趋势语义化、创建任务纵向步进器(真实表单联动)、依据链/执行链去盒化、Ontology Shell 壳层(EP 图标统一、member-pill 暗色对比 7.3–7.5:1)、composer 深度工艺、任务台三栏密度、空态插画体系(20 调用点审计)、welcome-badge 1.25MB→45KB。
2. **PR #16**(2 提交):真实 ndjson 流式会话端到端(SSE 消费/跨 chunk sentinel 守卫/断连零落库/persisted 诚实语义+amber 对账锁)、UI 验收台 `frontend/ui-lab.html`(六 case,sandbox fail-closed 边界,入 verify_all)、FlaiBloom 品牌标(严格旋转对称,idle/generating/reduced-motion 三态)、流式停止钮、滚动跟随守卫+回到底部浮钮、键盘主路径(侧栏 router-link 化、选择器 Esc/↑↓)、围栏代码块(流式未闭合兜底)、会话标题投影(列表 API 新增 `first_user_message` 字段+前端三层诚实回退 SSOT)、签发确认钮 teal、首屏一排 40px 意图卡(说明层 243→165px)。
3. **PR #17**(1 提交):全站降噪(五律:人话优先/零值不显示/一处一行/行话进披露/稀疏即尊重)——方案卡分类学 chips 收 title、今日页 overview 三格改一行安静摘要、FeedbackPage 任务下拉人话打头。

## 验证基线

- 命令(必须在 `/private/tmp` 隔离副本,**e2e 会写 `docs/reviews`**,禁止在产品树直跑):
  `rsync -a --exclude='.git' <repo>/ <copy>/ && cd <copy> && UV_OFFLINE=1 bash scripts/verify_all.sh`
- 当前基线(EXIT=0,2026-08-04 批 0 实测 @ `d5a52aa`+切片 1;main 在动,以你实测为准):Pytest **1785 passed, 2 skipped**;Node **231/231**;E2E **21/21 套**;Craft **121/121**;Batch-G **46/46**;Batch-H **26/26**;bundle 预算:主入口 JS gzip ≈132KB(135,106B)、同步 CSS ≈20KB、动态入口 7、最大路由闭包 GuidePage ≈202KB。
- 体验审计档案(本机 `/tmp`,重启即失):`/tmp/ui-audit-lab/REPORT.md`、`/tmp/flai-audit-ux/REPORT.md`(12 维评分)、`/tmp/flai-audit-chain/`(流式链路证据:HAR/截图/observations)。审计 P1 已全部关闭;商业级验收清单 9/10,余=真实 LLM 内网复验。

## 红线(违反=废)

人是唯一签发者(LLM 不进判决链)· 假绿死罪 · fail-closed(`is True`/`is False`,绝不 truthiness)· mock 如实标注 · 信任色锁五槽(clay 工作/绿仅严格 REAL/teal 仅认证会话绑定人签/红真失败/amber 待核受限未知;completed 恒中性)· 不可变列 CAS-on-NULL · 诚实地板文案逐字不动 · e2e 锚(class/文案/DOM 序/颜色断言)变更必须实现+测试+截图原子同批 · 零新依赖零新框架(owner 批准除外)。

## 运行中的体验栈(一次性,本机 /tmp,重启即失)

- 前端 `http://127.0.0.1:5202`(vite dev,产品树)+ stub 后端 `127.0.0.1:8620`。
- launcher `/tmp/flai-audit-stack/launch.py`,DB `/tmp/flai-audit-stack/flai.db`;重启:`cd /tmp/flai-audit-stack && UV_OFFLINE=1 uv run --no-project --with fastapi --with uvicorn --with jsonschema --with pyyaml --with python-multipart --with "pydantic>2" --with httpx --with jieba --with openpyxl python launch.py`。
- 账户:`tester / Tester#2026`、`audit / Audit#2026`。stub 关键词:报错(中途失败 persisted:false)/慢(长流)/思考(首 token 前 5s 沉默)/拒绝/计划。

## 待裁决 / 待办(按优先级)

1. **真实 LLM 链路内网复验**——全部流式证据为 stub 网关驱动(链路真、内容假);`probe_llm_gateway.py` 连通性 + 真实网关走一遍 m6/m9。
2. **「今日页与任务台合并」owner 裁决项**——对话轴已全能(签发/产物/状态/恢复全内联),任务台已退深链无一级导航;合并=今日页三分组与任务台左栏语义去重。
3. **会话按登录用户隔离**(breaking,安全敏感):`list_conversations` 当前不按登录用户过滤,同域互见;`first_user_message` 投影未扩大该面,但真正的按人隔离需立项。**注意:只过滤列表不构成隔离**——codex 评审指出 `GET /conversations/{id}`、消息发送与流式、conclude、model-call 列表、任务列表均仅凭会话 ID 即可读写,不比对 `created_by` 与 `request.state.user`;任何持有可能猜到他人会话 ID 的已认证用户仍可越权。立项范围必须是**所有会话端点统一做 owner 校验**(可复用 `object_authorization` 的既有模式),而非仅改列表。
4. WorkLog 头「已处理 0 秒」零值段(craft ⑩G3 有锚,需原子同批)。
5. `IntentGlyph.vue` 零消费、`empty-log.png` 无 full 消费面——退役裁决。
6. `package_release.sh` 离线打包待 M4 落锤(预案 `docs/M11-OFFLINE-PACKAGE-PLAN.md`);Windows `.ps1` 未实机验证(仅 macOS AST 语法检查)。
7. 敏感密级 pill 常驻方案卡行头(判定为 amber 信任信号非分类学;owner 若裁定收 title,一行 v-if)。
