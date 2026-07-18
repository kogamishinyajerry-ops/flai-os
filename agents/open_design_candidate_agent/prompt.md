# Open Design candidate agent

本 Agent 为 `model.profile=none` 的确定性作业，不调用 LLM，本文件仅保留 Agent
Package 的版本化 prompt 槽位。

任何生产 Open Design 生成都必须通过新的 `mock=false` Tool Package 接入，仍须保持
`candidate_only=true`、人工审核与发布隔离；不得把 prompt 文本当成签发规则。
