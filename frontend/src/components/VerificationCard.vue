<template>
  <!-- 核验自证段（批次二 F3，kit11 成果卡「校验方式」语法 × FLAi-OS 假绿哲学）：
       成果不只报「做了什么」，还要给出「怎么核验它是真的」。仅终态与
       waiting_review 渲染（签发前最后一眼），三行全部是已落库数据的忠实投影
       ——凑不出数据的行整行降级或不渲染，绝不推断。
       信任色锁审计：amber=仅未核（mock 披露/待签）· teal=仅人签 · 红=仅驳回/
       真失败计数 ·「均为真实执行」用中性墨**不给绿**——绿解锁是性能盘真结果
       接入后的项目级决策，本组件不越权。 -->
  <div v-if="visible" class="verify-card">
    <h3 class="verify-title">
      <el-icon aria-hidden="true"><DocumentChecked /></el-icon>
      核验三面
    </h3>

    <!-- ①工具真实性：数据源只认 tool_runs 落库记录（runner 如实记 mock 位），
         措辞限定在「记录」层，不越权声称运行时真相；拉取失败诚实降级为
         「不可用」（中性——网络失败≠任务失败，红不外借）。 -->
    <div class="verify-row">
      <el-icon class="verify-icon" aria-hidden="true"><Tools /></el-icon>
      <span class="verify-label">工具</span>
      <span v-if="toolState === 'loading'" class="verify-muted">核验信息加载中…</span>
      <span v-else-if="toolState === 'error'" class="verify-muted">工具核验信息不可用（拉取失败）</span>
      <span v-else-if="toolStats.total === 0" class="verify-muted">无工具调用记录</span>
      <span v-else-if="toolStats.mock > 0" class="verify-text">
        <span class="num-token">{{ toolStats.total }}</span> 次工具调用 · 含 <span class="num-token">{{ toolStats.mock }}</span> 次 mock
        <span class="pill-amber">未经真实核验</span>
      </span>
      <span v-else class="verify-text">
        <span class="num-token">{{ toolStats.total }}</span> 次工具调用 · 均为真实执行
      </span>
    </div>

    <!-- ②人工签发：与 WorkLog 口播真·同源（utils/format deriveSignoff+
         signoffText 同一谓词同一措辞——3-lens paradigm P3 抓过两处措辞漂移），
         report 级与时间轴级双呈现不矛盾——kit11 语法点即「核验线索必须在
         报告层有汇总位」。redacted 态（3-lens trust P1）：review_* 事件在场但
         payload 被分级门遮蔽（ADR-0025）——中性「不可用」，绝不把「已签发但
         内容受限」呈现成「未经签发」；「未经人工签发流程」严格收窄到 events
         里根本不存在 review_* 事件。 -->
    <div class="verify-row">
      <el-icon class="verify-icon" aria-hidden="true"><UserFilled /></el-icon>
      <span class="verify-label">签发</span>
      <span v-if="signoff && signoff.redacted" class="verify-muted">签发记录不可用（内容受限）</span>
      <!-- unknown（Codex R0-P2）：无遮蔽标记的缺字段=「不完整」，不编「受限」。 -->
      <span v-else-if="signoff && signoff.unknown" class="verify-muted">签发记录不完整</span>
      <span
        v-else-if="signoff"
        class="verify-text verify-signoff"
        :style="{ color: signoff.approved ? 'var(--trust-signed)' : 'var(--trust-fail)' }"
        :title="signoff.comment || undefined"
      >{{ signoffText(signoff) }}</span>
      <span v-else-if="isWaitingReview" class="verify-text verify-pending">待人工签发</span>
      <span v-else class="verify-muted">未经人工签发流程</span>
    </div>

    <!-- ③批量结果：有 summary_generated 事件才渲染（batchSummary=null 整行
         不出现，不编「成功 0 · 失败 0」）。 -->
    <div v-if="batchSummary" class="verify-row">
      <el-icon class="verify-icon" aria-hidden="true"><DataAnalysis /></el-icon>
      <span class="verify-label">批量</span>
      <span class="verify-text">
        成功 <span class="num-token">{{ batchSummary.ok }}</span> · 失败
        <span class="num-token" :class="{ 'verify-fail-count': batchSummary.failed > 0 }">{{ batchSummary.failed }}</span>
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from "vue";
import { DataAnalysis, DocumentChecked, Tools, UserFilled } from "@element-plus/icons-vue";
import { getToolRunsSummary } from "../api/tasks";
import { deriveSignoff, signoffText } from "../utils/format";

const props = defineProps({
  task: { type: Object, default: null },
  events: { type: Array, default: () => [] },
  batchSummary: { type: Object, default: null },
});

// 渲染窗=completed/failed/waiting_review：有成果或有签发裁决才有「核验」可言；
// cancelled 是中断（不进签发流、无成果语义），渲染核验段只添噪音——显式排除。
const VERIFY_STATUSES = ["completed", "failed", "waiting_review"];
const isWaitingReview = computed(() => props.task?.status === "waiting_review");
const visible = computed(() => VERIFY_STATUSES.includes(props.task?.status));

// ── ①工具真实性：状态进入渲染窗（waiting_review/终态）各拉一次**计数投影**
// （GET tool_runs/summary，Codex R0-P2：全量明细会把批量任务的 input/output
// 轨迹整条搬给前端，本卡只要两个数）。waiting→completed 迁移后补拉一次（放行
// 后 runner 可能补写收尾 run），同状态轮询绝不重复请求（lastFetchedStatus
// 守卫）。与 WorkLog 展开态的懒加载明细互不依赖：那边要逐工具徽标（必须明细），
// 这边只要汇总计数。 ──
const toolSummary = ref(null); // null=未加载/加载中；{total, mock_count}=已加载
const toolError = ref(false);
let lastFetchedStatus = null;
// 请求世代守卫（Codex R1-P2）：waiting→completed 迁移会在首请求在途时发起第二
// 请求——只许「最新一次发起」落盘，迟到的旧响应（成功或失败）整包作废，否则
// 旧失败会抹掉新成功（永久「不可用」）、反序会装入 stale 计数。与 TaskDetail
// feedbackSeq 同 house pattern。
let fetchSeq = 0;

watch(() => props.task?.status, (s) => {
  if (!VERIFY_STATUSES.includes(s)) return;
  if (s === lastFetchedStatus) return;
  lastFetchedStatus = s;
  toolError.value = false;
  const seq = ++fetchSeq;
  getToolRunsSummary(props.task.id)
    .then((sum) => {
      if (seq !== fetchSeq) return; // stale 响应作废
      // 形状校验：畸形响应=「不可用」而非 0 计数——0 是「无工具调用记录」的
      // 确信性断言，凑不出数据绝不冒充（假绿死罪）。
      if (!sum || typeof sum.total !== "number" || typeof sum.mock_count !== "number") {
        toolError.value = true;
        toolSummary.value = null;
        lastFetchedStatus = null;
        return;
      }
      toolSummary.value = sum;
    })
    .catch(() => {
      if (seq !== fetchSeq) return; // stale 失败不得抹掉新结果
      // 诚实降级：拉取失败=「不可用」，绝不把未知呈现成「无 mock」（假绿死罪）。
      // 复位守卫：下次状态迁移可重试。
      toolError.value = true;
      toolSummary.value = null;
      lastFetchedStatus = null;
    });
}, { immediate: true });

const toolState = computed(() => {
  if (toolError.value) return "error";
  if (toolSummary.value === null) return "loading";
  return "ready";
});
const toolStats = computed(() => {
  const s = toolSummary.value;
  return { total: s ? s.total : 0, mock: s ? s.mock_count : 0 };
});

// ── ②人工签发：SSOT=utils/format deriveSignoff（三态：null=从未签发 /
// redacted=有签发但内容被分级门遮蔽 / 完整记录），与 WorkLog 同一份谓词。 ──
const signoff = computed(() => deriveSignoff(props.events));
</script>

<style scoped>
/* 外距由宿主 class="section"（margin-top 24px）供给。标题样式自持——宿主的
   .section h3 是 scoped 规则（选择器尾项打宿主 data-v），进不了子组件内部，
   此处按同值复刻保持同屏节奏一致（15px/600/ink/底距 12px）。 */
.verify-title {
  display: flex;
  align-items: center;
  gap: 7px;
  margin: 0 0 12px;
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
}
.verify-title > .el-icon {
  width: 28px;
  height: 28px;
  border: 1px solid var(--hairline);
  border-radius: 8px;
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 16px;
}
.verify-row {
  display: flex;
  align-items: baseline;
  gap: 10px;
  padding: 5px 0;
  font-size: 12.5px;
}
.verify-icon {
  flex: none;
  width: 26px;
  height: 26px;
  border-radius: 8px;
  background: var(--paper-rail);
  color: var(--ink-soft);
  font-size: 15px;
}
.verify-row + .verify-row {
  border-top: 1px solid var(--hairline-soft);
}
.verify-label {
  flex: none;
  width: 34px;
  color: var(--ink-faint);
  font-size: 11.5px;
}
.verify-text {
  color: var(--ink-soft);
}
.verify-muted {
  color: var(--ink-faint);
}
.verify-signoff {
  font-weight: 600;
}
/* 待签=amber 未核槽（与全站 pill-amber/--trust-pending 同语义，不新增色槽） */
.verify-pending {
  color: var(--trust-pending);
  font-weight: 600;
}
/* 失败计数染红仅当 >0（红=仅真失败；0 不染——零值不制造情绪） */
.verify-fail-count {
  color: var(--trust-fail);
}
</style>
