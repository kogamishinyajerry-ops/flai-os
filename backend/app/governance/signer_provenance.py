"""Promotion 签发者来源值对象与校验（ADR-0019）。

HTTP 签发必须绑定提交时仍有效的精确认证会话；服务器 CLI 是显式、独立的
运维边界。历史记录只读兼容但永不被推断升级为可信来源。
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ..auth.service import (
    AuthenticatedSessionContext,
    current_auth_time,
    get_authenticated_session_by_hash,
)

AUTHENTICATED_SESSION = "authenticated_session"
SERVER_CLI = "server_cli"
LEGACY_UNVERIFIED = "legacy_unverified"


def _nonblank(value: Any) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _valid_user_id(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_session_hash(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(char in "0123456789abcdef" for char in value)
    )


@dataclass(frozen=True, slots=True)
class SignerContext:
    """调用适配层捕获的签发上下文；构造器把来源选择焊死在类型边界。"""

    source: str
    authenticated_session: AuthenticatedSessionContext | None = None
    operator_label: str | None = None

    @classmethod
    def from_authenticated_session(
        cls, session: AuthenticatedSessionContext
    ) -> "SignerContext":
        if not isinstance(session, AuthenticatedSessionContext):
            raise TypeError("authenticated_session 必须是 AuthenticatedSessionContext")
        return cls(source=AUTHENTICATED_SESSION, authenticated_session=session)

    @classmethod
    def from_server_cli(cls, operator_label: str) -> "SignerContext":
        if _nonblank(operator_label) is not True:
            raise ValueError("server_cli operator_label 不得为空白")
        return cls(source=SERVER_CLI, operator_label=operator_label.strip())


@dataclass(frozen=True, slots=True)
class VerifiedSigner:
    """已在当前事务连接上复核、可写入审计记录的规范化签发者。"""

    source: str
    confirmed_by: str
    user_id: int | None
    username: str | None
    session_hash: str | None
    verified_at: str

    def same_binding(self, other: Any) -> bool:
        """忽略复核时点，只比较不可变来源与身份绑定。"""
        return (
            isinstance(other, VerifiedSigner)
            and self.source == other.source
            and self.confirmed_by == other.confirmed_by
            and self.user_id == other.user_id
            and self.username == other.username
            and self.session_hash == other.session_hash
        )


def resolve_signer(
    conn: sqlite3.Connection, context: SignerContext
) -> VerifiedSigner | None:
    """在给定连接的当前数据库视图内验证来源，失败统一返回 None。"""
    if not isinstance(context, SignerContext):
        return None
    verified_at = current_auth_time()
    if (
        not isinstance(verified_at, datetime)
        or verified_at.tzinfo is None
        or verified_at.utcoffset() is None
    ):
        return None
    if context.source == AUTHENTICATED_SESSION:
        expected = context.authenticated_session
        if expected is None or context.operator_label is not None:
            return None
        current = get_authenticated_session_by_hash(
            conn,
            expected.token_hash,
            at=verified_at,
        )
        if current is None or current != expected:
            return None
        return VerifiedSigner(
            source=AUTHENTICATED_SESSION,
            confirmed_by=current.display_name,
            user_id=current.user_id,
            username=current.username,
            session_hash=current.token_hash,
            verified_at=verified_at.isoformat(),
        )
    if context.source == SERVER_CLI:
        if context.authenticated_session is not None or _nonblank(context.operator_label) is not True:
            return None
        return VerifiedSigner(
            source=SERVER_CLI,
            confirmed_by=context.operator_label.strip(),
            user_id=None,
            username=None,
            session_hash=None,
            verified_at=verified_at.isoformat(),
        )
    return None


def stored_signer_attests(record: dict[str, Any]) -> bool:
    """持久记录是否具有受支持且字段互斥严格的签发来源。"""
    source = record.get("signer_source")
    confirmed_by = record.get("confirmed_by")
    user_id = record.get("signer_user_id")
    username = record.get("signer_username")
    session_hash = record.get("signer_session_hash")
    if _nonblank(confirmed_by) is not True:
        return False
    if source == AUTHENTICATED_SESSION:
        return (
            _valid_user_id(user_id) is True
            and _nonblank(username) is True
            and _valid_session_hash(session_hash) is True
        )
    if source == SERVER_CLI:
        return user_id is None and username is None and session_hash is None
    # legacy_unverified、未知来源、缺列都不能为 L1 启动证明背书。
    return False


def public_promotion_record(record: dict[str, Any]) -> dict[str, Any]:
    """HTTP 脱敏投影：保留可审计身份轴，绝不返回 session hash。"""
    public = dict(record)
    session_hash = public.pop("signer_session_hash", None)
    public["signer_session_bound"] = (
        public.get("signer_source") == AUTHENTICATED_SESSION
        and _valid_session_hash(session_hash) is True
        and stored_signer_attests(record) is True
    )
    return public
