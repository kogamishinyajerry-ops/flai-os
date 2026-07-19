"""File Service 接口：上传/下载，sha256 落库可追溯。"""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path
from typing import Any, BinaryIO, Callable

import anyio
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from starlette.datastructures import MutableHeaders

from ..core.errors import FileIntegrityError
from ..logging_setup import audit_event
from ..runtime.attachments import (
    TEXT_PREVIEW_EXTENSIONS,
    XLSX_PREVIEW_EXTENSIONS,
    render_text_preview_handle,
    render_xlsx_preview_handle,
)
from ..storage import repos
from ..storage.file_integrity import open_verified_file

router = APIRouter(prefix="/api", tags=["files"])

_CHUNK_SIZE = 1024 * 1024

# Starlette 私有覆写哨兵：_VerifiedFileResponse 靠覆写 FileResponse._handle_* 三个
# 私有挂点保证正文只从已验句柄流出。若升级 Starlette 后挂点改名/拆分，覆写会被
# **静默绕过**——基类将重开 self.path 直出未验内容，完整性闸形同虚设。fail-closed：
# 导入期断言挂点存在，升级破坏在启动/CI 即炸，绝不静默降级为未验直出。
for _hook in ("_handle_simple", "_handle_single_range", "_handle_multiple_ranges"):
    if not callable(getattr(FileResponse, _hook, None)):
        raise RuntimeError(
            f"Starlette FileResponse 缺少 {_hook}：完整性下载覆写失效，拒绝启动"
        )


class _VerifiedFileResponse(FileResponse):
    """保留 FileResponse 的响应头/Range 语义，但正文只读完整性校验后的句柄。"""

    def __init__(
        self,
        handle: BinaryIO,
        *,
        path: str,
        filename: str,
        expected_full_bytes: int | None = None,
        on_full_body_sent: Callable[[int], None] | None = None,
        outcome_actor: str | None = None,
        outcome_file_id: str | None = None,
    ) -> None:
        self._verified_handle = handle
        self._expected_full_bytes = expected_full_bytes
        self._on_full_body_sent = on_full_body_sent
        self._outcome_actor = outcome_actor
        self._outcome_file_id = outcome_file_id
        super().__init__(
            path,
            filename=filename,
            stat_result=os.fstat(handle.fileno()),
        )

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # 覆盖正常结束、Range、HEAD、客户端断连及 send 异常，句柄不会泄漏。
            self._verified_handle.close()

    def _capture_completed_body(self, delivered_bytes: int) -> None:
        """Post-send telemetry is best-effort and can never rewrite the response.

        This method runs only after the final ASGI body ``send`` returned.  Its
        database callback and audit fallback are both isolated: the client has
        already received the authoritative bytes, so a later DB/logging fault
        must not turn that successful delivery into an apparent HTTP failure.
        """
        callback = self._on_full_body_sent
        if callback is None:
            return
        try:
            callback(delivered_bytes)
        except Exception:  # post-send DB failure: warning only, never re-raise
            try:
                audit_event(
                    "artifact_outcome_capture_failed",
                    actor=self._outcome_actor or "system",
                    outcome="warning",
                    reason="post_send_db_failure",
                    file_id=self._outcome_file_id,
                )
            except Exception:
                # Logging failure is also post-send; do not corrupt the already
                # delivered response or leak DB exception text into audit data.
                pass

    async def _handle_simple(
        self, send: Any, send_header_only: bool, send_pathsend: bool
    ) -> None:
        del send_pathsend  # 已验句柄必须自己流出，绝不回退 http.response.pathsend 重开 path。
        await send(
            {"type": "http.response.start", "status": self.status_code, "headers": self.raw_headers}
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        more_body = True
        delivered_bytes = 0
        while more_body:
            chunk = await anyio.to_thread.run_sync(
                self._verified_handle.read, self.chunk_size
            )
            more_body = len(chunk) == self.chunk_size
            await send({"type": "http.response.body", "body": chunk, "more_body": more_body})
            delivered_bytes += len(chunk)

        # Only the complete simple 200 path can reach this point.  Range bodies
        # use separate handlers; HEAD returned above; a failed/interrupted send
        # raised before here.  Equality to the authoritative expected size is
        # mandatory—short/extra bodies are not recorded as delivery.
        if (
            self.status_code == 200
            and self._expected_full_bytes is not None
            and delivered_bytes == self._expected_full_bytes
            and self._on_full_body_sent is not None
        ):
            await anyio.to_thread.run_sync(
                self._capture_completed_body, delivered_bytes
            )

    async def _handle_single_range(
        self,
        send: Any,
        start: int,
        end: int,
        file_size: int,
        send_header_only: bool,
    ) -> None:
        headers = MutableHeaders(raw=list(self.raw_headers))
        headers["content-range"] = f"bytes {start}-{end - 1}/{file_size}"
        headers["content-length"] = str(end - start)
        await send(
            {"type": "http.response.start", "status": 206, "headers": headers.raw}
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        await anyio.to_thread.run_sync(self._verified_handle.seek, start)
        more_body = True
        while more_body:
            chunk = await anyio.to_thread.run_sync(
                self._verified_handle.read, min(self.chunk_size, end - start)
            )
            start += len(chunk)
            more_body = len(chunk) == self.chunk_size and start < end
            await send({"type": "http.response.body", "body": chunk, "more_body": more_body})

    async def _handle_multiple_ranges(
        self,
        send: Any,
        ranges: list[tuple[int, int]],
        file_size: int,
        send_header_only: bool,
    ) -> None:
        from secrets import token_hex

        boundary = token_hex(13)
        content_length, header_generator = self.generate_multipart(
            ranges, boundary, file_size, self.headers["content-type"]
        )
        headers = MutableHeaders(raw=list(self.raw_headers))
        headers["content-type"] = f"multipart/byteranges; boundary={boundary}"
        headers["content-length"] = str(content_length)
        await send(
            {"type": "http.response.start", "status": 206, "headers": headers.raw}
        )
        if send_header_only:
            await send({"type": "http.response.body", "body": b"", "more_body": False})
            return

        for start, end in ranges:
            await send(
                {
                    "type": "http.response.body",
                    "body": header_generator(start, end),
                    "more_body": True,
                }
            )
            await anyio.to_thread.run_sync(self._verified_handle.seek, start)
            while start < end:
                chunk = await anyio.to_thread.run_sync(
                    self._verified_handle.read, min(self.chunk_size, end - start)
                )
                start += len(chunk)
                await send(
                    {"type": "http.response.body", "body": chunk, "more_body": True}
                )
            await send(
                {"type": "http.response.body", "body": b"\r\n", "more_body": True}
            )
        await send(
            {
                "type": "http.response.body",
                "body": f"--{boundary}--".encode("latin-1"),
                "more_body": False,
            }
        )


def _sanitize_filename(raw: str | None) -> str:
    """落盘文件名净化（P1-1 路径穿越修复）：只取路径最后一段，杜绝 `../../evil.txt`
    这类穿越 payload 被直接拼进落盘路径；净化后为空或退化为 `.`/`..` 一律兜底 `unnamed`。

    另去控制字符/换行（M7 反方审 P1-B 根因）：换行/引号能污染下游的
    Content-Disposition 头与会话附件 fence header——从入库源头就剥掉，落库
    filename 恒为可打印单行。渲染器仍会二次中和（防御纵深，不赖单点）。
    """
    name = Path((raw or "").strip()).name
    # 去控制字符/换行**和引号**（codex M7-P2）：`"` 是可打印字符，isprintable()
    # 留不住它；恶意客户端可发字面引号污染 Content-Disposition 头与会话附件
    # fence header——根因层必须真剥（httpx 等客户端会预编码引号，故上传级测试
    # 测不到这条分支，直接单测 _sanitize_filename 才咬得住）。
    name = "".join(ch for ch in name if ch.isprintable() and ch != '"')
    if not name or name in (".", ".."):
        return "unnamed"
    return name


def _max_upload_bytes() -> int:
    """上传限额（P2-6），每次调用现读 env，便于测试用 monkeypatch 注入更小的限额。"""
    return int(os.environ.get("FLAI_MAX_UPLOAD_MB", "100")) * 1024 * 1024


_CLASSIFICATIONS = ("internal", "sensitive")


@router.post("/files/upload")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    task_id: str | None = Form(default=None),
    classification: str = Form(default="internal"),
) -> dict[str, Any]:
    # 分级合法性校验先于任何磁盘 I/O（ADR-0021 D2/设计审 F7）：非法值拒收
    # 不落盘不入库——错误方向是「拒收」而非「静默降级 internal 洗白入库」。
    if classification not in _CLASSIFICATIONS:
        raise HTTPException(
            status_code=422,
            detail=f"非法 classification：{classification!r}（合法值 internal|sensitive）",
        )
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
            classification=classification,
            # 分级是自报值（ADR-0021 D2 信任根声明）——标注人记名，标错可追责。
            uploaded_by=request.state.user["display_name"],
        )
    except Exception:
        # 审计 P3（孤儿 blob）：落盘成功但入库失败（如锁等待超时）——磁盘有文件、
        # 库无记录，永远不可达也不可清。入库失败即回收本次落盘，同读循环失败口径。
        dest_path.unlink(missing_ok=True)
        try:
            dest_dir.rmdir()
        except OSError:
            pass
        raise
    finally:
        conn.close()


def _gated_verified_handle(
    request: Request,
    file_id: str,
    *,
    denied_action: str,
    access_label: str,
) -> tuple[dict[str, Any], BinaryIO]:
    """Resolve a file through the shared classification and integrity gates.

    Both download and preview use this exact sequence: record existence,
    internal-only classification, authoritative root selection, and an already
    verified handle.  A future gate change therefore cannot accidentally leave
    preview as a weaker side door.
    """
    conn = request.app.state.conn_factory()
    try:
        record = repos.get_file(conn, file_id)
    finally:
        conn.close()
    if record is None:
        raise HTTPException(status_code=404, detail=f"文件不存在：{file_id}")

    # 分级下载门（ADR-0021 D4）：internal-allowlist——sensitive 与任何未知/坏值
    # 一律 403。V0.1 无角色轴，「谁可下载 sensitive」无裁决依据，诚实答案就是
    # 「暂时没有人可以」；不做白名单/口令旁路（伪造未经设计的授权体系）。
    if record["classification"] != "internal":
        # 审计留痕（ADR-0023）：谁尝试访问了 sensitive 数据必可回溯（EAR 合规）。
        # actor=唯一 username（Codex R0 P2-4：display_name 非唯一，同名账户无法归因），
        # display_name 作附加字段留人可读线索。
        audit_event(
            denied_action,
            actor=request.state.user["username"],
            outcome="denied",
            file_id=file_id,
            classification=record["classification"],
            display_name=request.state.user["display_name"],
        )
        raise HTTPException(
            status_code=403,
            detail=(
                f"文件分级 {record['classification']!r} 未开放{access_label}：角色授权体系"
                "未建立前非 internal 数据一律 fail-closed 拒绝（ADR-0021）"
            ),
        )

    # input 与 output 分属两个权威根：根由应用装配给出，绝不从待校验 path 自推。
    # 未知 kind 没有可信根，按完整性失败 fail-closed。
    if record["kind"] == "input":
        allowed_root = request.app.state.uploads_dir
    elif record["kind"] == "output":
        allowed_root = request.app.state.task_runs_dir
    else:
        raise HTTPException(
            status_code=409,
            detail="文件完整性校验失败：磁盘内容与登记指纹不符",
        )

    try:
        handle = open_verified_file(
            record["path"],
            allowed_root=allowed_root,
            expected_size=record["size_bytes"],
            expected_sha256=record["sha256"],
        )
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail=f"文件记录存在但磁盘缺失：{file_id}")
    except FileIntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail="文件完整性校验失败：磁盘内容与登记指纹不符",
        ) from exc
    return record, handle


@router.get("/files/{file_id}/download")
def download_file(file_id: str, request: Request) -> _VerifiedFileResponse:
    record, handle = _gated_verified_handle(
        request,
        file_id,
        denied_action="sensitive_download_denied",
        access_label="下载",
    )

    # Only output artifacts that are already in the signed outcome cohort when
    # this response is constructed can produce a delivery fact.  Snapshot the
    # exact capture/review witness before streaming: discovering a marker only
    # after the body was sent would retroactively admit a request that started
    # while the artifact was unsigned.  The callback opens its own connection
    # because FileResponse streams after this sync endpoint has returned, then
    # SQLite revalidates the snapshotted witness on insert.  Legacy/input files
    # truthfully no-op.  Repeated complete downloads remain repeated deliveries.
    try:
        on_full_body_sent: Callable[[int], None] | None = None
        if (
            record["kind"] == "output"
            and request.method == "GET"
            # Any Range request is explicitly outside full_download semantics,
            # even when If-Range makes Starlette fall back to a simple 200 body.
            and "range" not in request.headers
        ):
            conn_factory = request.app.state.conn_factory
            actor_username = request.state.user["username"]
            witness_conn = conn_factory()
            try:
                capture_witness = repos.get_artifact_capture_witness(
                    witness_conn, file_id
                )
            finally:
                witness_conn.close()

            if capture_witness is not None:
                source_task_id = capture_witness["source_task_id"]
                source_file_id = capture_witness["source_file_id"]
                review_event_id = capture_witness["review_event_id"]

                def _record(delivered_bytes: int) -> None:
                    conn = conn_factory()
                    try:
                        repos.record_full_download_outcome(
                            conn,
                            source_task_id=source_task_id,
                            source_file_id=source_file_id,
                            review_event_id=review_event_id,
                            actor_username=actor_username,
                            delivered_bytes=delivered_bytes,
                        )
                    finally:
                        conn.close()

                on_full_body_sent = _record

        return _VerifiedFileResponse(
            handle,
            path=record["path"],
            filename=record["filename"],
            expected_full_bytes=record["size_bytes"],
            on_full_body_sent=on_full_body_sent,
            outcome_actor=request.state.user["username"],
            outcome_file_id=file_id,
        )
    except BaseException:
        handle.close()
        raise


# 「先看一眼是什么」的人工审阅预算。完整内容只能由用户显式点击下载获取。
_PREVIEW_CHARS = 8_000


def _preview_response(
    record: dict[str, Any],
    *,
    extension: str,
    preview_kind: str,
    is_text: bool,
    truncated: bool,
    text: str | None,
) -> dict[str, Any]:
    return {
        "file_id": record["id"],
        "filename": record["filename"],
        "size_bytes": record["size_bytes"],
        "extension": extension,
        "preview_kind": preview_kind,
        "is_text": is_text,
        "truncated": truncated,
        "text": text,
    }


@router.get("/files/{file_id}/preview")
def preview_file(file_id: str, request: Request) -> dict[str, Any]:
    """Return verified metadata plus a bounded text/xlsx preview.

    Unsupported formats never expose bytes, but still pass classification and
    integrity checks before their metadata is returned.  This endpoint never
    redirects to download and never reads a full binary blob for presentation.
    """
    record, handle = _gated_verified_handle(
        request,
        file_id,
        denied_action="sensitive_preview_denied",
        access_label="预览",
    )
    extension_with_dot = Path(record["filename"] or "").suffix.lower()
    extension = extension_with_dot.removeprefix(".")
    try:
        if extension_with_dot in TEXT_PREVIEW_EXTENSIONS:
            text, truncated = render_text_preview_handle(handle, _PREVIEW_CHARS)
        elif extension_with_dot in XLSX_PREVIEW_EXTENSIONS:
            text, truncated = render_xlsx_preview_handle(handle, _PREVIEW_CHARS)
        else:
            return _preview_response(
                record,
                extension=extension,
                preview_kind="unsupported",
                is_text=False,
                truncated=False,
                text=None,
            )
    finally:
        handle.close()

    return _preview_response(
        record,
        extension=extension,
        preview_kind="text",
        is_text=True,
        truncated=truncated,
        text=text,
    )
