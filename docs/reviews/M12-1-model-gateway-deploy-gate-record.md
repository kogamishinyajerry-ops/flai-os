# M12-1 模型网关部署门 + 诚实配置错文案 · 审查档案

> 来源：PM 战略审 Workflow（10 agent 六镜头扫 33 机会去重 → 三裁判独立排序
> → 综合 M12 候选批）。**三裁判（战略价值/风险-首日/ROI）独立一致 top_pick**：
> 部署门 11 项全绿判定上线，但主入口「对话/导引」用 reasoning profile，首条
> 消息若 FLAI_LLM_* 未配即失败，门探不到这个确定性首日假绿=最伤采纳信心。

## 一、grounded 复核（工作流论断亲验坐实）

| 论断 | 亲验 |
|---|---|
| check_health 只断言 status==ok，无模型连通检查 | ✓ deploy_selfcheck.py:200 |
| /api/health 已返回 llm_base_url_set/api_key_set/model_reasoning_set 三布尔 | ✓ main.py health |
| guide_agent（对话主入口）用 profile: reasoning | ✓ agents/guide_agent/agent.yaml:26 |
| reasoning profile 的三 env = FLAI_LLM_BASE_URL/API_KEY/MODEL_REASONING（与 health 三布尔一一对应）| ✓ profiles.yaml |
| 缺 env → gateway 抛 ModelUpstreamError（fail-closed）→ conversations.py:119 包成 502「（可重试）」| ✓ gateway.py:79/84/90 + conversations.py:116 |
| 「（可重试）」对永久配置错误导（重试永不好）| ✓ 属实 |

## 二、实现（S 成本，两处）

1. **部署门第 7 项 check_model_gateway_config**：断言 health 三布尔（is True，
   不认 truthy），零外部依赖、**不往返 LLM**（保 stdlib-only，续 Codex R2-P2
   教训不拉 httpx）；更深连通性诊断走 probe_llm_gateway.py（httpx，非门职责）。
2. **诚实错误分流**：新增 `ModelConfigError(ModelUpstreamError)` 子类（errors.py）
   ——gateway 缺 env 三处改抛子类；conversations.py 优先捕获 → **503**「模型网关
   未配置，非临时故障，需管理员配置」（区别于临时上游故障的 502「可重试」）。
   子类向后兼容：既有 `except ModelUpstreamError` 全部仍捕获、失败留痕不变。

## 三、自证

- **单测**（test_deploy_selfcheck.py 4 + test_model_gateway.py 2 + test_m6 2）：
  门检查 PASS/FAIL/truthy-非-True/health 不可达；子类分流（缺 env=ModelConfigError、
  上游 500≠ModelConfigError）；导引缺 env→503 事务性零落库、临时故障→502 可重试。
- **tamper 变异 8b**（门判定 `is not True`→`if False` 恒不缺失）：2 witness 咬中
  假绿回归。
- **真机三态**（scratch 服务）：不配 FLAI_LLM_* → 第 7 项 FAIL（「首条消息将 503」）；
  配了 → PASS。
- **连带修**：3 处任务路径测试（knowledge_qa/fta/audit）断言的异常类名
  ModelUpstreamError→ModelConfigError（缺 env 是配置错子类，更精确）。
- verify_all 十步全绿（build+646 pytest+8 e2e，m6 导引走 502 临时路径不受影响）。

## 四、Codex 异源治理审（86gs gpt-5.6-sol ultra）

**R0：No actionable correctness defects found**（干净过关，90 个改动测试全收集）。
沙箱只读无法跑全量，本地已 646 passed 补足。

## 五、递延（PM 战略审 M12 候选批其余项，入队列待 owner/后续）

rank2 control_logic 首个真实 L1 晋升（挂服务重启窗口）· rank3 stdlib 进程日志
基建 + 认证审计 · rank4 部署门自证负例测试 + 单实例锁自排他探针 · rank5 进程
守护交付物（systemd/NSSM）· rank6 reviewer≠creator 职责分离子赢 + 完整角色轴
（真实 EAR 数据进场硬前置，owner 拍板）。详见战略审综合输出。
