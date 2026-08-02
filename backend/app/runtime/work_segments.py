"""Shared authoritative boundaries for one conversation-first work segment."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping


def created_strictly_after(created_at: Any, boundary: Any) -> bool:
    """Return true only for valid ISO timestamps strictly after the boundary."""

    if not isinstance(created_at, str) or not isinstance(boundary, str):
        return False
    try:
        return datetime.fromisoformat(created_at) > datetime.fromisoformat(boundary)
    except (TypeError, ValueError):
        return False


def created_at_or_before(created_at: Any, boundary: Any) -> bool:
    """Return true only for valid ISO timestamps at or before the boundary."""

    if not isinstance(created_at, str) or not isinstance(boundary, str):
        return False
    try:
        return datetime.fromisoformat(created_at) <= datetime.fromisoformat(boundary)
    except (TypeError, ValueError):
        return False


def latest_valid_iso(values: list[Any]) -> str | None:
    """Return the greatest valid ISO timestamp; malformed values do not advance it."""

    parsed: list[tuple[datetime, str]] = []
    for value in values:
        if not isinstance(value, str):
            continue
        try:
            parsed.append((datetime.fromisoformat(value), value))
        except ValueError:
            continue
    return max(parsed, key=lambda item: item[0])[1] if parsed else None


def is_guide_refuse_delivery(message: Mapping[str, Any]) -> bool:
    """A persisted, Guide-validated refusal closes the preceding work segment."""

    recommendation = message.get("recommendation")
    return (
        message.get("role") == "assistant"
        and isinstance(recommendation, Mapping)
        and recommendation.get("decision") == "refuse"
    )


def is_canonical_qa_delivery(message: Mapping[str, Any]) -> bool:
    """Recognize the validated policy/standards QA delivery shape."""

    recommendation = message.get("recommendation")
    if message.get("role") != "assistant" or not isinstance(recommendation, Mapping):
        return False
    findings = recommendation.get("findings")
    refusals = recommendation.get("refusals")
    return (
        set(recommendation) == {"answer", "findings", "refusals"}
        and isinstance(recommendation.get("answer"), str)
        and recommendation["answer"] == message.get("content")
        and isinstance(findings, list)
        and isinstance(refusals, list)
        and bool(findings or refusals)
    )
