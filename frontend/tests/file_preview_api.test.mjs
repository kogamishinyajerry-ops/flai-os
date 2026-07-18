import assert from "node:assert/strict";
import test from "node:test";

import { downloadUrl, fetchFilePreview } from "../src/api/files.js";

test("file preview reads bounded JSON endpoint and never downloads the blob", async () => {
  const calls = [];
  globalThis.fetch = async (path) => {
    calls.push(path);
    return {
      ok: true,
      json: async () => ({
        file_id: "file-1",
        filename: "report.md",
        size_bytes: 123,
        extension: "md",
        preview_kind: "text",
        is_text: true,
        truncated: true,
        text: "bounded preview",
      }),
    };
  };

  const result = await fetchFilePreview("file-1");

  assert.deepEqual(calls, ["/api/files/file-1/preview"]);
  assert.equal(calls.some((path) => path.includes("/download")), false);
  assert.deepEqual(result, {
    fileId: "file-1",
    filename: "report.md",
    ext: "md",
    size: 123,
    previewKind: "text",
    isText: true,
    truncated: true,
    text: "bounded preview",
  });
});

test("unsupported preview remains metadata-only until explicit download", async () => {
  const calls = [];
  globalThis.fetch = async (path) => {
    calls.push(path);
    return {
      ok: true,
      json: async () => ({
        file_id: "file-2",
        filename: "mesh.bin",
        size_bytes: 4,
        extension: "bin",
        preview_kind: "unsupported",
        is_text: false,
        truncated: false,
        text: null,
      }),
    };
  };

  const result = await fetchFilePreview("file-2");

  assert.equal(result.previewKind, "unsupported");
  assert.equal(result.text, null);
  assert.deepEqual(calls, ["/api/files/file-2/preview"]);
  assert.equal(downloadUrl("file-2"), "/api/files/file-2/download");
});

test("literal truncation words stay ordinary content when the backend flag is false", async () => {
  globalThis.fetch = async () => ({
    ok: true,
    json: async () => ({
      file_id: "file-3",
      filename: "evidence.json",
      size_bytes: 36,
      extension: "json",
      preview_kind: "text",
      is_text: true,
      truncated: false,
      text: '{"note":"[截断： is source text"}',
    }),
  });

  const result = await fetchFilePreview("file-3");

  assert.equal(result.truncated, false);
  assert.match(result.text, /\[截断：/);
});
