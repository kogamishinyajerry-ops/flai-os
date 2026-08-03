"""Deterministic JSON digests shared across execution and ontology evidence."""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any


def _stable_value(value: Any) -> Any:
    """Mirror the ontology candidate canonical-value contract, including NFC."""
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise ValueError("canonical object keys must be strings")
        return {
            unicodedata.normalize("NFC", key): _stable_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_stable_value(item) for item in value]
    if isinstance(value, tuple):
        return [_stable_value(item) for item in value]
    if isinstance(value, str):
        return unicodedata.normalize("NFC", value)
    if value is None or isinstance(value, (bool, int)):
        return value
    if (
        isinstance(value, float)
        and value == value
        and value not in (float("inf"), float("-inf"))
    ):
        return value
    raise ValueError(f"unsupported canonical value type: {type(value).__name__}")


def canonical_digest(value: Any) -> str:
    """Return the ontology-compatible SHA-256 digest of a JSON-like value."""
    payload = json.dumps(
        _stable_value(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(payload).hexdigest()}"
