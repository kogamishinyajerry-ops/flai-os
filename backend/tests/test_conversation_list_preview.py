"""会话列表投影 first_user_message（E-4 侧栏标题人话化的服务端数据面）。

背景：侧栏历史会话标题此前只能回退「与 X 的对话」（雷同），或依赖
GuidePage 拉过全量后的内存缓存（刷新即失效）。列表投影 additive 增加
first_user_message=首条 role=user 消息的服务端截断预览（120 字符），前端
再截 18 字；无用户消息 → null，绝不编造。

权限面论证（ADR-0019）：列表端点本就支持 created_by 过滤（会话发起人的
服务端派生 display_name），预览只在列表行内带出，可见性与打开会话读全文
（GET /conversations/{id}，同样只要求登录态）同权——不新增任何越权面。
分级闸（ADR-0025 fail-closed）：闸作用于任务派生内容（tool_runs/
model_calls/events/error_message 等外部真源读回的数据），会话消息是用户
本人键入的一手输入，不在闸的内容键清单内；预览与全文读同一路径语义，
无绕过。
"""

from __future__ import annotations

from typing import Any, Iterator

import pytest
from fastapi.testclient import TestClient

from conftest import TEST_DISPLAY_NAME, login, seed_user


class _CannedStub:
    """返回固定 assistant 文本的 stub gateway（口径同 test_m6_guide_conversation）。"""

    def chat(self, profile: str, messages: list[dict[str, Any]], **kwargs: Any) -> dict[str, Any]:
        return {
            "content": "好的，我记下了。",
            "token_usage": None,
            "model_name": "stub",
            "finish_reason": "stop",
        }


@pytest.fixture()
def client(app_env) -> Iterator[TestClient]:
    c, _ = app_env
    yield c


def _open_conversation(client: TestClient) -> str:
    resp = client.post("/api/conversations", json={"agent_id": "guide_agent"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def _post_user_message(client: TestClient, conv_id: str, content: str) -> None:
    resp = client.post(
        f"/api/conversations/{conv_id}/messages", json={"content": content}
    )
    assert resp.status_code == 200, resp.text


def _list_row(client: TestClient, conv_id: str) -> dict[str, Any]:
    rows = client.get("/api/conversations").json()
    matches = [r for r in rows if r["id"] == conv_id]
    assert len(matches) == 1
    return matches[0]


def test_list_projection_includes_first_user_message(client: TestClient, app_env) -> None:
    _, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub()
    conv_id = _open_conversation(client)
    _post_user_message(client, conv_id, "帮我评估一下这个机翼方案的颤振边界")

    row = _list_row(client, conv_id)
    assert row["first_user_message"] == "帮我评估一下这个机翼方案的颤振边界"


def test_list_projection_stays_on_first_user_message_after_more_rounds(
    client: TestClient, app_env
) -> None:
    """多轮对话后仍取首条 user 消息（不是最新一条）。"""
    _, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub()
    conv_id = _open_conversation(client)
    _post_user_message(client, conv_id, "第一句话才是标题来源")
    _post_user_message(client, conv_id, "第二句不应顶掉标题")

    row = _list_row(client, conv_id)
    assert row["first_user_message"] == "第一句话才是标题来源"


def test_list_projection_null_when_no_user_message(client: TestClient) -> None:
    """新建的零消息会话 → first_user_message 为 None（绝不编造）。"""
    conv_id = _open_conversation(client)
    row = _list_row(client, conv_id)
    assert row["first_user_message"] is None


def test_list_projection_truncates_at_120_chars(client: TestClient, app_env) -> None:
    _, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub()
    conv_id = _open_conversation(client)
    long_content = "超长需求描述" * 30  # 180 字符
    _post_user_message(client, conv_id, long_content)

    row = _list_row(client, conv_id)
    assert row["first_user_message"] == long_content[:120]
    assert len(row["first_user_message"]) == 120


def test_list_projection_preview_respects_created_by_filter(
    client: TestClient, app_env
) -> None:
    """归属断言：created_by 过滤视图下乙用户看不到甲的会话及其预览。"""
    _, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub()
    conv_id = _open_conversation(client)  # 发起人=TEST_DISPLAY_NAME（登录态派生）
    _post_user_message(client, conv_id, "甲的私密需求草稿")

    seed_user(app.state.db_path, username="user_b", display_name="用户乙", password="pw-b-12345")
    login(client, username="user_b", password="pw-b-12345")

    mine = client.get("/api/conversations", params={"created_by": "用户乙"}).json()
    assert all(r["created_by"] == "用户乙" for r in mine)
    assert conv_id not in {r["id"] for r in mine}

    theirs = client.get(
        "/api/conversations", params={"created_by": TEST_DISPLAY_NAME}
    ).json()
    assert theirs == [], "display_name 过滤不能越过当前 username 的 owner 边界"
