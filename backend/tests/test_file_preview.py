"""Fable Batch 8 C: bounded file-preview access contract.

The preview endpoint is a read surface, not an authorization shortcut.  These
tests deliberately lock the failure paths before the happy rendering paths:
classification and integrity checks must match download, unsupported formats
must still pass the integrity gate, and previews must stay bounded.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import openpyxl
import pytest


def _upload(client, name: str, data: bytes) -> dict:
    response = client.post(
        "/api/files/upload",
        files={"file": (name, data, "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    return response.json()


def test_preview_unknown_file_is_404(app_env) -> None:
    client, _app = app_env

    response = client.get("/api/files/does-not-exist/preview")

    assert response.status_code == 404


def test_preview_sensitive_file_is_fail_closed(app_env) -> None:
    client, app = app_env
    record = _upload(client, "secret.md", "受限内容".encode())
    conn = app.state.conn_factory()
    try:
        conn.execute(
            "UPDATE files SET classification = 'sensitive' WHERE id = ?",
            (record["id"],),
        )
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 403
    assert "fail-closed" in response.json()["detail"]
    audit_path = Path(app.state.db_path).parent / "logs" / "audit.log"
    audit_rows = [json.loads(line) for line in audit_path.read_text("utf-8").splitlines()]
    denied = [
        row
        for row in audit_rows
        if row.get("action") == "sensitive_preview_denied"
        and row.get("file_id") == record["id"]
    ]
    assert len(denied) == 1
    assert denied[0]["actor"] == "test_engineer"


def test_preview_unknown_file_kind_is_integrity_failure(app_env) -> None:
    client, app = app_env
    record = _upload(client, "kind.md", b"registered bytes")
    conn = app.state.conn_factory()
    try:
        conn.execute("UPDATE files SET kind = 'mystery' WHERE id = ?", (record["id"],))
        conn.commit()
    finally:
        conn.close()

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 409
    assert response.json()["detail"] == "文件完整性校验失败：磁盘内容与登记指纹不符"


def test_preview_same_size_tamper_is_409(app_env) -> None:
    client, _app = app_env
    original = b"signed-A"
    tampered = b"forged-B"
    assert len(original) == len(tampered)
    record = _upload(client, "tamper.md", original)
    Path(record["path"]).write_bytes(tampered)

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 409
    assert response.json()["detail"] == "文件完整性校验失败：磁盘内容与登记指纹不符"
    assert tampered not in response.content


def test_unsupported_preview_still_rejects_tampered_bytes(app_env) -> None:
    client, _app = app_env
    record = _upload(client, "opaque.bin", b"trusted")
    Path(record["path"]).write_bytes(b"forged!")

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 409


def test_preview_missing_registered_file_is_404(app_env) -> None:
    client, _app = app_env
    record = _upload(client, "missing.md", b"registered")
    Path(record["path"]).unlink()

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 404
    assert "磁盘缺失" in response.json()["detail"]


def test_preview_markdown_is_bounded_and_reports_truncation(app_env) -> None:
    client, _app = app_env
    text = "裕度核查。" * 4_000
    record = _upload(client, "margin.md", text.encode())

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body == {
        "file_id": record["id"],
        "filename": "margin.md",
        "size_bytes": len(text.encode()),
        "extension": "md",
        "preview_kind": "text",
        "is_text": True,
        "truncated": True,
        "text": body["text"],
    }
    assert "裕度核查" in body["text"]
    assert "[截断：内容超出预览预算" in body["text"]
    assert "原文" not in body["text"], "bounded reads must not invent a total character count"
    assert len(body["text"]) < 8_200


def test_preview_literal_truncation_marker_does_not_forge_structured_flag(app_env) -> None:
    client, _app = app_env
    payload = '{"note":"用户原文包含 [截断： 与 [行截断： 字样"}'
    record = _upload(client, "literal-marker.json", payload.encode("utf-8"))

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["text"] == payload
    assert body["truncated"] is False


@pytest.mark.parametrize("extension", ["text", "markdown"])
def test_preview_preserves_existing_plain_text_extensions(app_env, extension: str) -> None:
    client, _app = app_env
    payload = "既有文本格式仍应在线预览"
    record = _upload(client, f"evidence.{extension}", payload.encode("utf-8"))

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    assert response.json()["is_text"] is True
    assert response.json()["text"] == payload


def test_preview_xlsx_uses_shared_bounded_renderer(app_env) -> None:
    client, _app = app_env
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["工况", "裕度"])
    sheet.append(["巡航", 0.23])
    buffer = io.BytesIO()
    workbook.save(buffer)
    record = _upload(client, "margins.xlsx", buffer.getvalue())

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["preview_kind"] == "text"
    assert body["extension"] == "xlsx"
    assert body["is_text"] is True
    assert "[xlsx 预览]" in body["text"]
    assert "工况" in body["text"] and "巡航" in body["text"]


def test_preview_xlsx_column_cap_sets_structured_truncated_flag(app_env) -> None:
    client, _app = app_env
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append([f"c{column}" for column in range(17)])
    buffer = io.BytesIO()
    workbook.save(buffer)
    record = _upload(client, "wide.xlsx", buffer.getvalue())

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["truncated"] is True
    assert "…[+1 列]" in body["text"]


def test_preview_malformed_xlsx_is_honest_not_500(app_env) -> None:
    client, _app = app_env
    record = _upload(client, "broken.xlsx", b"not a zip workbook")

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["preview_kind"] == "text"
    assert body["truncated"] is False
    assert "未解析" in body["text"]
    assert "zip" in body["text"]


def test_preview_valid_zip_with_malformed_xlsx_xml_is_honest_not_500(app_env) -> None:
    client, _app = app_env
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types><Override")
        archive.writestr("xl/workbook.xml", "<workbook>")
    record = _upload(client, "malformed-xml.xlsx", buffer.getvalue())

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["preview_kind"] == "text"
    assert body["truncated"] is False
    assert "未解析" in body["text"]
    assert "xlsx" in body["text"]


def test_preview_unsupported_format_returns_metadata_without_content(app_env) -> None:
    client, _app = app_env
    payload = b"\x00\x01\x02\x03"
    record = _upload(client, "opaque.bin", payload)

    response = client.get(f"/api/files/{record['id']}/preview")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "file_id": record["id"],
        "filename": "opaque.bin",
        "size_bytes": len(payload),
        "extension": "bin",
        "preview_kind": "unsupported",
        "is_text": False,
        "truncated": False,
        "text": None,
    }
