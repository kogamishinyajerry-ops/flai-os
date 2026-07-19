import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const read = (path) => readFileSync(new URL(path, import.meta.url), "utf8");

test("QuestionCard is a separate accessible clarification surface", () => {
  const source = read("../src/components/QuestionCard.vue");
  for (const witness of ["<fieldset", "<legend", 'type="radio"', "<textarea", "提交回答", "aria-live", "role=\"alert\""]) {
    assert.match(source, new RegExp(witness.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")));
  }
  assert.match(source, /min-height:\s*44px/);
  assert.match(source, /outline:\s*2px solid var\(--focus-ring-clay\)/);
  assert.match(source, /outline-offset:\s*2px/);
  assert.match(source, /@media\s*\(max-width:\s*520px\)/);
  assert.match(source, /@media\s*\(prefers-reduced-motion:\s*reduce\)/);
  assert.match(source, /:aria-labelledby="headingId"/);
  assert.match(source, /`question-heading-\$\{props\.question\.id\}`/);
  assert.match(source, /emit\('refresh'\)/);
  assert.match(source, /重新核对/);
  assert.doesNotMatch(source, /trust-real|trust-signed|批准|驳回|签发|推荐选项|default/i);
  assert.doesNotMatch(source, /:hover[^}]*transform/s);
});

test("Question trust colors keep work, uncertainty, terminal, and request failure distinct", () => {
  const source = read("../src/components/QuestionCard.vue");
  const guide = read("../src/views/GuidePage.vue");

  assert.match(source, /requestFailed:\s*\{\s*type:\s*Boolean\s*\}/);
  assert.match(source, /visibleRequestFailure/);
  assert.match(source, /\.question-card\.is-pending\s*\{[^}]*border-left-color:\s*var\(--clay\)/s);
  assert.match(source, /\.question-card\.is-expired,[\s\S]*?\.question-card\.is-unknown\s*\{[^}]*border-left-color:\s*var\(--trust-pending\)/s);
  assert.match(source, /\.question-card\.is-answered,[\s\S]*?\.question-card\.is-superseded\s*\{[^}]*border-left-color:\s*var\(--hairline\)/s);
  assert.match(source, /\.question-error\s*\{\s*color:\s*var\(--trust-pending\);\s*\}/);
  assert.match(source, /\.question-error\.is-request-failure\s*\{\s*color:\s*var\(--trust-fail\);\s*\}/);
  assert.doesNotMatch(source, /\.question-unknown\s*\{[^}]*trust-fail/s);

  assert.match(guide, /const questionRequestFailed = reactive\(\{\}\)/);
  assert.match(guide, /:request-failed="questionRequestFailed\[m\.question\.id\] === true"/);
});

test("QuestionCard re-samples the wall clock at submit after a throttled expiry timer", () => {
  const source = read("../src/components/QuestionCard.vue");
  const start = source.indexOf("function submitAnswer()");
  const submit = source.slice(start, source.indexOf("\nscheduleExpiry();", start));

  assert.match(submit, /const submitNowMs = Date\.now\(\);/);
  assert.match(submit, /nowMs\.value = submitNowMs;/);
  assert.match(submit, /nowMs:\s*submitNowMs/);
  assert.ok(
    submit.indexOf("const submitNowMs = Date.now()")
      < submit.indexOf("validateQuestionSubmission"),
    "the exact submit-time clock sample must precede validation",
  );
});

test("QuestionCard submission ids use the secure UUID helper without Math.random", () => {
  const source = read("../src/components/QuestionCard.vue");
  const core = read("../src/utils/questionCardCore.js");

  assert.match(source, /createSecureSubmissionId,/);
  assert.match(source, /submissionId\.value = createSecureSubmissionId\(\)/);
  assert.doesNotMatch(source, /crypto\.randomUUID|Math\.random/);
  assert.doesNotMatch(core, /Math\.random/);
});

test("QuestionCard typography stays on the existing App font scale", () => {
  const source = read("../src/components/QuestionCard.vue");
  const declarations = [...source.matchAll(/font-size:\s*([^;]+);/g)].map((match) => match[1].trim());

  assert.ok(declarations.length > 0, "QuestionCard must declare its typography explicitly");
  for (const value of declarations) {
    assert.match(value, /^var\(--fs-(?:display-lg|display|title|h3|body|sm|xs|2xs)\)$/);
  }
});

test("Guide renders QuestionCard next to assistant prose and uses the dedicated Answer API", () => {
  const guide = read("../src/views/GuidePage.vue");
  const api = read("../src/api/conversations.js");
  assert.match(guide, /import QuestionCard from "\.\.\/components\/QuestionCard\.vue"/);
  assert.match(guide, /<QuestionCard/);
  assert.match(guide, /m\.question/);
  assert.match(guide, /:key="m\.message_id \|\| idx"/);
  assert.ok(
    guide.indexOf("<MarkdownLite") < guide.indexOf("<QuestionCard")
      && guide.indexOf("<QuestionCard") < guide.indexOf("<!-- 导引计划"),
    "QuestionCard must follow assistant prose and precede plan cards",
  );
  assert.match(guide, /const questionBusy = reactive\(\{\}\)/);
  assert.match(guide, /const questionErrors = reactive\(\{\}\)/);
  assert.match(guide, /const questionRequestTokens = new Map\(\)/);
  assert.match(guide, /isCurrentQuestionRequest\(requestToken\)/);
  assert.match(guide, /question_revision:\s*submission\.questionRevision/);
  assert.match(guide, /submission_id:\s*submission\.submissionId/);
  assert.match(guide, /appendCanonicalMessage\(result\.answer_message/);
  assert.match(guide, /appendCanonicalMessage\(result\.message/);
  assert.match(guide, /const canonicalUser = res\.user_message \|\|/);
  assert.match(guide, /result\.replayed !== true/);
  assert.match(guide, /err\?\.status === 409 \|\| err\?\.status === 0/);
  assert.match(guide, /reconcileConversationSnapshot\(\s*targetConversationId/);
  assert.match(guide, /@refresh="refreshQuestion\(m\.question\.id\)"/);
  assert.doesNotMatch(guide, /submitQuestionAnswer[\s\S]{0,2000}messages\.value\.push\(\{\s*role:\s*["']user["']/);
  assert.match(api, /export const answerQuestion/);
  assert.match(api, /questions\/\$\{questionId\}\/answer/);
  assert.doesNotMatch(api, /questions[^\n]+\/review/);
});

test("a pending Question owns the single write axis and disables the normal composer", () => {
  const guide = read("../src/views/GuidePage.vue");

  assert.match(guide, /hasPendingConversationQuestion/);
  assert.match(guide, /const hasPendingQuestion = computed\(/);
  assert.match(guide, /const composerWriteReady = computed\(/);
  assert.match(guide, /:disabled="sending \|\| !composerWriteReady"/);
  assert.match(guide, /if \(hasPendingQuestion\.value === true\)/);
  assert.match(guide, /scheduleQuestionExpiryGate/);

  const sendStart = guide.indexOf("async function send()");
  const pendingGate = guide.indexOf("hasPendingQuestion.value === true", sendStart);
  const optimisticPush = guide.indexOf("messages.value.push(optimisticMessage)", sendStart);
  assert.ok(pendingGate > sendStart && pendingGate < optimisticPush);
});

test("Guide recovery controls and scripted scrolling honor the existing design contract", () => {
  const guide = read("../src/views/GuidePage.vue");

  assert.doesNotMatch(guide, /var\(--(?:paper|line)\)/);
  assert.match(
    guide,
    /\.page-alert-action\.is-secondary\s*\{[\s\S]*?background:\s*var\(--surface-raised\);[\s\S]*?border:\s*1px solid var\(--hairline\);[\s\S]*?\}/,
  );
  assert.match(guide, /window\.matchMedia\("\(prefers-reduced-motion: reduce\)"\)\.matches === true/);
  assert.match(guide, /behavior:\s*reduceMotion \? "auto" : "smooth"/);
});
