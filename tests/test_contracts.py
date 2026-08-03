"""M0 契约自校验门：全部 schema 合法 + 示例包过校验 + 反例必咬。

这是仓库的第一道 gate。它咬三类漂移：
1. contracts/*.schema.json 本身不是合法 JSON Schema（schema 腐坏）；
2. 示例包（hello_agent / mock_tools）与契约脱节（标准与样例互相说谎）；
3. 契约失去咬合力（反例 witness：缺必填字段/非法枚举必须 FAIL——
   「全绿」但反例不咬 = 假信心，见 docs/00 宪法第五条）。
"""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator, ValidationError, validate

REPO = Path(__file__).resolve().parents[1]
CONTRACTS = REPO / "contracts"

SCHEMA_FILES = [
    "agent.schema.json",
    "agent_shell.schema.json",
    "asset_draft_preview_request.schema.json",
    "asset_draft_bundle.schema.json",
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


def _valid_agent_shell_snapshot() -> dict:
    def facet(kind: str) -> dict:
        return {
            "id": kind,
            "total_count": 0,
            "task_count": 0,
            "conversation_count": 0,
            "unknown_launch_count": 0,
        }

    return {
        "schema_version": "agent_shell.v1",
        "source": {"kind": "registry_snapshot", "read_only": True},
        "summary": {
            "agent_count": 0,
            "work_type_count": 0,
            "domain_count": 0,
            "unresolved_reference_count": 0,
            "defaulted_clearance_count": 0,
            "mock_tool_reference_count": 0,
        },
        "facets": {
            "work_types": [],
            "domains": [],
            "launch_kinds": [facet("task"), facet("conversation"), facet("unknown")],
        },
        "agents": [],
        "diagnostics": [],
    }


def test_agent_shell_schema_accepts_minimal_read_only_snapshot() -> None:
    validate(_valid_agent_shell_snapshot(), _load_schema("agent_shell.schema.json"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["source"].__setitem__("read_only", False),
        lambda value: value.__setitem__("can_launch", True),
        lambda value: value["summary"].__setitem__("agent_count", -1),
        lambda value: value["facets"].__setitem__("launch_kinds", []),
        lambda value: value["facets"]["launch_kinds"][1].__setitem__("id", "task"),
    ],
)
def test_agent_shell_schema_bites_authority_and_shape_drift(mutate) -> None:
    invalid = _valid_agent_shell_snapshot()
    mutate(invalid)
    with pytest.raises(ValidationError):
        validate(invalid, _load_schema("agent_shell.schema.json"))


def _valid_asset_draft_request() -> dict:
    return {
        "schema_version": "asset_draft_preview_request.v1",
        "generalization": {
            "title": "入口边界复核",
            "trigger": "收到待计算的稳态算例",
            "desired_outcome": "形成可签认的复核清单",
            "inputs": ["边界条件表"],
            "outputs": ["复核清单"],
            "steps": ["核输入", "标缺口"],
            "evidence_requirements": ["保留原始位置"],
            "human_decision_points": ["冲突值由工程师确认"],
            "limitations": ["不适用于瞬态工况"],
        },
    }


def test_asset_draft_request_contract_accepts_editable_semantic_gaps() -> None:
    schema = _load_schema("asset_draft_preview_request.schema.json")
    validate(_valid_asset_draft_request(), schema)

    incomplete = _valid_asset_draft_request()
    incomplete["generalization"]["outputs"] = []
    incomplete["generalization"]["steps"] = []
    validate(incomplete, schema)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value.__setitem__("approved", True),
        lambda value: value["generalization"].__setitem__("inputs", [""]),
        lambda value: value["generalization"].__setitem__("steps", [1]),
    ],
)
def test_asset_draft_request_contract_rejects_authority_and_shape_drift(mutate) -> None:
    invalid = _valid_asset_draft_request()
    mutate(invalid)
    with pytest.raises(ValidationError):
        validate(invalid, _load_schema("asset_draft_preview_request.schema.json"))


def test_asset_draft_bundle_contract_locks_no_side_effects_and_no_recorded_decision() -> None:
    from backend.app.ontology.asset_builder import AssetDraftBuilder

    conversation = {
        "id": "conv_contract",
        "agent_id": "guide_agent",
        "status": "active",
        "messages": [
            {"id": "msg_1", "role": "user", "content": "核对入口边界", "file_ids": []}
        ],
    }
    bundle = AssetDraftBuilder().preview(
        conversation=conversation,
        generalization=_valid_asset_draft_request()["generalization"],
    )
    schema = _load_schema("asset_draft_bundle.schema.json")
    validate(bundle, schema)

    for field in (
        "writes_database",
        "executes_work",
        "registers_asset",
        "promotes_asset",
    ):
        invalid = deepcopy(bundle)
        invalid["effects"][field] = True
        with pytest.raises(ValidationError):
            validate(invalid, schema)

    invalid = deepcopy(bundle)
    invalid["review"]["decision_state"] = "approved"
    with pytest.raises(ValidationError):
        validate(invalid, schema)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda value: value["review"].__setitem__("ready", False),
        lambda value: value["review"].__setitem__("state", "not_ready"),
        lambda value: value["validation"].__setitem__("blocking_count", 1),
        lambda value: value["validation"].update(
            {
                "issues": [
                    {
                        "code": "fake.blocker",
                        "severity": "blocking",
                        "path": "/task_pattern/title",
                        "message": "不能在 ready 状态隐藏阻断项",
                    }
                ]
            }
        ),
    ],
)
def test_asset_draft_bundle_contract_rejects_fake_review_readiness(mutate) -> None:
    from backend.app.ontology.asset_builder import AssetDraftBuilder

    bundle = AssetDraftBuilder().preview(
        conversation={
            "id": "conv_contract_readiness",
            "agent_id": "guide_agent",
            "status": "active",
            "messages": [
                {
                    "id": "msg_1",
                    "role": "user",
                    "content": "核对入口边界",
                    "file_ids": [],
                }
            ],
        },
        generalization=_valid_asset_draft_request()["generalization"],
    )
    mutate(bundle)

    with pytest.raises(ValidationError):
        validate(bundle, _load_schema("asset_draft_bundle.schema.json"))


def test_asset_draft_bundle_contract_accepts_blocked_editable_draft() -> None:
    from backend.app.ontology.asset_builder import AssetDraftBuilder

    bundle = AssetDraftBuilder().preview(
        conversation={
            "id": "conv_contract_blocked",
            "agent_id": "guide_agent",
            "status": "active",
            "messages": [
                {
                    "id": "msg_1",
                    "role": "user",
                    "content": "核对入口边界",
                    "file_ids": [],
                }
            ],
        },
        generalization={
            **_valid_asset_draft_request()["generalization"],
            "outputs": [],
        },
    )

    validate(bundle, _load_schema("asset_draft_bundle.schema.json"))
    assert bundle["validation"]["state"] == "needs_revision"
    assert bundle["review"]["ready"] is False

    invalid = deepcopy(bundle)
    invalid["validation"]["issues"] = [
        {
            "code": "fake.warning",
            "severity": "warning",
            "path": "/generalization/inputs",
            "message": "不能用 warning 冒充 blocking issue",
        }
    ]
    with pytest.raises(ValidationError):
        validate(invalid, _load_schema("asset_draft_bundle.schema.json"))
