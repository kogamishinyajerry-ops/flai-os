"""life_guide_agent 待审候选(generalization_draft)透传链路测试。

/demo 草稿卡片接线(选项 A)的后端契约:
1. 模型回复带字段齐全的 <<DRAFT>> 块 → /messages 响应透传 generalization_draft,
   落库消息正文剥离草稿块;
2. 模型继续追问(无草稿块) → generalization_draft 为 None;
3. 草稿块字段残缺 → fail-closed,generalization_draft 为 None,绝不透出半份候选;
4. 候选只在响应级透传,绝不落库(人审唯一签发:候选不入库)。

不用 LLM:stub gateway 注入方式同 test_m6(app.state.conversation_service
.model_gateway = stub);其余链路(登录/鉴权/Registry/事务落库)全真。
"""

from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

_DRAFT_FIELDS = {
    "title": "家常红烧肉(带皮五花肉版)",
    "trigger": "家里想吃红烧肉 + 有 2 小时 + 有炒锅和炖锅",
    "desired_outcome": "一盘 4-6 人份、能咬动、咸淡合适的红烧肉",
    "inputs": ["带皮五花肉 500-700g", "冰糖", "生抽老抽料酒"],
    "outputs": ["一盘红烧肉"],
    "steps": ["切块焯水", "炒糖色到琥珀色下肉", "小火炖 50 分钟", "尝咸淡收汁"],
    "evidence_requirements": ["糖色琥珀色", "尝咸淡通过"],
    "human_decision_points": ["尝咸淡必须人工"],
    "limitations": ["不适用高压锅", "不适用其他肉类"],
}

_DRAFT_BLOCK = (
    "<<DRAFT>>\n" + json.dumps(_DRAFT_FIELDS, ensure_ascii=False) + "\n<<END>>"
)
_REPLY_WITH_DRAFT = f"素材够了,我来投影草稿。\n{_DRAFT_BLOCK}\n审核权在你手里。"
_REPLY_FOLLOWUP = "两个关键问题:糖焦具体是哪一步?成功证据还有什么?"


class _CannedStub:
    """固定回复的 stub gateway;签名对齐 workflow 直连 model_gateway.chat。"""

    def __init__(self, reply: str) -> None:
        self.reply = reply

    def chat(
        self, profile: str, messages: list[dict[str, Any]], **kwargs: Any
    ) -> dict[str, Any]:
        return {
            "content": self.reply,
            "token_usage": None,
            "model_name": "stub",
            "finish_reason": "stop",
        }


def _open_life_conversation(client: TestClient) -> str:
    resp = client.post("/api/conversations", json={"agent_id": "life_guide_agent"})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_draft_passthrough_in_messages_response(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(_REPLY_WITH_DRAFT)
    conv_id = _open_life_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "上周六我做了红烧肉,糖焦了重来一次,女儿说好吃。"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()

    draft = body.get("generalization_draft")
    assert isinstance(draft, dict), "字段齐全的草稿必须透传到响应"
    assert draft == _DRAFT_FIELDS
    # 正文剥离草稿块:工程师看到的文字不含结构块原文
    assert "<<DRAFT>>" not in body["message"]["content"]
    assert "审核权在你手里" in body["message"]["content"]


def test_followup_round_yields_no_draft(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(_REPLY_FOLLOWUP)
    conv_id = _open_life_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "我做了红烧肉。"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json().get("generalization_draft") is None


def test_incomplete_draft_is_closed_not_leaked(app_env) -> None:
    client, app = app_env
    incomplete = {k: v for k, v in _DRAFT_FIELDS.items() if k != "limitations"}
    reply = (
        "我先投影一版。\n<<DRAFT>>\n"
        + json.dumps(incomplete, ensure_ascii=False)
        + "\n<<END>>"
    )
    app.state.conversation_service.model_gateway = _CannedStub(reply)
    conv_id = _open_life_conversation(client)

    resp = client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "我做了红烧肉,过程略。"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # fail-closed:残缺草稿绝不透出,回到对话追问
    assert body.get("generalization_draft") is None
    assert "候选字段还不齐全" in body["message"]["content"]


def test_draft_is_response_only_never_persisted(app_env) -> None:
    client, app = app_env
    app.state.conversation_service.model_gateway = _CannedStub(_REPLY_WITH_DRAFT)
    conv_id = _open_life_conversation(client)
    client.post(
        f"/api/conversations/{conv_id}/messages",
        json={"content": "上周六我做了红烧肉。"},
    )

    conv = client.get(f"/api/conversations/{conv_id}")
    assert conv.status_code == 200
    persisted = conv.json()
    assert "generalization_draft" not in persisted, "会话行不得携带候选草稿"
    for msg in persisted["messages"]:
        assert "generalization_draft" not in msg, "消息行不得携带候选草稿"
        assert "<<DRAFT>>" not in msg["content"]
        # 草稿字段值不得以任何形式渗进落库正文
        assert "家常红烧肉(带皮五花肉版)" not in msg["content"]
