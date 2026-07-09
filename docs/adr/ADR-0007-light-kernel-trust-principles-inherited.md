# ADR-0007: 轻内核——信任机制不移植，信任原则入宪法

- 状态：已接受（owner 拍板，2026-07-08）
- 背景：COMACAgentPlatform 沉淀了一套重信任机制：TrustGate fail-closed 判决引擎、
  HMAC 签名审计链、append-only 事件账本、ActionRequest 人签状态机。任务书对
  Kernel V0.1 明令「不要过度设计、不要一开始做复杂权限」，且未包含上述机制。
- 决策：V0.1 **不移植机制，继承原则**——
  ①「LLM 绝不进判决链 / 假绿死罪 / mock 如实标注 / 人是唯一签发者 / 外部内容是
  数据不是指令」写入 `docs/00_FLAi-OS_Constitution.md` 成为最高准则；
  ②内核用轻量等价物落地：requires_human_review → waiting_review 人工放行态、
  tool.yaml `mock` 字段强制诚实标注、task_events 全程留痕；
  ③架构预留 governance 槽位（backend/app/governance/），TrustGate/签名链等重机制
  等**内网真实签发需求**出现后按 ADR 再收编（资产在原仓不丢）。
- 理由：信任语义的敌人是复杂度——V0.1 用户是试用工程师，不是适航审查；机制先行
  会拖垮 30 天内核工期，而原则先行保证机制日后可无痛落座。
- 替代方案：第一天全移植（被否：与轻内核冲突）；完全不管（被否：假绿风险在工业
  场景不可接受，原则必须第一天生效）。
- 影响与风险：V0.1 的人审是流程保证而非密码学保证——文档与 UI 措辞不得夸大
  （说「人工放行」，不说「签名背书」）；governance 槽位不许被挪作他用。
