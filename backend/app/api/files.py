"""File Service 接口：上传/下载，sha256 落库可追溯。"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse

from ..storage import repos

router = APIRouter(prefix="/api", tags=["files"])

_CHUNK_SIZE = 1024 * 1024


def _sanitize_filename(raw: str | None) -> str:
    """落盘文件名净化（P1-1 路径穿越修复）：只取路径最后一段，杜绝 `../../evil.txt`
    这类穿越 payload 被直接拼进落盘路径；净化后为空或退化为 `.`/`..` 一律兜底 `unnamed`。
    """
    name = Path((raw or "").strip()).name
    if not name or name in (".", ".."):
        return "unnamed"
    return name


def _max_upload_bytes() -> int:
    """上传限额（P2-6），每次调用现读 env，便于测试用 monkeypatch 注入更小的限额。"""
    return int(os.environ.get("FLAI_MAX_UPLOAD_MB", "100")) * 1024 * 1024


@router.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    task_id: str | None = Form(default=None),
) -> dict[str, Any]:
    uploads_dir: Path = request.app.state.uploads_dir
    file_id = str(uuid.uuid4())
    dest_dir = uploads_dir / file_id
    filename = _sanitize_filename(file.filename)
    dest_path = dest_dir / filename

    # 防御性断言（belt & suspenders）：净化后仍要求落盘路径不得逃出 uploads_dir，
    # 否则一律 400 拒绝——不依赖净化逻辑单独扛住所有花式穿越 payload。
    uploads_resolved = uploads_dir.resolve()
    dest_resolved = dest_path.resolve()
    if dest_resolved != uploads_resolved and uploads_resolved not in dest_resolved.parents:
        raise HTTPException(
            status_code=400,
            detail=f"非法文件名，落盘路径逃出 uploads 目录：{file.filename!r}",
        )

    dest_dir.mkdir(parents=True, exist_ok=True)
    max_bytes = _max_upload_bytes()
    digest = hashlib.sha256()
    size = 0
    try:
        with dest_path.open("wb") as out:
            while True:
                chunk = await file.read(_CHUNK_SIZE)
                if not chunk:
                    break
                size += len(chunk)
                if size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超出上传限额（FLAI_MAX_UPLOAD_MB，当前={max_bytes} 字节）",
                    )
                digest.update(chunk)
                out.write(chunk)
    except HTTPException:
        dest_path.unlink(missing_ok=True)
        try:
            dest_dir.rmdir()
        except OSError:
            pass  # 目录非空（罕见并发场景）则保留，不强删其他内容
        raise

    conn = request.app.state.conn_factory()
    try:
        return repos.create_file(
            conn,
            file_id=file_id,
            task_id=task_id,
            kind="input",
            filename=filename,
            path=str(dest_path),
            size_bytes=size,
            sha256=digest.hexdigest(),
        )
    finally:
        conn.close()


@router.get("/files/{file_id}/download")
def download_file(file_id: str, request: Request) -> FileResponse:
    conn = request.app.state.conn_factory()
    try:
        record = repos.get_file(conn, file_id)
    finally:
        conn.close()
    if record is None:
        raise HTTPException(status_code=404, detail=f"文件不存在：{file_id}")
    path = Path(record["path"])
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"文件记录存在但磁盘缺失：{file_id}")
    return FileResponse(path, filename=record["filename"])
