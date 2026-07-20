# 变更记录

## 0.1.0（Agent-layer v1，2026-07-20）

- 新增 `jerryagent_sidecar@flai.agent-layer.v1` 冻结绑定。
- 默认 disabled，输出只作为 sensitive、candidate-only、人签必需的研究候选。
- 本地 `workflow.py` 改为 fail-closed sentinel，证明不可静默回退 native。

