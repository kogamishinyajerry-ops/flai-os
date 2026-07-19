"""Small deterministic waits for self-contained browser acceptance scripts."""

from __future__ import annotations

import math
import time
from collections.abc import Callable


def wait_for_condition(
    predicate: Callable[[], bool],
    *,
    timeout_seconds: float,
    poll_seconds: float = 1.0,
    clock: Callable[[], float] = time.monotonic,
    sleeper: Callable[[float], None] = time.sleep,
) -> bool:
    """Poll through the exact timeout boundary without using wall-clock time."""
    if (
        not math.isfinite(timeout_seconds)
        or not math.isfinite(poll_seconds)
        or timeout_seconds <= 0
        or poll_seconds <= 0
    ):
        raise ValueError("timeout_seconds and poll_seconds must be finite and positive")

    deadline = clock() + timeout_seconds
    while True:
        if clock() > deadline:
            return False
        if predicate() is True:
            return clock() <= deadline
        remaining = deadline - clock()
        if remaining <= 0:
            return False
        sleeper(min(poll_seconds, remaining))
