export function isDisplayableEvidenceRow(row) {
  return (
    row
    && typeof row === "object"
    && !Array.isArray(row)
    && typeof row.kind === "string"
    && row.kind.trim() !== ""
    && typeof row.source_ref === "string"
    && row.source_ref.trim() !== ""
    && (row.resolved === true || row.resolved === false)
  );
}

export function summarizeEvidenceFindings(findings) {
  if (!Array.isArray(findings) || findings.length === 0) return null;
  let verified = 0;
  let unverified = 0;
  const levels = [];
  for (const finding of findings) {
    if (
      !finding
      || typeof finding !== "object"
      || !Array.isArray(finding.evidence)
      || finding.evidence.length === 0
    ) {
      return { invalid: true, total: null, verified: null, unverified: null, level: "" };
    }
    for (const row of finding.evidence) {
      if (!isDisplayableEvidenceRow(row)) {
        return { invalid: true, total: null, verified: null, unverified: null, level: "" };
      }
      if (row.resolved === true) verified += 1;
      else unverified += 1;
    }
    const level = finding.confidence?.level;
    if (["low", "medium", "high"].includes(level)) levels.push(level);
  }
  const rank = { low: 0, medium: 1, high: 2 };
  const labels = { low: "低", medium: "中", high: "高" };
  const worst = levels.sort((a, b) => rank[a] - rank[b])[0] || null;
  return {
    invalid: false,
    total: verified + unverified,
    verified,
    unverified,
    level: worst ? labels[worst] : "",
  };
}

// map#46 #56（R-B/R-C 依据行）：方案卡级聚合——把成员任务各自的
// summarizeEvidenceFindings 结果与 withheld 标记合成一行计数。纯函数零 IO。
// 语义全取保守向（诚实地板）：
//   - invalid 任一命中即整体 invalid（结构待核降级，计数只来自结构合法的成员）；
//   - 置信度取最低档（与 summarizeEvidenceFindings 多 finding 同口径）；
//   - 零占位：无任何成员数据且无遮蔽项时返回 null，消费面不渲行。
// 入参 entries: [{ summary, withheld }]，summary 为 summarizeEvidenceFindings
// 的返回（null=该成员无可读依据），withheld 为 taskEvidenceWithheld 的布尔。
export function mergeEvidenceSummaries(entries) {
  const list = Array.isArray(entries) ? entries : [];
  const withheld = list.some((entry) => entry?.withheld === true);
  const summaries = list
    .map((entry) => entry?.summary ?? null)
    .filter((s) => s !== null);
  if (summaries.length === 0) {
    return withheld
      ? { invalid: false, total: null, verified: null, unverified: null, level: "", withheld: true }
      : null;
  }
  const rank = { 低: 0, 中: 1, 高: 2 };
  let total = 0;
  let verified = 0;
  let unverified = 0;
  let worst = null;
  for (const s of summaries) {
    if (s.invalid === true) continue; // 结构不合法的成员不贡献计数
    total += s.total;
    verified += s.verified;
    unverified += s.unverified;
    if (
      typeof s.level === "string"
      && s.level in rank
      && (worst === null || rank[s.level] < rank[worst])
    ) {
      worst = s.level;
    }
  }
  return {
    invalid: summaries.some((s) => s.invalid === true),
    total,
    verified,
    unverified,
    level: worst ?? "",
    withheld,
  };
}

// map#46 #56 互审 F2/F3（owner 2026-08-06 裁）：方案卡依据行的成员态聚合裁决。
// 入参 memberStates: [{ state, summary? }]，state 由消费面（GuidePage）用确定性
// 信号判定：
//   attributionFailed = 成员有任务但无一落在该卡开工时间窗内（归属不定）；
//   noTask   = 成员零任务（未开工）；pending = 任务在窗内但未终态/水合在途；
//   withheld = 依据按密级隐藏（已知的遮蔽态，不是未知）；
//   empty    = 终态已水合、零 findings（零占位纪律，已知空）；
//   data     = 终态已水合、有 findings 摘要（含 invalid 摘要）。
// 裁决（诚实地板，全保守向）：
//   - 任一 attributionFailed → null：归属不定 fail-closed 不渲行，绝不拿会话级
//     latest-by-agent 近似冒充该卡依据（F2）；
//   - 无任何 data/withheld → null：零占位（开工前/全员在途/全员空都不渲）；
//   - 有 data/withheld 且仍有 pending/noTask 成员 → 「依据结构待核」amber：
//     部分成员计数绝不冒充方案完整计数（F3 降级，不显示部分数字）；
//   - 全员已知（data/withheld/empty）→ 正常聚合计数（empty 零占位不贡献），
//     invalid 任一命中整体待核、遮蔽共存沿 W7 后缀「·另有密级隐藏项」。
export function decidePlanEvidenceLine(memberStates) {
  const list = Array.isArray(memberStates) ? memberStates : [];
  if (list.length === 0) return null;
  if (list.some((s) => s?.state === "attributionFailed")) return null;
  const readable = list.some((s) => s?.state === "data" || s?.state === "withheld");
  if (!readable) return null;
  if (list.some((s) => s?.state === "pending" || s?.state === "noTask")) {
    return { text: "依据结构待核", hasUnverified: true, withheldOnly: false };
  }
  const merged = mergeEvidenceSummaries(
    list.map((s) => ({
      summary: s?.state === "data" ? s.summary ?? null : null,
      withheld: s?.state === "withheld",
    })),
  );
  if (!merged) return null;
  if (merged.invalid) {
    return {
      text: merged.withheld ? "依据结构待核·另有密级隐藏项" : "依据结构待核",
      hasUnverified: true,
      withheldOnly: false,
    };
  }
  if (merged.total === null) {
    return { text: "依据清单〔按密级隐藏〕", hasUnverified: false, withheldOnly: true };
  }
  let text = `依据 ${merged.total} 条（${merged.verified} 已核验 · ${merged.unverified} 未核）`;
  if (merged.level) text += ` · 置信度 ${merged.level}（模型自评）`;
  if (merged.withheld) text += "·另有密级隐藏项";
  return { text, hasUnverified: merged.unverified > 0, withheldOnly: false };
}

function flattenEvidence(findings) {
  if (!Array.isArray(findings)) return { valid: false, rows: [] };
  const rows = [];
  for (const finding of findings) {
    if (
      !finding
      || typeof finding !== "object"
      || !Array.isArray(finding.evidence)
      || finding.evidence.length === 0
    ) {
      return { valid: false, rows: [] };
    }
    for (const row of finding.evidence) {
      if (!isDisplayableEvidenceRow(row)) {
        return { valid: false, rows: [] };
      }
      rows.push(row);
    }
  }
  return { valid: true, rows };
}

export function buildEvidenceTrace({
  findings,
  withheld = false,
  requiredMissing = false,
} = {}) {
  if (withheld === true) {
    return [
      { id: "source", label: "依据来源", tone: "neutral", detail: "依据内容按密级隐藏" },
      { id: "resolution", label: "系统回源", tone: "neutral", detail: "回源详情不可见" },
      { id: "decision", label: "人工判断", tone: "pending", detail: "结论仍由有权限人员判断" },
    ];
  }

  const flattened = flattenEvidence(findings);
  if (!flattened.valid) {
    return [
      { id: "source", label: "依据来源", tone: "pending", detail: "依据结构待核" },
      { id: "resolution", label: "系统回源", tone: "pending", detail: "回源状态待核" },
      { id: "decision", label: "人工判断", tone: "pending", detail: "结论仍由人判断" },
    ];
  }

  const rows = flattened.rows;
  const unresolved = rows.filter((row) => row?.resolved !== true).length;
  let source;
  if (requiredMissing === true && rows.length === 0) {
    source = { tone: "pending", detail: "需要依据，但当前无可展示依据" };
  } else if (rows.length > 0) {
    source = { tone: "neutral", detail: `${rows.length} 条可展示依据` };
  } else {
    source = { tone: "neutral", detail: "暂无可展示依据" };
  }

  let resolution;
  if (rows.length === 0) {
    resolution = requiredMissing === true
      ? { tone: "pending", detail: "等待依据回源" }
      : { tone: "neutral", detail: "暂无回源记录" };
  } else if (unresolved > 0) {
    resolution = { tone: "pending", detail: `${unresolved} 条未回源核对` };
  } else {
    resolution = { tone: "neutral", detail: `${rows.length} 条已回源核对` };
  }

  return [
    { id: "source", label: "依据来源", ...source },
    { id: "resolution", label: "系统回源", ...resolution },
    { id: "decision", label: "人工判断", tone: "pending", detail: "回源不等于结论成立，仍由人判断" },
  ];
}

export function buildKnowledgeTrace(citations) {
  if (!Array.isArray(citations)) {
    return [
      { id: "source", label: "检索引用", tone: "pending", detail: "引用结构待核" },
      { id: "compare", label: "指纹比对", tone: "pending", detail: "比对信息不完整" },
      { id: "decision", label: "人工判断", tone: "pending", detail: "仍需人工核对原文" },
    ];
  }

  const source = citations.length > 0
    ? { tone: "neutral", detail: `${citations.length} 条检索引用` }
    : { tone: "neutral", detail: "暂无知识引用" };
  const drifted = citations.filter((item) =>
    typeof item?.searchFingerprint === "string"
    && typeof item?.currentFingerprint === "string"
    && item.searchFingerprint !== item.currentFingerprint
  ).length;
  const incomplete = citations.filter((item) =>
    typeof item?.searchFingerprint !== "string"
    || typeof item?.currentFingerprint !== "string"
  ).length;
  let compare;
  if (citations.length === 0) {
    compare = { tone: "neutral", detail: "暂无可比对记录" };
  } else if (drifted > 0) {
    compare = { tone: "pending", detail: `${drifted} 条语料已变动` };
  } else if (incomplete > 0) {
    compare = { tone: "pending", detail: "比对信息不完整" };
  } else {
    compare = { tone: "neutral", detail: "当前指纹一致" };
  }

  return [
    { id: "source", label: "检索引用", ...source },
    { id: "compare", label: "指纹比对", ...compare },
    { id: "decision", label: "人工判断", tone: "pending", detail: "引用仍需人工核对原文" },
  ];
}
