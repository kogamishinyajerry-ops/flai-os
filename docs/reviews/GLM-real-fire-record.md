# 真实 LLM 首次点火记录（公网 GLM，2026-07-11）

> 性质：**本机 + 公网 GLM 的参照实测**，不是内网验收——内网端点/鉴权/模型形态
> 仍以 M4 现场侦察为准（docs/M4_intranet_day1_recon_checklist.md §① 的现场填列
> 保持空白）。本记录的价值：网关协议链路、fail-closed 行为、审核闭环在**真实
> 模型**下首次全链验证通过，「平台未跑过任何真实业务」自此作废（README #9 已同步）。

## 接入方式（零代码改动）

- 端点：`https://open.bigmodel.cn/api/coding/paas/v4`（OpenAI 兼容 /chat/completions）
- 环境变量：`FLAI_LLM_BASE_URL` / `FLAI_LLM_API_KEY` / `FLAI_LLM_MODEL_REASONING=glm-5.1`
  / `FLAI_LLM_MODEL_FAST=glm-5.1`——profiles.yaml/网关/Agent 代码零改动，
  验证了「升级模型只改环境变量」的设计承诺。**key 不入仓、不入 .env 文件、
  不出现在任何日志（探针输出已脱敏）。**

## 分层探针观测（scripts/probe_llm_gateway.py）

- HTTP 200 · Content-Type application/json · JSON 可解析
- `choices[0].message.content` 存在 ✓ · `usage` 存在 ✓（含 completion_tokens_details.reasoning_tokens 扩展字段，网关按契约忽略未知字段）
- 中文往返正常（下方两条业务实测即中文全程）
- 对应 M4 checklist 1-1/1-3/1-4 的**公网参照证据**（内网现场列不填）

## 业务实测 #1：导引真实对话（guide_agent × glm-5.1）

- 输入：「一批性能盘试验数据想做批量校核，再对超差 case 做 FTA」
- 真实模型行为：**decision=refuse 诚实拒绝**——正确引用 performance_disk_agent
  契约 limitations（模拟阶段/纯属虚构），拒绝用 mock 做真实数据校核，
  并指出 fta_agent 可独立走、需要哪些直接输入。26.6s 一轮。
- 结论：宪法「接不住就明说」在真实模型下自然涌现（契约层 limitations 文案
  被 LLM 忠实采信——P2-8 文案轮的下游价值实证）。

## 业务实测 #2：fta_agent 全链（人签闭环）

task_75869032910e4ae5ba5a387658890c6f：
- queued → running（真实 GLM 调用 ~30s）→ **waiting_review**（绝无自动放行）
- model_calls 留痕：glm-5.1 · success · usage {prompt 205, completion 2328, total 2533}
  ——TaskDetail「模型调用」消耗披露块首次显示真实数据
- 草案产物：强制水印齐全（「AI 辅助生成…不得用于任何安全性判断」+ 宪法第五条
  引用），中间事件/基本事件按组件分组，不确定处逐条标「待工程师确认」
- 人签放行：reviewer=Jerry approve → completed；样本 review_outcome 回填链路生效

## 边界与残余（诚实清单）

- 公网 GLM ≠ 内网 GLM：鉴权形态/模型名/延迟/限流内网可能不同，M4 侦察不可省；
- glm-5.1 的 `reasoning_content` 扩展字段网关当前忽略——若内网模型同形态，
  推理过程不留痕（是否需要留痕待 owner 判断，涉及存储量）；
- MODEL_FAST 暂同 reasoning（按需分档）；60s 超时对 2.5K token 草案充裕，
  更长草案未压测。
