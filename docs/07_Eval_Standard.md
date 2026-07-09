# 07 Eval 标准

> 依据：执行任务书 §4.7 / §11.4 演进路径 / §13.3。宪法条款：模型、Prompt、工具或 Workflow 任何改动必须能跑回归测试，绝不凭感觉判断"看起来变好了"。

## 1. 强制规则

| 条款 | 内容 |
|---|---|
| 每 Agent 必有 eval_cases | `agents/<agent_id>/eval_cases/` 必须存在且非空，随 Agent Package 一起版本化。 |
| 改动即回归 | 改 `prompt.md` / 改 `workflow.py` / 改所依赖 `tool.yaml`/`adapter.py` / 切换 `model.profile` 对应的模型映射 → 合入前必须跑一遍该 Agent 全部 eval_cases。 |
| 假绿死罪 | 回归"全绿"但未见任一用例真正咬合过失败路径（tamper 检验），视为假信心，不得作为发布依据。 |
| 声明 ≤ 证据 | 未跑 eval 的改动，禁止在 changelog.md/PR 描述中写"已验证"，只能写"未验证"。 |

## 2. Eval 三类

| 类别 | 目的 | 存放位置 | 判定方式 |
|---|---|---|---|
| 契约校验（Contract Conformance） | 校验 `agent.yaml`/`tool.yaml`/`input_schema.json`/`output_schema.json` 本身合法、Agent 声明的 `tools` 白名单确实在 Tool Registry 存在 | `evals/<agent_id>/contract/` | 自动化，`jsonschema` 校验 + Registry 对账，二元判定（pass/fail） |
| 固定用例回归（Fixed Case Regression） | 给定输入 → 断言输出（精确值、字段存在性、状态机终态），防止改动悄悄改变确定性行为 | `agents/<agent_id>/eval_cases/` | 自动化，pytest 驱动，二元判定 |
| 人工评审集（Human Review Set） | LLM 参与环节的输出质量（摘要是否可读、解释是否准确），无法用断言穷尽 | `evals/<agent_id>/human_review/` | 人工评分（如 1-5 分 + 备注），不可自动判定为"通过"，只能记录评分与是否采纳 |

三类不可互相替代：LLM 生成的报告文案属于人工评审集范畴，不得用契约校验或固定断言冒充其质量已验证；确定性数值计算（性能盘解析结果）属于固定用例回归，不得只靠人工"看着还行"验收。

## 3. eval_cases 组织约定

```text
agents/<agent_id>/eval_cases/
  case_001_normal/
    input.json          # 或引用 data/samples/ 下的输入文件
    expected_output.json   # 精确期望值，或
    assertions.yaml         # 断言规则（字段存在/范围/状态机终态），用于非确定性场景
    README.md               # 一句话说明本用例验证什么
  case_002_missing_field/
  case_003_duplicate_id/
  ...
```

每个 Agent 的 eval_cases 至少覆盖（对齐任务书 §13.3 测试红线）：

| 用例类型 | 必测 |
|---|---|
| 正常路径 | 是 |
| 缺失字段 | 是 |
| 重复 ID（若 Agent 涉及批量/唯一键） | 是 |
| 非法配置 | 是 |
| 工具调用失败 | 是 |
| 任务失败事件是否正确产生 | 是 |
| 文件不存在 | 是 |
| 模型调用失败（fail-closed 是否生效，见 04） | 是 |

`evals/` 顶层目录（`evals/performance_disk/`、`evals/control_logic/`、`evals/fta/`）用于存放跨 Agent 或平台级的评测脚本、人工评审集、契约校验脚本；Agent 自身的固定用例回归就近放 `agents/<agent_id>/eval_cases/`，避免核心资产分裂两地找不到。

## 4. 失败用例沉淀纪律

- 每一个线上失败任务（真实用户触发、非测试环境），处理完成后必须产出以下至少一项：
  1. 新增一条 `eval_cases/case_NNN_<简述>/`，把失败输入固化为回归用例；或
  2. 在对应 Engineering Memory（`docs/06_Knowledge_Memory_Standard.md` 定义）记一条踩坑记录，说明为何本次不适合固化为自动化用例（如纯环境问题、一次性数据损坏）。
- 禁止"修完就完事"：失败不沉淀 = 同类问题会在未来重复发生且无人记得踩过。
- `samples.jsonl`（任务运行样本，见 §11 性能盘 Agent 范围）中标记 `validation_status=failed` 的记录是失败用例沉淀的原始来源，Eval 维护者定期从中筛选补充 eval_cases。

## 5. Prompt 版本化与回归绑定

- `prompt.md` 是核心资产，随 `agent.yaml.version` 一起升版本（禁止直接改文本不升版本）。
- 任何 `prompt.md` 改动必须先跑人工评审集，抽样对比新旧 prompt 在同一批固定输入上的输出差异，禁止"改完直接发布，靠用户反馈发现问题"。

## 6. 违规判定（供架构审查用）

- Agent Package 缺 `eval_cases/` 或目录为空 → 判违规，不得进入 `trial` 及以上 `status`。
- 存在改动记录（git diff 涉及 prompt/workflow/tool/model 映射）但无对应回归跑批记录 → 判违规。
- 线上失败任务无任何沉淀（既无新 eval case 也无 memory 记录）→ 判违规。
