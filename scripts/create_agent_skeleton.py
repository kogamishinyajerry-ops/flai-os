#!/usr/bin/env python3
"""新 Agent 包脚手架（评审 N14「共建入口」）。

把「复制 hello_agent 再逐字段改」压成一条命令：生成一个**当场就能通过
Agent Registry 扫描**的最小合法包（status=draft / maturity=L0 / 无模型 /
零工具），业务逻辑与真实契约由开发者接着填。

安全性质（fail-closed）：
- 目标目录已存在 → 拒绝并退出 2，绝不覆盖任何现有包；
- 全部文件先在内存渲染并**自验**（agent.yaml 过 contracts/agent.schema.json，
  两个 IO 契约过 JSON Schema 元校验）通过后才落盘——不产生半截包；
- id 约束与 schema 同一正则（^[a-z][a-z0-9_]{2,63}$），不合法退出 2。

用法：
    python scripts/create_agent_skeleton.py my_agent \
        [--name 显示名] [--summary 一句话] [--category tool_automation] [--root agents]
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path

import jsonschema
import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENT_SCHEMA_PATH = REPO_ROOT / "contracts" / "agent.schema.json"

# 与 contracts/agent.schema.json 的 id pattern 逐字一致（单一真源在 schema，
# 这里提前拦只为给出中文可读错误而非 jsonschema 报文）。
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

CATEGORIES = ["tool_automation", "knowledge_qa", "structured_gen", "reasoning_assist"]


def _yaml_scalar(value: str) -> str:
    """把用户串编码成安全的 YAML 双引号标量（Codex 治理审 R0 P1）。

    json.dumps 产出的双引号串是合法 YAML flow 标量（YAML 是 JSON 超集），且把
    换行/引号/控制符全转义——堵死 `--name "x\\nstatus: released"` 这类换行注入
    重复键、把 draft/L0 篡成 released/L2 的越治理路径。ensure_ascii=False 保中文。
    """
    return json.dumps(value, ensure_ascii=False)


def render_agent_yaml(agent_id: str, name: str, summary: str, category: str) -> str:
    # f-string 模板而非 yaml.dump：注释是给新手看的承重内容，dump 会丢光。
    # name/summary 经 _yaml_scalar 安全编码（绝不裸插——YAML 注入越治理红线）。
    return f'''id: {agent_id}
name: {_yaml_scalar(name)}
version: 0.1.0
status: draft            # draft → trial → released 走治理流程；不改此行不会上生产
maturity: L0             # L0=原型；升 L1 走 scripts/promote_agent_l1.py（评测门）
category: {category}
summary: {_yaml_scalar(summary)}
description: >
  TODO：两三句话说清楚——给谁用、输入什么、产出什么、边界在哪。
owner:
  department: 二所
  maintainer: TBD        # 写真名：问题找得到人是治理底线
  business_reviewer: TBD
model:
  profile: none          # 需要大模型时改画像名（见 contracts/model_profile.schema.json）
knowledge:
  enabled: false
  scopes: []             # 只能填 Scope Registry 已注册的 scope（装配期对账，缺=整包拒）
tools: []                # 只能填 Tool Registry 已注册的 tool id（default-deny 对账）
input:
  type: params
  schema: input_schema.json
output:
  formats:
    - .json
  schema: output_schema.json
workflow:
  entrypoint: workflow.py
  mode: job
  requires_human_review: true   # 业务 Agent 默认要人签发；确无判断成分才可改 false
permissions:
  visibility: admin_only        # 试跑期先只对管理员可见，验证后再放开
  allowed_roles:
    - admin
    - agent_developer
logging:
  save_inputs: true
  save_outputs: true
  save_tool_logs: true
  save_model_calls: true
  save_feedback: true
data_asset:
  collect_samples: false        # 样本回流默认关；确认无敏感字段后再开
  sample_fields: []
limitations:
  - "TODO：如实写下本 Agent 不适用的范围——诚实边界会上屏给使用者看，不是免责声明。"
'''


def render_input_schema(agent_id: str) -> str:
    return json.dumps(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"{agent_id} 输入契约（TODO：替换成真实字段）",
            "type": "object",
            "additionalProperties": False,
            "required": [],
            "properties": {
                "example_input": {
                    "type": "string",
                    "title": "示例参数（占位——请替换为真实输入字段）",
                    "description": "脚手架占位字段：改成真实字段名+类型+中文 title 再提交。",
                }
            },
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def render_output_schema(agent_id: str) -> str:
    return json.dumps(
        {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": f"{agent_id} 输出契约（TODO：替换成真实结构）",
            "type": "object",
            "additionalProperties": False,
            "required": ["result"],
            "properties": {
                "result": {
                    "type": "string",
                    "description": "脚手架占位输出：workflow.py 与本契约同步改。",
                }
            },
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


WORKFLOW_TEMPLATE = '''"""{agent_id} workflow 骨架（create_agent_skeleton 生成）。

统一入口约定（docs/02_Agent_Package_Standard.md）：
    def run(context: dict) -> dict
context 至少含 inputs / tool_registry / event_logger / output_dir；
返回 {{"status": "success" | "failed", "outputs": [...]}}。
骨架只做「回显输入并落一个产物」——证明包能跑通，业务逻辑由你替换。
"""

from __future__ import annotations

import json
import os
from typing import Any


def run(context: dict[str, Any]) -> dict[str, Any]:
    inputs = context.get("inputs", {{}})
    output_dir = context.get("output_dir", ".")
    # TODO：替换为真实业务逻辑；工具经 context["tool_registry"].call(...) 调用，
    # 关键节点用 context["event_logger"].log(...) 留痕。
    result = {{"result": f"skeleton ok（inputs={{json.dumps(inputs, ensure_ascii=False)}}）"}}
    path = os.path.join(output_dir, "result.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    return {{"status": "success", "outputs": [result]}}
'''


README_TEMPLATE = """# {agent_id}

由 `scripts/create_agent_skeleton.py` 生成的最小合法 Agent 包（已可通过
Registry 扫描）。上生产前按顺序补齐：

1. **agent.yaml**：填 summary/description/limitations 的 TODO，maintainer 写真名；
2. **input_schema.json / output_schema.json**：换成真实契约（占位字段必须删）；
3. **workflow.py**：写业务逻辑（工具走 tool_registry.call，留痕走 event_logger.log）；
4. **eval_cases/**：至少补一条真实用例（参照 agents/hello_agent/eval_cases/）；
5. 本地验证：`bash scripts/verify_all.sh`（或先跑 backend 测试子集）；
6. 治理路径：draft 试跑 → 评测过门升 L1（scripts/promote_agent_l1.py）→ 按需申请 trial/released。

红线提醒：requires_human_review 默认 true——你的 Agent 产物默认停在人签发面前，
这是平台宪法（人是唯一签发者），不是流程摩擦。
"""


CHANGELOG_TEMPLATE = """# Changelog

## 0.1.0 — {today}

- create_agent_skeleton 生成初始骨架（draft/L0，未接业务逻辑）。
"""


PROMPT_TEMPLATE = """# 提示词（当前未启用）

model.profile=none 时本文件不参与运行。接入大模型（改 agent.yaml 的
model.profile）后，在此维护系统提示词，并保持与 workflow.py 的调用一致。
"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="生成最小合法 Agent 包骨架（N14）")
    parser.add_argument("agent_id", help="Agent id（^[a-z][a-z0-9_]{2,63}$）")
    parser.add_argument("--name", default=None, help="显示名（默认取 id）")
    parser.add_argument("--summary", default=None, help="一句话能力描述（默认 TODO 占位）")
    parser.add_argument("--category", default="tool_automation", choices=CATEGORIES)
    parser.add_argument("--root", default=str(REPO_ROOT / "agents"),
                        help="包根目录（默认仓内 agents/；测试用）")
    args = parser.parse_args(argv)

    agent_id = args.agent_id
    if ID_RE.fullmatch(agent_id) is None:
        print(f"[拒绝] agent_id 不合法：{agent_id!r}（要求 ^[a-z][a-z0-9_]{{2,63}}$，"
              "小写字母开头，只含小写字母/数字/下划线）", file=sys.stderr)
        return 2

    target = Path(args.root) / agent_id
    if target.exists():
        print(f"[拒绝] 目录已存在：{target}——脚手架绝不覆盖现有包（fail-closed）。",
              file=sys.stderr)
        return 2

    name = args.name or f"{agent_id}（骨架，待补显示名）"
    summary = args.summary or "TODO：一句话说清本 Agent 替使用者做什么（会上屏到门户卡片）。"

    files = {
        "agent.yaml": render_agent_yaml(agent_id, name, summary, args.category),
        "input_schema.json": render_input_schema(agent_id),
        "output_schema.json": render_output_schema(agent_id),
        "workflow.py": WORKFLOW_TEMPLATE.format(agent_id=agent_id),
        "README.md": README_TEMPLATE.format(agent_id=agent_id),
        "changelog.md": CHANGELOG_TEMPLATE.format(today=date.today().isoformat()),
        "prompt.md": PROMPT_TEMPLATE,
    }
    # 最小可执行 eval 用例（Codex 治理审 R0 P2 → R1 P2 修正终态）：空 eval_cases/ 与
    # docs/07 非空强制规则冲突且「最小合法包」名不副实。占位断言必须是
    # **waiting_review**——脚手架固定 requires_human_review: true，成功执行的终态是
    # 人签发前的 waiting_review 而非 completed（人是唯一签发者红线）；断言 completed
    # 会让占位用例必然失败。如实标注待替换。
    eval_case = json.dumps(
        {
            "case_id": "case_001_placeholder",
            "description": "脚手架占位用例（TODO：替换为真实输入与断言，参照 agents/hello_agent/eval_cases/）。requires_human_review=true 故成功终态为 waiting_review。",
            "inputs": {"example_input": "占位输入"},
            "checks": [{"kind": "status_is", "value": "waiting_review"}],
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"

    # ── 落盘前自验（渲染在内存，验证全过才写第一个字节）──
    manifest = yaml.safe_load(files["agent.yaml"])
    agent_schema = json.loads(AGENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.validate(manifest, agent_schema)
    # 治理字段落地不变量（Codex 治理审 R0 P1）：即便 name/summary 被安全编码，
    # 仍显式断言解析后的治理字段=预期——脚手架**只能**产出 draft/L0/本 id，
    # 任何注入把它们改成 released/L2/别的 id 一律 fail-closed 拒绝落盘。
    for field_name, expected in (("id", agent_id), ("status", "draft"),
                                 ("maturity", "L0"), ("category", args.category)):
        actual = manifest.get(field_name)
        if actual != expected:
            print(f"[拒绝] 自验失败：{field_name}={actual!r} ≠ 预期 {expected!r}"
                  "（疑似注入篡改治理字段，绝不落盘）", file=sys.stderr)
            return 2
    for key in ("input_schema.json", "output_schema.json"):
        jsonschema.Draft202012Validator.check_schema(json.loads(files[key]))

    # ── 原子落盘（Codex 治理审 R0 P2 → R1 P2 唯一 staging）：先写同父目录下
    # **每次调用唯一**的临时包（tempfile.mkdtemp，不再用固定名），全部成功后
    # os.replace 原子改名到目标——磁盘满/权限错/中断只留可清理的临时目录，绝不
    # 在正式路径留半截包。唯一 staging 名杜绝并发调用互相 rmtree（固定名的旧
    # 缺陷）。目标已存在预检见上（exists()→return 2）；os.replace 到已存在的
    # 非空目录会 OSError（POSIX rename 语义），此处目标预检已过，残留竞态窗口
    # 对单用户本地脚手架工具可接受，不再引入跨平台目录锁。──
    target.parent.mkdir(parents=True, exist_ok=True)  # 包根目录（agents/）不存在则先建
    staging = Path(tempfile.mkdtemp(prefix=f".{agent_id}.skeleton.", dir=target.parent))
    try:
        (staging / "eval_cases").mkdir()
        for rel, content in files.items():
            (staging / rel).write_text(content, encoding="utf-8")
        (staging / "eval_cases" / "case_001_placeholder.json").write_text(
            eval_case, encoding="utf-8")
        os.replace(staging, target)  # 同一文件系统内原子改名
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)  # 异常/中断不留半截临时包
        raise

    print(f"已生成 Agent 包骨架：{target}")
    print("  状态：draft / L0，requires_human_review=true（人签发默认在）")
    print("  下一步（按序）：")
    print("  1. agent.yaml 填掉全部 TODO（maintainer 写真名）")
    print("  2. input/output_schema.json 换成真实契约（删占位字段）")
    print("  3. workflow.py 写业务逻辑")
    print("  4. eval_cases/ 用真实用例替换占位（参照 agents/hello_agent/）")
    print("  5. bash scripts/verify_all.sh 全绿后再走治理（README.md 有完整路径）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
