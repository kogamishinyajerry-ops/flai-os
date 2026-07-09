"""任务十态状态机全转移矩阵测试（docs/05 §1-2 唯一真相源）。

覆盖：合法转移 8+ 例、非法转移 10+ 例（含终态无出边、含 running 不得跳过
analyzing 直转 completed 这条 docs/05 明文强制规则）、is_terminal 判定。
"""

from __future__ import annotations

import pytest

from backend.app.core.errors import IllegalTransitionError
from backend.app.core.statemachine import STATES, TERMINAL, assert_transition, is_terminal

# ── 合法转移（严格镜像 docs/05 第 2 节表格）───────────────────────────

LEGAL_TRANSITIONS = [
    ("created", "queued"),
    ("created", "cancelled"),
    ("queued", "validating"),
    ("queued", "cancelled"),
    ("validating", "running"),
    ("validating", "failed"),
    ("validating", "cancelled"),
    ("running", "parsing"),
    ("running", "analyzing"),
    ("running", "waiting_review"),
    ("running", "failed"),
    ("running", "cancelled"),
    ("parsing", "analyzing"),
    ("parsing", "running"),
    ("parsing", "failed"),
    ("parsing", "cancelled"),
    ("analyzing", "waiting_review"),
    ("analyzing", "completed"),
    ("analyzing", "failed"),
    ("analyzing", "cancelled"),
    ("waiting_review", "completed"),
    ("waiting_review", "failed"),
]


@pytest.mark.parametrize("current, new", LEGAL_TRANSITIONS)
def test_legal_transition_does_not_raise(current: str, new: str) -> None:
    assert_transition(current, new)  # 不抛即通过


# ── 非法转移（含终态无出边 + running 不得跳过 analyzing 直转 completed）─

ILLEGAL_TRANSITIONS = [
    ("created", "running"),
    ("created", "completed"),
    ("created", "validating"),
    ("queued", "running"),
    ("queued", "completed"),
    ("validating", "waiting_review"),
    ("validating", "completed"),
    ("running", "completed"),  # docs/05 强制规则：不得跳过 analyzing 直转 completed
    ("running", "created"),
    ("parsing", "waiting_review"),
    ("parsing", "completed"),
    ("analyzing", "running"),
    ("analyzing", "parsing"),
    ("waiting_review", "running"),
    ("waiting_review", "cancelled"),  # waiting_review 只能人工放行转 completed/failed
    ("completed", "failed"),
    ("completed", "running"),
    ("failed", "completed"),
    ("cancelled", "created"),
    ("cancelled", "queued"),
]


@pytest.mark.parametrize("current, new", ILLEGAL_TRANSITIONS)
def test_illegal_transition_raises(current: str, new: str) -> None:
    with pytest.raises(IllegalTransitionError):
        assert_transition(current, new)


@pytest.mark.parametrize("terminal_state", sorted(TERMINAL))
def test_terminal_state_has_no_legal_outbound(terminal_state: str) -> None:
    """终态无出边：对全部十态尝试转出，必须无一合法。"""
    for target in STATES:
        with pytest.raises(IllegalTransitionError):
            assert_transition(terminal_state, target)


def test_is_terminal() -> None:
    for s in ("completed", "failed", "cancelled"):
        assert is_terminal(s) is True
    for s in ("created", "queued", "validating", "running", "parsing", "analyzing", "waiting_review"):
        assert is_terminal(s) is False


def test_unknown_state_raises() -> None:
    with pytest.raises(IllegalTransitionError):
        assert_transition("no_such_state", "queued")
    with pytest.raises(IllegalTransitionError):
        assert_transition("created", "no_such_state")


def test_states_count_is_ten() -> None:
    assert len(STATES) == 10
