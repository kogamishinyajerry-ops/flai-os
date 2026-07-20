"""M0 契约自校验门：六份 schema 合法 + 示例包过校验 + 反例必咬。

这是仓库的第一道 gate。它咬三类漂移：
1. contracts/*.schema.json 本身不是合法 JSON Schema（schema 腐坏）；
2. 示例包（hello_agent / mock_tools）与契约脱节（标准与样例互相说谎）；
3. 契约失去咬合力（反例 witness：缺必填字段/非法枚举必须 FAIL——
   「全绿」但反例不咬 = 假信心，见 docs/00 宪法第五条）。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError, validate

REPO = Path(__file__).resolve().parents[1]
CONTRACTS = REPO / "contracts"

SCHEMA_FILES = [
    "agent.schema.json",
    "tool.schema.json",
    "task.schema.json",
    "event.schema.json",
    "model_profile.schema.json",
    "knowledge_scope.schema.json",
]


def _load_schema(name: str) -> dict:
    return json.loads((CONTRACTS / name).read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ── 1. schema 本身合法 ──────────────────────────────────────────────

@pytest.mark.parametrize("name", SCHEMA_FILES)
def test_schema_file_is_valid_jsonschema(name: str) -> None:
    schema = _load_schema(name)
    Draft202012Validator.check_schema(schema)
    # 契约必须自我说明：无 title/description 的契约不许进仓
    assert schema.get("title"), name
    assert schema.get("description"), name


# ── 2. 示例包过校验（标准与样例不许互相说谎）────────────────────────

def test_hello_agent_yaml_validates() -> None:
    agent = _load_yaml(REPO / "agents/hello_agent/agent.yaml")
    validate(agent, _load_schema("agent.schema.json"))


@pytest.mark.parametrize(
    "agent_dir",
    sorted(p.name for p in (REPO / "agents").iterdir() if (p / "agent.yaml").is_file()),
)
def test_every_agent_package_yaml_validates(agent_dir: str) -> None:
    """遍历仓内全部 Agent 包过 agent.schema.json（M5 起多 Agent 并存，
    新包漂移不许只靠 hello_agent 一个样本兜底）。"""
    agent = _load_yaml(REPO / "agents" / agent_dir / "agent.yaml")
    validate(agent, _load_schema("agent.schema.json"))


def test_mock_tool_yaml_validates() -> None:
    tool = _load_yaml(REPO / "tools_impl/mock_tools/tool.yaml")
    validate(tool, _load_schema("tool.schema.json"))
    # mock 工具必须诚实自标（宪法第五条在契约层的落点）
    assert tool.get("mock") is True


def test_hello_agent_package_files_exist() -> None:
    pkg = REPO / "agents/hello_agent"
    for f in ["agent.yaml", "prompt.md", "workflow.py", "input_schema.json",
              "output_schema.json", "README.md", "changelog.md"]:
        assert (pkg / f).is_file(), f"Agent Package 缺 {f}（docs/02 标准强制）"
    assert (pkg / "eval_cases").is_dir(), "Agent Package 缺 eval_cases/（docs/07 强制）"
    assert any((pkg / "eval_cases").iterdir()), "eval_cases/ 不许为空"


def test_mock_tool_package_files_exist() -> None:
    """Tool Package 核心四件强制（docs/03；input_builder/output_parser 仅文件型工具强制）。"""
    pkg = REPO / "tools_impl/mock_tools"
    for f in ["tool.yaml", "adapter.py", "README.md"]:
        assert (pkg / f).is_file(), f"Tool Package 缺 {f}（docs/03 核心四件）"
    assert (pkg / "tests").is_dir() and any((pkg / "tests").glob("test_*.py")), \
        "Tool Package 缺 tests/（docs/03 核心四件）"


def test_slot_directories_tracked() -> None:
    """槽位目录必须从第一天进版本库（宪法 §6；任务书 §5）——git 不追踪空目录，靠 .gitkeep。"""
    for d in ["evals", "backend/app", "backend/tests", "frontend/src",
              "frontend/public", "data/samples", "logs"]:
        p = REPO / d
        assert p.is_dir(), f"槽位目录缺失：{d}"
        assert any(p.iterdir()), f"槽位目录 {d} 为空且无 .gitkeep（首次 commit 会静默丢失）"


def test_hello_agent_declared_tool_is_registered_mock_tool() -> None:
    """agent.yaml 的工具白名单必须指向真实注册的 tool id（先注册再调用）。"""
    agent = _load_yaml(REPO / "agents/hello_agent/agent.yaml")
    tool = _load_yaml(REPO / "tools_impl/mock_tools/tool.yaml")
    assert tool["id"] in agent["tools"]


# ── 3. 反例 witness：契约必须真的咬 ────────────────────────────────

def _valid_agent() -> dict:
    return _load_yaml(REPO / "agents/hello_agent/agent.yaml")


@pytest.mark.parametrize("mutate, reason", [
    (lambda a: a.pop("limitations"), "缺 limitations（不适用范围强制）"),
    (lambda a: a.pop("owner"), "缺 owner"),
    (lambda a: a.__setitem__("status", "L0_POC"), "status 用了成熟度值（双轴不许混淆）"),
    (lambda a: a.__setitem__("maturity", "L9"), "非法成熟度枚举"),
    (lambda a: a.__setitem__("version", "v1"), "非 semver 版本"),
    (lambda a: a.__setitem__("私自加的字段", 1), "未声明字段（additionalProperties=false）"),
    (lambda a: a["model"].__setitem__("profile", "glm-4.6"),
     "profile 写了具体模型名形态（含连字符/点号即拒——模型名只许进 Gateway 配置）"),
    (lambda a: a.__setitem__("limitations", []), "limitations 空列表（≥1 强制）"),
])
def test_agent_schema_bites_on_invalid(mutate, reason) -> None:
    bad = _valid_agent()
    mutate(bad)
    with pytest.raises(ValidationError):
        validate(bad, _load_schema("agent.schema.json"))
        pytest.fail(f"契约没咬住反例：{reason}")


@pytest.mark.parametrize(
    ("adapter", "contract_version"),
    [
        ("native_python", "flai.agent-layer.v1"),
        ("jerryagent_sidecar", "native.workflow.v1"),
    ],
)
def test_agent_schema_rejects_mismatched_execution_pair(
    adapter: str,
    contract_version: str,
) -> None:
    bad = _valid_agent()
    bad["execution"] = {
        "adapter": adapter,
        "contract_version": contract_version,
    }

    with pytest.raises(ValidationError):
        validate(bad, _load_schema("agent.schema.json"))


def _valid_tool() -> dict:
    return _load_yaml(REPO / "tools_impl/mock_tools/tool.yaml")


@pytest.mark.parametrize("mutate, reason", [
    (lambda t: t.pop("safety"), "缺 safety 三开关"),
    (lambda t: t.pop("runtime"), "缺 runtime"),
    (lambda t: t.__setitem__("type", "shell_script"), "非法工具类型"),
    (lambda t: t.__setitem__("entrypoint", "随便写的"), "非法 entrypoint 形态"),
    (lambda t: t["runtime"].__setitem__("timeout_seconds", 0), "超时=0"),
])
def test_tool_schema_bites_on_invalid(mutate, reason) -> None:
    bad = _valid_tool()
    mutate(bad)
    with pytest.raises(ValidationError):
        validate(bad, _load_schema("tool.schema.json"))
        pytest.fail(f"契约没咬住反例：{reason}")


# ── 4. 任务/事件契约与文档口径一致（十态/事件枚举抽检）─────────────

def test_task_schema_has_ten_states() -> None:
    schema = _load_schema("task.schema.json")
    states = schema["properties"]["status"]["enum"]
    assert set(states) == {
        "created", "queued", "validating", "running", "waiting_review",
        "parsing", "analyzing", "completed", "failed", "cancelled",
    }, "任务十态与任务书 §4.5 口径漂移"


def test_task_schema_accepts_inputs_property() -> None:
    """P1-2：params 型任务的 inputs 字段是真实 API 响应携带的键，task.schema.json
    必须声明它（additionalProperties=false 下缺声明 = 契约与实现互相说谎）。
    """
    schema = _load_schema("task.schema.json")
    sample = {
        "id": "task_001", "agent_id": "hello_agent", "agent_version": "0.1.0",
        "execution_adapter": "native_python",
        "execution_contract_version": "native.workflow.v1",
        "status": "queued", "created_by": "tester", "created_at": "2026-07-08T00:00:00Z",
        "inputs": {"name": "张三"},
    }
    validate(sample, schema)


def test_event_schema_smoke() -> None:
    schema = _load_schema("event.schema.json")
    sample = {
        "event_id": "evt_001", "task_id": "task_001", "agent_id": "hello_agent",
        "event_type": "task_created", "level": "info",
        "message": "任务已创建", "payload": {}, "created_at": "2026-07-08T00:00:00Z",
    }
    validate(sample, schema)
    bad = dict(sample, level="fatal")
    with pytest.raises(ValidationError):
        validate(bad, schema)
