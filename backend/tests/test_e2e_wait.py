"""Deterministic contracts for browser acceptance polling."""

from __future__ import annotations

import math

import pytest

from frontend.e2e._wait import wait_for_condition


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def read(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def test_wait_for_condition_checks_the_exact_timeout_boundary() -> None:
    clock = _FakeClock()

    observed = wait_for_condition(
        lambda: clock.now >= 30.0,
        timeout_seconds=30.0,
        poll_seconds=1.0,
        clock=clock.read,
        sleeper=clock.sleep,
    )

    assert observed is True
    assert clock.now == 30.0


def test_wait_for_condition_does_not_oversleep_timeout() -> None:
    clock = _FakeClock()

    observed = wait_for_condition(
        lambda: False,
        timeout_seconds=2.5,
        poll_seconds=1.0,
        clock=clock.read,
        sleeper=clock.sleep,
    )

    assert observed is False
    assert clock.now == 2.5


def test_wait_for_condition_rejects_success_observed_only_after_oversleep() -> None:
    clock = _FakeClock()

    def oversleep(seconds: float) -> None:
        clock.now += seconds + 0.4

    observed = wait_for_condition(
        lambda: clock.now >= 2.5,
        timeout_seconds=2.5,
        poll_seconds=1.0,
        clock=clock.read,
        sleeper=oversleep,
    )

    assert clock.now > 2.5
    assert observed is False


@pytest.mark.parametrize(
    ("timeout_seconds", "poll_seconds"),
    [
        (0.0, 1.0),
        (-1.0, 1.0),
        (1.0, 0.0),
        (1.0, -1.0),
        (math.nan, 1.0),
        (math.inf, 1.0),
        (-math.inf, 1.0),
        (1.0, math.nan),
        (1.0, math.inf),
        (1.0, -math.inf),
    ],
)
def test_wait_for_condition_rejects_non_positive_intervals(
    timeout_seconds: float,
    poll_seconds: float,
) -> None:
    with pytest.raises(ValueError):
        wait_for_condition(
            lambda: False,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
            clock=lambda: 0.0,
            sleeper=lambda _seconds: pytest.fail("invalid intervals must fail before sleeping"),
        )
