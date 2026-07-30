const MATURITY_LEVELS = ["L0", "L1", "L2", "L3"];
const REQUIRED_PROMOTION_CHECKS = [
  "transition_supported",
  "min_eval_coverage",
  "eval_evidence",
  "changelog_nonempty",
  "feedback_channel",
  "manual_confirmation",
  "package_snapshot",
];

export const PROMOTION_CHECK_LABELS = {
  transition_supported: "晋升路径",
  min_eval_coverage: "评测覆盖",
  eval_evidence: "评测证据",
  changelog_nonempty: "变更记录",
  feedback_channel: "反馈通道",
  manual_confirmation: "人工确认",
  package_snapshot: "包快照",
};

function nonblank(value) {
  return typeof value === "string" && value.trim() !== "";
}

function nonnegativeInteger(value) {
  return Number.isInteger(value) && value >= 0;
}

export function buildMaturityLadder(maturity) {
  const currentIndex = MATURITY_LEVELS.indexOf(maturity);
  const known = currentIndex >= 0;
  return {
    known,
    items: MATURITY_LEVELS.map((level, index) => ({
      level,
      reached: known && index <= currentIndex,
      current: known && index === currentIndex,
      outOfScope: index >= 2,
    })),
  };
}

export function summarizeEvalRun(run) {
  if (!run || typeof run !== "object") {
    return { tone: "pending", detail: "尚未跑过评测", evidenceReady: false };
  }
  if (run.status === "queued") {
    return { tone: "pending", detail: "评测已入队，等待执行", evidenceReady: false };
  }
  if (run.status === "running") {
    return { tone: "work", detail: "评测执行中", evidenceReady: false };
  }
  if (run.status === "error" || run.status === "failed") {
    return { tone: "fail", detail: "评测执行错误，结果不可作为证据", evidenceReady: false };
  }
  if (run.status !== "completed") {
    return { tone: "pending", detail: "评测状态待核", evidenceReady: false };
  }

  const counts = [run.total, run.passed, run.failed, run.skipped];
  if (!counts.every(nonnegativeInteger)) {
    return { tone: "pending", detail: "评测结果字段待核", evidenceReady: false };
  }
  if (run.passed + run.failed + run.skipped !== run.total) {
    return { tone: "pending", detail: "评测计数未对上", evidenceReady: false };
  }
  if (!Array.isArray(run.case_results)) {
    return { tone: "pending", detail: "评测用例明细待核", evidenceReady: false };
  }
  if (run.case_results.length !== run.total) {
    return { tone: "pending", detail: "评测用例明细未对上", evidenceReady: false };
  }
  if (run.total === 0) {
    return { tone: "neutral", detail: "评测完成 · 无有效用例", evidenceReady: true };
  }

  const invalidVerdict = run.case_results.some((item) =>
    !["passed", "failed", "skipped"].includes(item?.verdict)
  );
  if (invalidVerdict) {
    return { tone: "pending", detail: "评测判定字段待核", evidenceReady: false };
  }
  if (run.failed > 0 || run.case_results.some((item) => item.verdict === "failed")) {
    return {
      tone: "fail",
      detail: `通过 ${run.passed}/${run.total} · 含 ${run.failed} 个失败`,
      evidenceReady: true,
    };
  }
  if (run.skipped > 0 || run.case_results.some((item) => item.verdict === "skipped")) {
    return {
      tone: "pending",
      detail: `通过 ${run.passed}/${run.total} · 含 ${run.skipped} 个跳过`,
      evidenceReady: true,
    };
  }
  if (
    run.passed === run.total
    && run.case_results.every((item) => item.verdict === "passed")
  ) {
    return {
      tone: "real",
      detail: `评测结果全部通过 ${run.passed}/${run.total}`,
      evidenceReady: true,
    };
  }
  return { tone: "pending", detail: "评测结果待核", evidenceReady: false };
}

export function promotionIdentity(promotion) {
  if (!promotion || typeof promotion !== "object") {
    return { tone: "pending", detail: "晋升身份记录待核" };
  }
  const actor = nonblank(promotion.confirmed_by)
    ? promotion.confirmed_by.trim()
    : "记名人待核";
  if (
    promotion.signer_source === "authenticated_session"
    && promotion.signer_session_bound === true
    && nonblank(promotion.confirmed_by)
  ) {
    return { tone: "signed", detail: `${actor} · 认证会话记名` };
  }
  if (promotion.signer_source === "server_cli" && nonblank(promotion.confirmed_by)) {
    return { tone: "neutral", detail: `${actor} · 服务器 CLI 来源` };
  }
  return { tone: "pending", detail: `${actor} · 身份来源待核` };
}

export function promotionChecksSummary(checks) {
  if (!checks || typeof checks !== "object" || Array.isArray(checks)) {
    return { tone: "pending", detail: "准入判定记录待核" };
  }
  const allValues = Object.values(checks).map((check) => check?.ok);
  if (allValues.some((value) => value === false)) {
    const failed = allValues.filter((value) => value === false).length;
    return { tone: "fail", detail: `服务端准入记录含 ${failed} 项未通过` };
  }
  const requiredValues = REQUIRED_PROMOTION_CHECKS.map((name) => checks[name]?.ok);
  if (
    requiredValues.every((value) => value === true)
    && allValues.length >= REQUIRED_PROMOTION_CHECKS.length
    && allValues.every((value) => value === true)
  ) {
    return { tone: "real", detail: "服务端准入记录全部通过" };
  }
  return { tone: "pending", detail: "准入判定记录不完整" };
}

/**
 * 评测通过率趋势点：只画 summarizeEvalRun 判定「字段与用例明细严格对上」的
 * 已完成跑批（evidenceReady）——畸形/在途/报错 run 一律剔除，未知计数绝不
 * 压成 0。pct=null 表示 total=0「无有效用例」；tone 直接承袭 summarizeEvalRun
 * 的信任色（real=严格全通过才给绿，fail=真实失败，pending=含跳过待核，
 * neutral=无有效用例恒中性）。返回旧→新（时间轴左旧右新），最多 limit 条。
 */
export function buildEvalTrend(runs, { limit = 8 } = {}) {
  if (!Array.isArray(runs)) return [];
  return runs
    .filter((run) => summarizeEvalRun(run).evidenceReady === true)
    .slice(0, limit)
    .map((run) => ({
      id: run.id,
      passed: run.passed ?? 0,
      total: run.total ?? 0,
      pct: run.total > 0 ? Math.round((run.passed / run.total) * 100) : null,
      at: run.finished_at || run.started_at,
      tone: summarizeEvalRun(run).tone,
    }))
    .reverse();
}

export function buildGovernanceJourney({
  maturity,
  curatedCasesCount = null,
  latestRun = null,
  promotionConfirmed = false,
  promotions = [],
} = {}) {
  const countKnown = nonnegativeInteger(curatedCasesCount);
  const runSummary = summarizeEvalRun(latestRun);
  const promotionRecords = Array.isArray(promotions) ? promotions : [];
  const runId = nonblank(latestRun?.id) ? latestRun.id : null;
  // 只有明确引用当前评测 run 的晋升记录才可接入同一闭环。旧晋升仍由下方
  // 历史时间线展示，但绝不能借新评测结果拼成一条连续证据链。
  const matchedPromotion = runId
    ? promotionRecords.find((item) =>
      item && typeof item === "object" && item.eval_run_id === runId
    ) || null
    : null;
  const identity = matchedPromotion ? promotionIdentity(matchedPromotion) : null;

  let dispatch;
  if (!latestRun || typeof latestRun !== "object") {
    dispatch = { tone: "pending", detail: "等待发起评测" };
  } else if (latestRun.status === "queued") {
    dispatch = { tone: "pending", detail: "已入队" };
  } else if (latestRun.status === "running") {
    dispatch = { tone: "work", detail: "正在执行" };
  } else if (latestRun.status === "error" || latestRun.status === "failed") {
    dispatch = { tone: "fail", detail: "执行已报错" };
  } else if (latestRun.status === "completed") {
    dispatch = { tone: "neutral", detail: "调度已收口" };
  } else {
    dispatch = { tone: "pending", detail: "调度状态待核" };
  }

  let confirmation;
  if (promotionConfirmed === true) {
    confirmation = { tone: "pending", detail: "已选择，提交成功后才记名" };
  } else if (identity?.tone === "signed") {
    confirmation = identity;
  } else if (identity?.tone === "neutral") {
    confirmation = identity;
  } else if (runId && promotionRecords.length > 0) {
    confirmation = { tone: "pending", detail: "当前评测尚无对应人工确认" };
  } else {
    confirmation = { tone: "pending", detail: "等待人工确认" };
  }

  const promotion = matchedPromotion
    ? { ...identity }
    : runId && promotionRecords.length > 0
      ? { tone: "pending", detail: "当前评测尚无对应晋升记录" }
    : promotionRecords.length > 0
      ? { tone: "pending", detail: "历史晋升记录未接入当前评测闭环" }
    : buildMaturityLadder(maturity).known && maturity !== "L0"
      ? { tone: "pending", detail: "成熟度已变化，晋升记录待核" }
      : { tone: "neutral", detail: "尚无晋升记录" };

  return [
    {
      id: "cases",
      label: "固化用例",
      tone: countKnown ? "neutral" : "pending",
      detail: countKnown
        ? curatedCasesCount > 0
          ? `仓内 ${curatedCasesCount} 个用例`
          : "仓内无固化用例"
        : "用例数量待核",
    },
    { id: "dispatch", label: "评测调度", ...dispatch },
    { id: "result", label: "真实结果", ...runSummary },
    { id: "confirmation", label: "人工确认", ...confirmation },
    {
      id: "gate",
      label: "服务端准入门",
      ...(matchedPromotion
        ? promotionChecksSummary(matchedPromotion.checks)
        : { tone: "pending", detail: "等待服务端准入复核" }),
    },
    { id: "promotion", label: "晋升记录", ...promotion },
  ];
}
