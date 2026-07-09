"""任务十态状态机（docs/05_Task_Event_Standard.md §1-2 唯一真相源）。

转移表严格镜像 docs/05 第 2 节合法转移表——该表本身无歧义（逐行给出 From/合法 To），
故不采用 M1 接口契约里"若 docs/05 有歧义"时给的兜底简化表；兜底表与 docs/05 的差异
（缺 running/parsing/analyzing 的 cancelled 出边、缺 parsing→running 回边、多出
running→completed 直转）已在本次交付说明里显式报告，详见调用方返回值。
"""

from __future__ import annotations

from .errors import IllegalTransitionError

# 十态
STATES: frozenset[str] = frozenset(
    {
        "created",
        "queued",
        "validating",
        "running",
        "parsing",
        "analyzing",
        "waiting_review",
        "completed",
        "failed",
        "cancelled",
    }
)

# 合法转移表：严格镜像 docs/05 第 2 节。
TRANSITIONS: dict[str, frozenset[str]] = {
    "created": frozenset({"queued", "cancelled"}),
    "queued": frozenset({"validating", "cancelled"}),
    "validating": frozenset({"running", "failed", "cancelled"}),
    "running": frozenset({"parsing", "analyzing", "waiting_review", "failed", "cancelled"}),
    "parsing": frozenset({"analyzing", "running", "failed", "cancelled"}),
    "analyzing": frozenset({"waiting_review", "completed", "failed", "cancelled"}),
    # waiting_review 只能由人工放行动作转出（review_approved -> completed /
    # review_rejected -> failed），禁止任何自动化路径，docs/05 §2 强制规则。
    "waiting_review": frozenset({"completed", "failed"}),
    # 终态：无出边。
    "completed": frozenset(),
    "failed": frozenset(),
    "cancelled": frozenset(),
}

TERMINAL: frozenset[str] = frozenset({"completed", "failed", "cancelled"})


def is_terminal(state: str) -> bool:
    """终态判定：completed/failed/cancelled 禁止再迁移。"""
    return state in TERMINAL


def assert_transition(current: str, new: str) -> None:
    """校验一次状态迁移是否合法，非法抛 IllegalTransitionError。

    对未知状态字符串（既非 current 也非 new 落在 STATES 内）同样判非法，
    不静默放行——状态机是十态之外没有第十一态。
    """
    if current not in STATES:
        raise IllegalTransitionError(f"未知的当前状态：{current!r}")
    if new not in STATES:
        raise IllegalTransitionError(f"未知的目标状态：{new!r}")
    if new not in TRANSITIONS[current]:
        raise IllegalTransitionError(f"非法转移：{current} -> {new}（docs/05 转移表未声明该迁移）")
