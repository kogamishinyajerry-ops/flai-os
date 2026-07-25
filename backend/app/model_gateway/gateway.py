"""Model Gateway：Agent 只声明 profile，具体模型名/端点经环境变量注入（docs/04）。

宪法/ADR-0003 fail-closed 条款：
- profile 未在 profiles.yaml 声明 → ``ProfileNotConfiguredError``。
- 对应环境变量缺失 / 上游网络错误 / 上游非 2xx → ``ModelUpstreamError``。
- profile 已解析但能力尚未接入 → ``ModelCapabilityUnavailableError``（非临时故障）。
- 任何路径（成败）都必须落一条 ``model_calls`` 记录（"无事件=没发生"，docs/04 §7
  违规判定）——绝不静默降级、绝不编造回答顶替。

V0.1 只落地 ``provider: openai_compatible``，走 OpenAI 兼容 Chat/Completions 报文形态；
真实内网端点协议/鉴权方式待内网侦察，此处 profiles.yaml 只声明环境变量名占位。
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import httpx
import yaml
from jsonschema import validate

from ..config import CONTRACTS_DIR
from ..core.errors import (
    ModelCapabilityUnavailableError,
    ModelConfigError,
    ModelUpstreamError,
    ProfileNotConfiguredError,
)
from ..storage import repos

_PROFILE_SCHEMA_PATH = CONTRACTS_DIR / "model_profile.schema.json"

_RESPONSE_SUMMARY_LIMIT = 200


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _summarize(text: Any) -> str | None:
    """摘要化响应内容，避免落库全量敏感 payload（docs/04 §6 request/response_summary 语义）。"""
    if text is None:
        return None
    s = str(text)
    return s if len(s) <= _RESPONSE_SUMMARY_LIMIT else s[:_RESPONSE_SUMMARY_LIMIT] + "…"


class ModelGateway:
    """Model Gateway 唯一入口：chat/embed/vision 三方法 + 全量留痕（docs/04）。"""

    def __init__(self, profiles_path: str | Path, conn_factory: Callable[[], Any] | None = None) -> None:
        self.profiles_path = Path(profiles_path)
        self.conn_factory = conn_factory
        self._profiles: dict[str, dict[str, Any]] = {}
        self._load_profiles()

    def _load_profiles(self) -> None:
        schema = json.loads(_PROFILE_SCHEMA_PATH.read_text(encoding="utf-8"))
        raw = yaml.safe_load(self.profiles_path.read_text(encoding="utf-8")) or []
        profiles: dict[str, dict[str, Any]] = {}
        for entry in raw:
            validate(entry, schema)
            profiles[entry["profile_id"]] = entry
        self._profiles = profiles

    # ── 内部：profile 解析 + env 校验（fail-closed） ────────────────────

    def _resolve(self, profile: str) -> tuple[dict[str, Any], str, str | None, str]:
        """解析 profile 配置 + 环境变量，返回 (cfg, base_url, api_key, model_name)。

        env 缺失一律抛 ``ModelConfigError``（ModelUpstreamError 子类，宪法 fail-closed
        条款绝不静默降级；子类让调用方能区分「永久配置错」与「临时上游故障」）。
        """
        cfg = self._profiles.get(profile)
        if cfg is None:
            raise ProfileNotConfiguredError(f"未在 profiles.yaml 声明的 model profile：{profile}")

        base_url_env = cfg.get("base_url_env")
        base_url = os.environ.get(base_url_env, "") if base_url_env else ""
        if base_url_env and not base_url:
            raise ModelConfigError(f"缺少环境变量 {base_url_env}（profile={profile} 的 base_url，见 docs/04）")

        api_key_env = cfg.get("api_key_env")
        api_key = os.environ.get(api_key_env) if api_key_env else None
        if api_key_env and not api_key:
            raise ModelConfigError(f"缺少环境变量 {api_key_env}（profile={profile} 的 api_key，见 docs/04）")

        model_env = cfg.get("model_env")
        if model_env:
            model_name = os.environ.get(model_env, "")
            if not model_name:
                raise ModelConfigError(f"缺少环境变量 {model_env}（profile={profile} 的模型名，见 docs/04）")
        else:
            model_name = cfg["model"]

        return cfg, base_url, api_key, model_name

    def _record(
        self,
        *,
        task_id: str | None,
        agent_id: str | None,
        profile: str,
        model_name: str | None,
        status: str,
        request_summary: str | None,
        response_summary: str | None,
        error_message: str | None,
        token_usage: dict[str, Any] | None,
        conversation_id: str | None = None,
    ) -> None:
        """无论成败都记一条 model_calls（docs/04 §7：存在调用未落 model_calls 即判违规）。

        conn_factory 为 None 时跳过落库（供库内自测使用）。connection 用后即关闭，
        遵循 ADR-0008「连接 per-operation」的存储层约定。
        task_id / conversation_id 二选一携带（job 路径带 task_id，导引会话带
        conversation_id）——两条运行时的模型调用都必须可归因（ADR-0013）。
        """
        if self.conn_factory is None:
            return
        conn = self.conn_factory()
        try:
            repos.record_model_call(
                conn,
                task_id=task_id,
                conversation_id=conversation_id,
                agent_id=agent_id,
                model_profile=profile,
                model_name=model_name,
                status=status,
                request_summary=request_summary,
                response_summary=response_summary,
                error_message=error_message,
                token_usage_json=token_usage,
            )
        finally:
            conn.close()

    def _post(self, base_url: str, path: str, payload: dict[str, Any], api_key: str | None) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        for attempt in range(2):
            try:
                resp = httpx.post(f"{base_url}{path}", json=payload, headers=headers, timeout=60)
            except httpx.TransportError as exc:
                if attempt == 0:
                    time.sleep(0.5)
                    continue
                raise ModelUpstreamError(f"上游网络错误：{exc}") from exc
            except httpx.HTTPError as exc:
                # 非传输类 HTTPError 保持原有错误映射，但不属于可重试范围。
                raise ModelUpstreamError(f"上游网络错误：{exc}") from exc

            if resp.status_code in {502, 503, 504} and attempt == 0:
                time.sleep(0.5)
                continue
            break

        if not (200 <= resp.status_code < 300):
            raise ModelUpstreamError(f"上游返回非 2xx（status={resp.status_code}）：{resp.text[:500]}")
        # P2-4：上游 200 但 body 畸形（HTML 错误页/非 JSON/顶层非 object）不得让
        # 解析异常裸逃——统一折叠为 ModelUpstreamError，由调用方的 except 落
        # model_calls failed 行（成败皆留痕）。
        try:
            data = resp.json()
        except Exception as exc:
            raise ModelUpstreamError(
                f"上游返回 200 但响应不可解析为 JSON：{resp.text[:200]!r}"
            ) from exc
        if not isinstance(data, dict):
            raise ModelUpstreamError(
                f"上游返回 200 但响应顶层不是 object（实得 {type(data).__name__}），响应形状漂移"
            )
        return data

    # ── 对外三方法（docs/04 §3）─────────────────────────────────────────

    def chat(
        self,
        profile: str,
        messages: list[dict[str, Any]],
        *,
        task_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model_name: str | None = None
        request_summary = f"chat：{len(messages)} 条消息"
        try:
            cfg, base_url, api_key, model_name = self._resolve(profile)
            payload: dict[str, Any] = {"model": model_name, "messages": messages}
            for key in ("max_tokens", "temperature"):
                value = kwargs.get(key, cfg.get(key))
                if value is not None:
                    payload[key] = value
            data = self._post(base_url, "/chat/completions", payload, api_key)
            try:
                choice = (data.get("choices") or [{}])[0]
                message = choice.get("message") if isinstance(choice.get("message"), dict) else {}
                content = message.get("content")
                token_usage = data.get("usage")
                result = {
                    "content": content,
                    "token_usage": token_usage,
                    "model_name": model_name,
                    "finish_reason": choice.get("finish_reason"),
                }
            except (AttributeError, IndexError, KeyError, TypeError) as exc:
                # P2-4：上游 200 但字段形状漂移（choices 元素非 object 等）——
                # 折叠为 ModelUpstreamError 走下方统一留痕路径，绝不裸逃。
                raise ModelUpstreamError(f"上游返回 200 但 chat 响应形状漂移：{exc}") from exc
            if not isinstance(content, str) or not content.strip():
                # 审计硬化（ADR-0013）：上游 200 但 content 为空/非文本——若记
                # success 就是把「无回答」伪装成成功调用（fail-open）。按上游失败
                # 处理，走统一 failed 留痕；上层各自的空内容防线保留作纵深。
                raise ModelUpstreamError("上游返回 200 但 chat content 为空——按上游失败处理，不把空回答记 success")
        except (ProfileNotConfiguredError, ModelUpstreamError) as exc:
            self._record(
                task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
                profile=profile, model_name=model_name,
                status="failed", request_summary=request_summary, response_summary=None,
                error_message=str(exc), token_usage=None,
            )
            raise

        self._record(
            task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
            profile=profile, model_name=model_name,
            status="success", request_summary=request_summary,
            response_summary=_summarize(result["content"]), error_message=None,
            token_usage=result["token_usage"],
        )
        return result

    def embed(
        self,
        profile: str,
        text: str,
        *,
        task_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model_name: str | None = None
        request_summary = f"embed：{len(text)} 字符文本"
        try:
            cfg, base_url, api_key, model_name = self._resolve(profile)
            del cfg  # embed 暂无额外可覆盖参数
            payload = {"model": model_name, "input": text}
            data = self._post(base_url, "/embeddings", payload, api_key)
            try:
                vector = (data.get("data") or [{}])[0].get("embedding", [])
                result = {"vector": vector, "model_name": model_name}
            except (AttributeError, IndexError, KeyError, TypeError) as exc:
                raise ModelUpstreamError(f"上游返回 200 但 embed 响应形状漂移：{exc}") from exc
        except (ProfileNotConfiguredError, ModelUpstreamError) as exc:
            self._record(
                task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
                profile=profile, model_name=model_name,
                status="failed", request_summary=request_summary, response_summary=None,
                error_message=str(exc), token_usage=None,
            )
            raise

        self._record(
            task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
            profile=profile, model_name=model_name,
            status="success", request_summary=request_summary,
            response_summary=f"向量维度={len(result['vector'])}", error_message=None,
            token_usage=None,
        )
        return result

    def vision(
        self,
        profile: str,
        image_path: str,
        prompt: str,
        *,
        task_id: str | None = None,
        conversation_id: str | None = None,
        agent_id: str | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        model_name: str | None = None
        request_summary = f"vision：{prompt[:80]}"
        # fail-closed（红线）：openai_compatible 的 vision 报文形态未与内网端点对齐，
        # V0.1 若按占位协议（image_path 字段）发包，上游必然不认——发出即假请求。
        # 与其 fail-open 发一个必败的占位报文，不如显式记 failed 留痕后 raise，
        # 让调用方诚实面对「视觉能力未实装」，绝不让上游误答被当成真实视觉结论。
        try:
            cfg, base_url, api_key, model_name = self._resolve(profile)
            del cfg, base_url, api_key
            raise ModelCapabilityUnavailableError(
                "vision 能力未实装：openai_compatible 报文形态待内网侦察，"
                "V0.1 不发出占位请求（fail-closed，防假视觉结论）"
            )
        except (
            ModelCapabilityUnavailableError,
            ModelUpstreamError,
            ProfileNotConfiguredError,
        ) as exc:
            self._record(
                task_id=task_id, conversation_id=conversation_id, agent_id=agent_id,
                profile=profile, model_name=model_name,
                status="failed", request_summary=request_summary, response_summary=None,
                error_message=str(exc), token_usage=None,
            )
            raise
