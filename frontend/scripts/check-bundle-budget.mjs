import fs from "node:fs";
import path from "node:path";
import zlib from "node:zlib";

const DIST = path.resolve("dist");
const MANIFEST_PATH = path.join(DIST, ".vite", "manifest.json");
const MAX_JS_CHUNK_BYTES = 500_000;
const MAX_SYNC_JS_GZIP_BYTES = 220 * 1024;
const MAX_SYNC_CSS_GZIP_BYTES = 40 * 1024;
const MAX_ROUTE_JS_GZIP_BYTES = 220 * 1024;
const MAX_ROUTE_CSS_GZIP_BYTES = 40 * 1024;
// `/tasks/new` 的表单路由已按 ADR-0033 退役并重定向到主对话。当前 manifest
// 有 8 个真实懒加载 view；既有下限 7 仍咬住误把页面并回同步入口的回归。
const MIN_DYNAMIC_ENTRIES = 7;

if (!fs.existsSync(MANIFEST_PATH)) {
  throw new Error("缺少 dist/.vite/manifest.json；请先运行 npm run build");
}

const manifest = JSON.parse(fs.readFileSync(MANIFEST_PATH, "utf8"));
const entries = Object.entries(manifest);
const entryPair = entries.find(([, record]) => record.isEntry === true);
if (!entryPair) throw new Error("manifest 中没有 isEntry=true 的入口");

const [entryKey, entryRecord] = entryPair;
const recordByFile = new Map(entries.map(([key, record]) => [record.file, { key, record }]));

function collectClosure(record, files, cssFiles) {
  if (!record || files.has(record.file)) return;
  files.add(record.file);
  for (const css of record.css || []) cssFiles.add(css);
  for (const importKey of record.imports || []) {
    const imported = manifest[importKey] || recordByFile.get(importKey)?.record;
    if (!imported) throw new Error(`manifest 同步依赖缺失：${importKey}`);
    collectClosure(imported, files, cssFiles);
  }
}

function compressedSize(relativePath) {
  const bytes = fs.readFileSync(path.join(DIST, relativePath));
  return {
    bytes: bytes.length,
    gzip: zlib.gzipSync(bytes).length,
  };
}

function closureBudget(record) {
  const files = new Set();
  const cssFiles = new Set();
  collectClosure(record, files, cssFiles);
  return {
    jsGzip: [...files]
      .filter((file) => file.endsWith(".js"))
      .reduce((sum, file) => sum + compressedSize(file).gzip, 0),
    cssGzip: [...cssFiles]
      .reduce((sum, file) => sum + compressedSize(file).gzip, 0),
  };
}

const jsChunks = [...new Set(entries
  .map(([, record]) => record.file)
  .filter((file) => file?.endsWith(".js"))
)]
  .map((file) => ({ file, ...compressedSize(file) }));
const oversized = jsChunks.filter((chunk) => chunk.bytes >= MAX_JS_CHUNK_BYTES);
const entryClosure = closureBudget(entryRecord);
const uniqueDynamicEntries = [...new Map(
  entries
    .filter(([, record]) => record.isDynamicEntry === true)
    .map(([key, record]) => [record.file, { key, record }])
).values()];
// defineAsyncComponent 也会标 isDynamicEntry；预算里的“动态路由 chunk ≥7”只
// 统计 src/views，不能让异步子组件把退化的路由数顶成假绿。
const uniqueDynamicRouteEntries = uniqueDynamicEntries.filter(({ key, record }) =>
  (record.src || key).startsWith("src/views/")
);
const routeClosures = uniqueDynamicRouteEntries.map(({ key, record }) => ({
  key,
  file: record.file,
  ...closureBudget(record),
}));
const dynamicEntryCount = uniqueDynamicRouteEntries.length;
const asyncComponentEntryCount = uniqueDynamicEntries.length - dynamicEntryCount;
const oversizedRouteClosures = routeClosures.filter((route) =>
  route.jsGzip > MAX_ROUTE_JS_GZIP_BYTES
  || route.cssGzip > MAX_ROUTE_CSS_GZIP_BYTES
);

const failures = [];
if (oversized.length) {
  failures.push(`存在 ≥500 kB JS chunk：${oversized.map((item) => item.file).join("、")}`);
}
if (entryClosure.jsGzip > MAX_SYNC_JS_GZIP_BYTES) {
  failures.push(`入口同步 JS gzip ${entryClosure.jsGzip} B > ${MAX_SYNC_JS_GZIP_BYTES} B`);
}
if (entryClosure.cssGzip > MAX_SYNC_CSS_GZIP_BYTES) {
  failures.push(`入口同步 CSS gzip ${entryClosure.cssGzip} B > ${MAX_SYNC_CSS_GZIP_BYTES} B`);
}
if (dynamicEntryCount < MIN_DYNAMIC_ENTRIES) {
  failures.push(`唯一动态路由 chunk 仅 ${dynamicEntryCount} 个，少于 ${MIN_DYNAMIC_ENTRIES} 个`);
}
if (oversizedRouteClosures.length) {
  failures.push(
    `路由闭包超预算：${oversizedRouteClosures
      .map((item) => `${item.key}（JS gzip ${item.jsGzip} B / CSS gzip ${item.cssGzip} B）`)
      .join("、")}`
  );
}

const report = {
  entry: entryKey,
  entryFile: entryRecord.file,
  largestJsChunk: jsChunks.sort((a, b) => b.bytes - a.bytes)[0],
  syncJsGzip: entryClosure.jsGzip,
  syncCssGzip: entryClosure.cssGzip,
  dynamicEntryCount,
  asyncComponentEntryCount,
  largestRouteClosure: [...routeClosures]
    .sort((a, b) => (b.jsGzip + b.cssGzip) - (a.jsGzip + a.cssGzip))[0],
};
console.log(JSON.stringify(report, null, 2));

if (failures.length) {
  throw new Error(failures.join("\n"));
}
