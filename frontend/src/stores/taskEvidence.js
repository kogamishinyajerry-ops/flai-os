// 任务依据投影（批七 §2.2/§1.6）：completed/waiting_review 任务的 JSON 产物里
// 读顶层 findings/refusals（输出契约惯例，docs/02 §7）。模块级单例缓存——
// GuidePage 行内 chip 与 WorkbenchSession 收纳行共用，同任务只拉一次。
// 拉取失败（含密级遮蔽拒读）→ loaded 空结果：消费面零 chip 诚实缺位，绝不
// 编计数、不重试风暴。resolved 语义：true 只能来自后端回源指纹（ADR-0029），
// 本模块只忠实转读绝不改写。
import { reactive } from "vue";
import { listOutputFiles } from "../api/tasks";
import { fetchOutputFile } from "../api/files";

const cache = reactive({}); // taskId -> {loaded, findings, refusals}

export function useTaskEvidence() {
  return cache;
}

export function ensureTaskEvidence(t) {
  if (!t || cache[t.id]) return;
  if (t.status !== "completed" && t.status !== "waiting_review") return;
  const entry = reactive({ loaded: false, findings: [], refusals: [], withheld: false });
  cache[t.id] = entry;
  const ids = t.output_file_ids || [];
  if (ids.length === 0) {
    entry.loaded = true;
    return;
  }
  listOutputFiles(t.id)
    .then(async (files) => {
      // Codex R2 P1（verbatim，批B P1 同款先例）：internal-allowlist——非 internal
      // 分级产物**不发起下载**。被动依据水合对 sensitive 文件盲调 /download 会在
      // 后端落 sensitive_download_denied 审计（用户根本没有下载意图=假阳性审计
      // 事件），且 internal 件也省一次纯展示目的的全量 blob。密级遮蔽下诚实缺位：
      // 零 chip，不编计数。
      // 批八 withheld 接线：存在密级受限的 JSON 产物 → 标 withheld，消费面渲
      // 静态「按密级隐藏」标记——**绝不编造计数**（无内容即无 N）。与 internal
      // 件可共存（如 hello_output.json + 受限依据件）：可读的照常解析展示，
      // 受限的如实标遮蔽，两者都不隐瞒。
      entry.withheld = (files || []).some(
        (f) => /\.json$/i.test(f.filename || "") && f.data_classification !== "internal"
      );
      const jf = (files || []).find(
        (f) => /\.json$/i.test(f.filename || "") && f.data_classification === "internal"
      );
      if (!jf) {
        entry.loaded = true;
        return;
      }
      const res = await fetchOutputFile(jf.id);
      let data = {};
      if (res.isText && res.text) {
        try {
          data = JSON.parse(res.text);
        } catch {
          data = {}; // 非 JSON 产物=无依据结构，诚实空
        }
      }
      entry.findings = Array.isArray(data.findings) ? data.findings : [];
      entry.refusals = Array.isArray(data.refusals) ? data.refusals : [];
      entry.loaded = true;
    })
    .catch(() => {
      entry.loaded = true; // 拿不到=不渲 chip（诚实缺位）
    });
}

export function taskEvidenceOf(taskId) {
  const e = cache[taskId];
  return e && e.loaded === true ? e : null;
}

// withheld 判据（批八）：有 JSON 产物但密级受限，未发起任何下载——消费面据此
// 渲静态遮蔽标记（GuidePage chip / Workbench 收纳行 / TaskDetail 依据段三处
// 同口径，O6 逐一断言）。
export function taskEvidenceWithheld(taskId) {
  const e = cache[taskId];
  return e !== undefined && e.loaded === true && e.withheld === true;
}

// 依据摘要计数：置信度报最低档（诚实地板——多 finding 取最保守）。
export function taskEvidenceSummary(taskId) {
  const ev = taskEvidenceOf(taskId);
  if (!ev || ev.findings.length === 0) return null;
  let verified = 0;
  let unverified = 0;
  for (const f of ev.findings) {
    for (const e of f.evidence || []) {
      if (e.resolved === true) verified += 1;
      else unverified += 1;
    }
  }
  const rank = { low: 0, medium: 1, high: 2 };
  const LV = { low: "低", medium: "中", high: "高" };
  let worst = null;
  for (const f of ev.findings) {
    const l = f.confidence && f.confidence.level;
    if (l && rank[l] !== undefined && (worst === null || rank[l] < rank[worst])) worst = l;
  }
  return { total: verified + unverified, verified, unverified, level: worst ? LV[worst] : "" };
}
