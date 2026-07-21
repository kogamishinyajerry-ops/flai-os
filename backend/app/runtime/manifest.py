"""Agent manifest 的跨派发/执行规范化绑定。"""

from __future__ import annotations

import hashlib
import json
from typing import Any


MANIFEST_PIN_VERSION = "agent_manifest_pin.v1"


def canonical_manifest_digest(manifest: dict[str, Any]) -> str:
    encoded = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return "sha256:" + hashlib.sha256(encoded).hexdigest()
