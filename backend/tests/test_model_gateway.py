"""ModelGateway 测试（docs/04_Model_Gateway_Standard.md / ADR-0003）：画像制 + fail-closed + 全量留痕。

覆盖：
- profile 未在 profiles.yaml 声明 → ProfileNotConfiguredError；
- 对应环境变量缺失 → ModelUpstreamError，且 model_calls 记 failed；
- httpx.MockTransport 假 200 → 成功且 model_calls 记 success（绝无真网络）；
- 上游 500 → ModelUpstreamError + model_calls 记 failed。

真实 backend/app/model_gateway/profiles.yaml 声明的 reasoning/fast 两个画像共用
FLAI_LLM_BASE_URL / FLAI_LLM_API_KEY / FLAI_LLM_MODEL_REASONING|FAST 三类环境变量，
本文件直接用这份真实交付件做测试（而非另造一份 profiles.yaml），环境变量全靠
monkeypatch 注入/清空，全程不触真实网络。
"""

from __future__ import annotations

import time

import httpx
import pytest

from backend.app.config import REPO_ROOT
from backend.app.core.errors import ModelUpstreamError, ProfileNotConfiguredError
from backend.app.model_gateway import gateway as gateway_mod
from backend.app.model_gateway.gateway import ModelGateway
from backend.app.storage import db as db_mod
from backend.app.storage import repos

PROFILES_PATH = REPO_ROOT / "backend" / "app" / "model_gateway" / "profiles.yaml"

_ENV_VARS = ("FLAI_LLM_BASE_URL", "FLAI_LLM_API_KEY", "FLAI_LLM_MODEL_REASONING", "FLAI_LLM_MODEL_FAST")


@pytest.fixture(autouse=True)
def _clean_llm_env(monkeypatch):
    """每个测试前清空 LLM 相关环境变量，避免宿主机真实设置串扰测试。"""
    for var in _ENV_VARS:
        monkeypatch.delenv(var, raising=False)


def _make_conn_factory(tmp_path, name: str = "gw.db"):
    db_path = tmp_path / name
    db_mod.init_db(db_path)
    return db_path, (lambda: db_mod.get_conn(db_path))


# ── profile 未配置 ─────────────────────────────────────────────────────────

def test_chat_profile_not_configured_raises() -> None:
    gateway = ModelGateway(PROFILES_PATH)
    with pytest.raises(ProfileNotConfiguredError):
        gateway.chat("no_such_profile", [{"role": "user", "content": "hi"}])


# ── env 缺失 → ModelUpstreamError + model_calls 记 failed ──────────────────

def test_chat_missing_env_raises_model_upstream_error_and_records_failed(tmp_path) -> None:
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_a")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_a")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert calls[0]["model_profile"] == "reasoning"
    assert calls[0]["error_message"]


def test_missing_env_raises_model_config_error_subclass(tmp_path) -> None:
    """缺 env → ModelConfigError（永久配置错），且它是 ModelUpstreamError 子类
    （既有 except 全兼容）；上游 500（临时故障）则是 ModelUpstreamError 但**非**
    ModelConfigError——分流的语义基石（PM 战略审 top 的诚实文案依赖它）。"""
    from backend.app.core.errors import ModelConfigError

    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelConfigError):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_cfg")
    # 子类关系：既有 except ModelUpstreamError 仍捕获
    try:
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}])
    except ModelUpstreamError as exc:
        assert isinstance(exc, ModelConfigError)
    else:
        raise AssertionError("缺 env 必须抛异常")


def test_upstream_500_is_not_config_error(tmp_path, monkeypatch) -> None:
    """env 已配 + 上游 500 → ModelUpstreamError 但**不是** ModelConfigError
    （否则会被误判为永久配置错、误导为不可重试）。"""
    from backend.app.core.errors import ModelConfigError

    monkeypatch.setenv("FLAI_LLM_BASE_URL", "https://fake-llm.internal")
    monkeypatch.setenv("FLAI_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FLAI_LLM_MODEL_REASONING", "glm-mock")
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    def fake_post(url, *, json, headers, timeout):
        return httpx.Response(500, text="upstream boom", request=httpx.Request("POST", url))

    monkeypatch.setattr(gateway_mod.httpx, "post", fake_post)
    with pytest.raises(ModelUpstreamError) as ei:
        gateway.chat("reasoning", [{"role": "user", "content": "x"}], task_id="task_500")
    assert not isinstance(ei.value, ModelConfigError)


def test_embed_missing_env_raises_and_records_failed(tmp_path) -> None:
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError):
        gateway.embed("reasoning", "待向量化文本", task_id="task_embed")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_embed")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"


# ── httpx.MockTransport 假 200 → 成功且 model_calls 记 success ──────────────

def test_chat_success_via_mock_transport_records_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLAI_LLM_BASE_URL", "https://fake-llm.internal")
    monkeypatch.setenv("FLAI_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FLAI_LLM_MODEL_REASONING", "glm-mock")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/chat/completions"
        assert request.headers.get("authorization") == "Bearer fake-key"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "你好，世界"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3},
            },
        )

    def fake_post(url, *, json, headers, timeout):
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json, headers=headers)

    monkeypatch.setattr(gateway_mod.httpx, "post", fake_post)

    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    result = gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_b")
    assert result["content"] == "你好，世界"
    assert result["model_name"] == "glm-mock"
    assert result["token_usage"] == {"prompt_tokens": 5, "completion_tokens": 3}

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_b")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "success"
    assert calls[0]["model_name"] == "glm-mock"


# ── 上游 500 → ModelUpstreamError + model_calls 记 failed ──────────────────

def test_chat_upstream_500_raises_model_upstream_error_and_records_failed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("FLAI_LLM_BASE_URL", "https://fake-llm.internal")
    monkeypatch.setenv("FLAI_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FLAI_LLM_MODEL_REASONING", "glm-mock")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="内部服务错误")

    def fake_post(url, *, json, headers, timeout):
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json, headers=headers)

    monkeypatch.setattr(gateway_mod.httpx, "post", fake_post)

    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_c")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_c")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert "500" in calls[0]["error_message"]


def test_conn_factory_none_skips_db_write() -> None:
    """conn_factory=None 时跳过落库（供库内自测），env 缺失仍应 fail-closed 抛错。"""
    gateway = ModelGateway(PROFILES_PATH)
    with pytest.raises(ModelUpstreamError):
        gateway.chat("reasoning", [{"role": "user", "content": "hi"}])


# ── P2-4：上游 200 但 body 畸形 → ModelUpstreamError + model_calls 记 failed ──


def _mock_env_and_post(monkeypatch, handler) -> None:
    monkeypatch.setenv("FLAI_LLM_BASE_URL", "https://fake-llm.internal")
    monkeypatch.setenv("FLAI_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FLAI_LLM_MODEL_REASONING", "glm-mock")

    def fake_post(url, *, json, headers, timeout):
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json, headers=headers)

    monkeypatch.setattr(gateway_mod.httpx, "post", fake_post)


def test_chat_upstream_200_non_json_raises_and_records_failed(tmp_path, monkeypatch) -> None:
    """上游 200 但 body 是 HTML（如网关错误页）——此前 resp.json() 异常裸逃，
    model_calls 无记录；修后必须折叠为 ModelUpstreamError 且 model_calls 记 failed。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="<html><body>Bad Gateway impersonating 200</body></html>")

    _mock_env_and_post(monkeypatch, handler)
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_html200")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_html200")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert "不可解析" in calls[0]["error_message"]


def test_chat_upstream_200_top_level_not_object_raises_and_records_failed(tmp_path, monkeypatch) -> None:
    """上游 200 且是合法 JSON 但顶层不是 object（形状漂移）——同样 fail-closed 留痕。"""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=["not", "an", "object"])

    _mock_env_and_post(monkeypatch, handler)
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_list200")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_list200")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert "形状漂移" in calls[0]["error_message"]


def test_chat_upstream_200_choices_shape_drift_raises_and_records_failed(tmp_path, monkeypatch) -> None:
    """上游 200、顶层是 object，但 choices 元素非 object（字段级形状漂移）——
    提取阶段异常不得裸逃，折叠为 ModelUpstreamError + model_calls 记 failed。
    """
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": ["驴唇不对马嘴"]})

    _mock_env_and_post(monkeypatch, handler)
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_drift200")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_drift200")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"


# ── 上游 200 但 content 为空 → ModelUpstreamError（ADR-0013 fail-closed）────

def test_chat_empty_content_200_raises_and_records_failed(tmp_path, monkeypatch) -> None:
    """空回答绝不记 success：choices 结构合法但 content 为 null/空串的 200 响应，
    此前被记 status=success（把「无回答」伪装成成功调用）——现折叠为
    ModelUpstreamError 走统一 failed 留痕。"""
    monkeypatch.setenv("FLAI_LLM_BASE_URL", "https://fake-llm.internal")
    monkeypatch.setenv("FLAI_LLM_API_KEY", "fake-key")
    monkeypatch.setenv("FLAI_LLM_MODEL_REASONING", "glm-mock")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": None}, "finish_reason": "stop"}]},
        )

    def fake_post(url, *, json, headers, timeout):
        transport = httpx.MockTransport(handler)
        with httpx.Client(transport=transport) as client:
            return client.post(url, json=json, headers=headers)

    monkeypatch.setattr(gateway_mod.httpx, "post", fake_post)

    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError, match="content 为空"):
        gateway.chat("reasoning", [{"role": "user", "content": "你好"}], task_id="task_empty")

    conn = db_mod.get_conn(db_path)
    calls = repos.list_model_calls(conn, "task_empty")
    conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
    assert "content 为空" in calls[0]["error_message"]


# ── 可恢复上游故障有限重试（总尝试次数固定为 2）──────────────────────────

@pytest.mark.parametrize("first_failure", ["503", "transport"])
def test_chat_retryable_first_failure_then_success_records_one_success(
    tmp_path, monkeypatch, first_failure: str
) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            if first_failure == "503":
                return httpx.Response(503, text="上游暂不可用")
            raise httpx.ConnectError("模拟传输中断", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "重试成功"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2},
            },
        )

    _mock_env_and_post(monkeypatch, handler)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    result = gateway.chat(
        "reasoning", [{"role": "user", "content": "请重试"}], task_id="task_retry_success"
    )

    assert result["content"] == "重试成功"
    assert attempts == 2
    assert sleeps == [0.5]
    conn = db_mod.get_conn(db_path)
    try:
        calls = repos.list_model_calls(conn, "task_retry_success")
    finally:
        conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "success"


def test_chat_continuous_503_retries_once_and_records_one_failed(tmp_path, monkeypatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, text="持续不可用")

    _mock_env_and_post(monkeypatch, handler)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError, match="status=503"):
        gateway.chat(
            "reasoning", [{"role": "user", "content": "请重试"}], task_id="task_retry_failed"
        )

    assert attempts == 2
    assert sleeps == [0.5]
    conn = db_mod.get_conn(db_path)
    try:
        calls = repos.list_model_calls(conn, "task_retry_failed")
    finally:
        conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"


def test_chat_401_does_not_retry_and_records_one_failed(tmp_path, monkeypatch) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(401, text="未授权")

    _mock_env_and_post(monkeypatch, handler)
    sleeps: list[float] = []
    monkeypatch.setattr(time, "sleep", sleeps.append)
    db_path, conn_factory = _make_conn_factory(tmp_path)
    gateway = ModelGateway(PROFILES_PATH, conn_factory=conn_factory)

    with pytest.raises(ModelUpstreamError, match="status=401"):
        gateway.chat(
            "reasoning", [{"role": "user", "content": "不要重试"}], task_id="task_401"
        )

    assert attempts == 1
    assert sleeps == []
    conn = db_mod.get_conn(db_path)
    try:
        calls = repos.list_model_calls(conn, "task_401")
    finally:
        conn.close()
    assert len(calls) == 1
    assert calls[0]["status"] == "failed"
