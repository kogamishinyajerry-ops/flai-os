// 用户提示同样服从五槽信任色锁：绿只表示 REAL，teal 只表示认证人签。
import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, extname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
const SRC = join(ROOT, "src");

function sourceFiles(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sourceFiles(path);
    return [".js", ".vue"].includes(extname(entry.name)) ? [path] : [];
  });
}

function source(path) {
  return readFileSync(join(ROOT, path), "utf8");
}

test("普通动作、完成、取消和反馈不得借 Element success 假绿", () => {
  for (const path of sourceFiles(SRC)) {
    assert.doesNotMatch(
      readFileSync(path, "utf8"),
      /ElMessage\.success\s*\(/,
      `${path} 不得用绿色 toast 表示普通动作完成`,
    );
  }
  assert.match(source("src/views/AgentPortal.vue"), /ElMessage\.info\("评测完成——结果按逐项证据显示"\)/);
  assert.match(source("src/views/TaskDetail.vue"), /ElMessage\.info\("任务已取消"\)/);
});

test("认证人签 toast 固定使用 teal，驳回固定使用红槽", () => {
  const signedConsumers = [
    "src/views/AgentPortal.vue",
    "src/views/TaskDetail.vue",
    "src/components/StatusCenter.vue",
  ];
  for (const path of signedConsumers) {
    assert.match(source(path), /customClass:\s*"flai-message-signed"/);
  }

  const app = source("src/App.vue");
  assert.match(app, /\.flai-message-signed\s*\{/);
  assert.match(app, /--el-message-text-color:\s*var\(--trust-signed\)/);
  assert.match(source("src/components/StatusCenter.vue"), /ElMessage\.error\("已驳回"\)/);
  assert.match(source("src/views/TaskDetail.vue"), /ElMessage\.error\(`已\$\{label\}`\)/);
});
