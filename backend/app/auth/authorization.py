"""Agent manifest permissions 与认证账户角色的统一、默认拒绝判据。"""

from __future__ import annotations

import sqlite3
from typing import Any


_VISIBILITY_ROLES = {
    "admin_only": frozenset({"admin"}),
    "department_trial": frozenset({"admin", "agent_developer"}),
    "all": frozenset({"admin", "agent_developer", "business_user"}),
}
_KNOWN_ROLES = frozenset({"admin", "agent_developer", "business_user"})
_CALLABLE_AGENT_STATUSES = frozenset({"draft", "trial", "released"})


def role_can_access_agent(agent: dict[str, Any], role: str) -> bool:
    """角色必须同时满足 visibility 上界与 allowed_roles 明细；坏声明一律拒绝。"""
    permissions = agent.get("permissions") or {}
    if not isinstance(permissions, dict) or set(permissions) != {
        "visibility",
        "allowed_roles",
    }:
        return False
    allowed_roles = permissions.get("allowed_roles")
    visible_roles = _VISIBILITY_ROLES.get(permissions.get("visibility"))
    return (
        isinstance(allowed_roles, list)
        and bool(allowed_roles)
        and all(isinstance(item, str) and item in _KNOWN_ROLES for item in allowed_roles)
        and len(allowed_roles) == len(set(allowed_roles))
        and visible_roles is not None
        and role in _KNOWN_ROLES
        and role in visible_roles
        and role in allowed_roles
    )


def agent_is_callable(agent: dict[str, Any], *, mode: str | None = None) -> bool:
    """运行入口只接受 schema 定义的可调用状态，并可锁定 workflow.mode。"""
    if agent.get("status") not in _CALLABLE_AGENT_STATUSES:
        return False
    if mode is None:
        return True
    workflow = agent.get("workflow")
    return isinstance(workflow, dict) and workflow.get("mode") == mode


def current_actor_matches(
    conn: sqlite3.Connection, *, username: str, expected_role: str
) -> dict[str, Any] | None:
    """事务内重读主体；停用、缺失或角色变化均视作授权已失效。"""
    row = conn.execute(
        "SELECT id, username, display_name, role, is_active FROM users WHERE username = ?",
        (username,),
    ).fetchone()
    if row is None or row["is_active"] != 1 or row["role"] != expected_role:
        return None
    return dict(row)
