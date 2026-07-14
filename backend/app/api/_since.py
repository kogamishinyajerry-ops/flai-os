"""since 参数解析共享 helper（批C：stats.py 与 me.py 同款口径，抽出去重）。

offset-aware ISO8601 必填；Z 后缀先归一化再 fromisoformat（Py3.10 兼容，内网
Windows 定版下限不认 Z）；naive/纯日期 422 fail-closed；OverflowError 同归 422。
归一化为 UTC '+00:00' 表示——库内 repos 写入即该格式，字典序比较才恒等时间序。"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException


def parse_since_utc(since: str | None) -> str:
    if not since:
        raise HTTPException(status_code=422, detail="since 必填（ISO8601）")
    parse_src = since[:-1] + "+00:00" if since[-1] in ("Z", "z") else since
    try:
        dt = datetime.fromisoformat(parse_src)
        if dt.tzinfo is None:
            raise HTTPException(
                status_code=422, detail=f"since 必须带时区偏移（offset-aware）：{since}"
            )
        return dt.astimezone(timezone.utc).isoformat()
    except (ValueError, OverflowError) as exc:
        raise HTTPException(status_code=422, detail=f"since 不是合法 ISO8601：{since}") from exc
