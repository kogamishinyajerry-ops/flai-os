import assert from "node:assert/strict";
import test from "node:test";

import { projectObserverEvents } from "./observer-contract.js";
import {
  EXECUTION_REALITY_FIXTURES,
  EXECUTION_STATUS_FIXTURES,
  RUNTIME_ADAPTER_FIXTURE_LABELS,
  VERIFIED_CANDIDATE_CONTEXT,
  makeCurrentProductionPartialFacts,
  makeVerifiedCandidateFacts,
  makeVerifiedRealityFacts,
  makeVerifiedStatusFacts,
} from "./runtime-observer-adapter.fixtures.js";
import {
  RUNTIME_OBSERVER_ADAPTER_VERSION,
  adaptRuntimeFactsToObserver,
} from "./runtime-observer-adapter.js";

function diagnosticCodes(result) {
  return result.diagnostics.map((item) => item.code);
}

test("current production-shaped facts remain settled without a unified ExecutionRun", () => {
  const result = adaptRuntimeFactsToObserver(makeCurrentProductionPartialFacts());

  assert.equal(RUNTIME_ADAPTER_FIXTURE_LABELS.currentPartial.includes("MUST-NOT-ANIMATE"), true);
  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("execution_run_partial"));
  assert.ok(diagnosticCodes(result).includes("artifact_digest_missing"));
  assert.ok(diagnosticCodes(result).includes("knowledge_authority_unresolved"));

  const snapshot = projectObserverEvents(result.observerEvents, VERIFIED_CANDIDATE_CONTEXT);
  assert.equal(snapshot.mode, "unknown");
  assert.equal(snapshot.motion, false);
});

test("missing exact task revision refuses projection before inspecting supplied facts", () => {
  const facts = makeVerifiedCandidateFacts();
  delete facts.binding.taskRevision;

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.deepEqual(diagnosticCodes(result), ["binding_invalid"]);
  assert.equal(result.diagnostics[0].blocksObservation, true);
});

test("verified facts without a read snapshot cannot reach the observer contract", () => {
  const facts = makeVerifiedCandidateFacts();
  delete facts.readSnapshot;

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_invalid"));
});

test("verified read facts map to one contract event without trusting free-text claims", () => {
  const result = adaptRuntimeFactsToObserver(makeVerifiedCandidateFacts());

  assert.equal(RUNTIME_OBSERVER_ADAPTER_VERSION, "flai.stage-c.runtime-observer-adapter.v3");
  assert.equal(result.observerEvents.length, 1);
  const [event] = result.observerEvents;
  assert.equal(event.source, "control-kernel");
  assert.equal(event.eventId, "observer:run-cfd-7:17");
  assert.equal(event.sequence, 17);
  assert.equal(event.reality, "REAL");
  assert.equal(event.kind, "working");
  assert.equal(event.action, "inspect");
  assert.equal(event.title, "正在核对受控工作对象");
  assert.doesNotMatch(event.title, /完成|显著|签发/);
  assert.doesNotMatch(event.detail, /完成|显著|签发/);
  assert.equal(event.preview.title, "APU_inlet_case.zip");
  assert.match(event.preview.primary, /^SHA-256 000000000000…$/);
  assert.deepEqual(event.evidenceRefs, [
    `read-snapshot:sha256:${"d".repeat(64)}`,
    "task-event:evt-knowledge-4@ordinal:43",
    "execution:run-cfd-7@observation:17",
    "backend:execution-broker-cfd-primary@adapter:flai-execution-broker:candidate-1",
    "reality-witness:REAL:witness-run-cfd-7-real-activity",
    `backend-receipt:sha256:${"1".repeat(64)}`,
    `sandbox-witness:sha256:${"2".repeat(64)}`,
    `running-witness:sha256:${"6".repeat(64)}`,
    `artifact:file-input-cfd-1@sha256:${"0".repeat(64)}`,
    `knowledge:cfd_rules:foundation-11.md:foundation11%234@${"a".repeat(64)}`,
  ]);
  assert.deepEqual(diagnosticCodes(result), ["knowledge_authority_unresolved"]);
  assert.equal(result.diagnostics[0].severity, "warning");
  assert.equal(result.diagnostics[0].blocksObservation, false);
  assert.doesNotMatch(
    JSON.stringify(result),
    /全部工作完成|进展显著|建议直接签发|入口湍流量|\/withheld\/|uploaded_by/,
  );
});

test("a REAL ExecutionRun without a backend reality witness fails closed", () => {
  const facts = makeVerifiedCandidateFacts();
  delete facts.executionRun.reality_witness;

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("execution_reality_witness_missing"));
});

test("REAL, MOCK, and TEST retain distinct backend witness provenance", async (t) => {
  const requiredRef = {
    REAL: "sandbox-witness:",
    MOCK: "mock-seal:",
    TEST: "test-fixture:",
  };

  assert.deepEqual(EXECUTION_REALITY_FIXTURES, ["REAL", "MOCK", "TEST"]);
  for (const reality of EXECUTION_REALITY_FIXTURES) {
    await t.test(reality, () => {
      const result = adaptRuntimeFactsToObserver(makeVerifiedRealityFacts(reality));

      assert.equal(result.observerEvents.length, 1);
      const [event] = result.observerEvents;
      assert.equal(event.reality, reality);
      assert.ok(event.evidenceRefs.some((ref) => (
        ref.startsWith(`reality-witness:${reality}:`)
      )));
      assert.ok(event.evidenceRefs.some((ref) => ref.startsWith(requiredRef[reality])));
      assert.equal(result.diagnostics.some((item) => item.blocksObservation), false);

      const snapshot = projectObserverEvents(
        result.observerEvents,
        VERIFIED_CANDIDATE_CONTEXT,
      );
      assert.equal(snapshot.reasonCode, "observed");
      assert.equal(snapshot.reality, reality);
      assert.equal(snapshot.motion, true);
    });
  }
});

test("REAL backend identity names the ExecutionBroker, not a Sandbox or Tool port", () => {
  const facts = makeVerifiedRealityFacts("REAL");
  const result = adaptRuntimeFactsToObserver(facts);

  assert.equal(facts.executionRun.backend.backend_kind, "execution-broker");
  assert.equal(facts.executionRun.backend.adapter_id, "flai-execution-broker");
  assert.ok(
    result.observerEvents[0].evidenceRefs.includes(
      "backend:execution-broker-cfd-primary@adapter:flai-execution-broker:candidate-1",
    ),
  );
  assert.ok(
    result.observerEvents[0].evidenceRefs.some((ref) => (
      ref.startsWith("sandbox-witness:")
    )),
  );
});

test("a witness from another backend cannot bless the ExecutionRun", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.reality_witness.backend_id = "sandbox-other";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(
    diagnosticCodes(result).includes("execution_reality_witness_identity_mismatch"),
  );
});

test("MOCK cannot acquire REAL witness semantics by changing a declaration", () => {
  const facts = makeVerifiedRealityFacts("MOCK");
  facts.executionRun.reality_witness.verification = "verified";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(
    diagnosticCodes(result).includes("execution_reality_witness_policy_conflict"),
  );
});

test("backend and reality identity are frozen into the same read snapshot", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.readSnapshot.executionFact.reality = "MOCK";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("an Adapter version cannot drift under the same fact-set digest", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.backend.adapter_version = "1.0.1";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("witness evidence cannot drift under the same witness id and fact-set digest", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.reality_witness.evidence_refs.push(
    `backend-receipt:sha256:${"b".repeat(64)}`,
  );

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("a backend witness newer than its ExecutionRun observation is rejected", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.reality_witness.observed_at = "2026-07-23T05:00:05.000Z";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("execution_reality_witness_time_invalid"));
});

test("waiting_review and terminal statuses stay settled across REAL, MOCK, and TEST", async (t) => {
  const expected = {
    waiting_review: {
      mode: "attention",
      action: "hold",
      eventId: "evt-review-5",
      realPhaseRef: "collect-witness:",
    },
    completed: {
      mode: "preview",
      action: "render",
      eventId: "evt-completed-5",
      realPhaseRef: "result-witness:",
    },
    failed: {
      mode: "failed",
      action: "stop",
      eventId: "evt-failed-5",
      realPhaseRef: "failure-witness:",
    },
    cancelled: {
      mode: "stopped",
      action: "stop",
      eventId: "evt-cancelled-5",
      realPhaseRef: "termination-witness:",
    },
  };
  const realityRef = {
    REAL: "sandbox-witness:",
    MOCK: "mock-seal:",
    TEST: "test-fixture:",
  };

  assert.deepEqual(
    EXECUTION_STATUS_FIXTURES,
    ["waiting_review", "completed", "failed", "cancelled"],
  );
  for (const status of EXECUTION_STATUS_FIXTURES) {
    for (const reality of EXECUTION_REALITY_FIXTURES) {
      await t.test(`${status}/${reality}`, () => {
        const result = adaptRuntimeFactsToObserver(
          makeVerifiedStatusFacts(status, { reality }),
        );

        assert.equal(result.observerEvents.length, 1);
        const [event] = result.observerEvents;
        assert.equal(event.reality, reality);
        assert.equal(event.action, expected[status].action);
        assert.ok(
          event.evidenceRefs.some((ref) => (
            ref.startsWith(`task-event:${expected[status].eventId}@ordinal:`)
          )),
        );
        assert.ok(
          event.evidenceRefs.some((ref) => ref.startsWith(realityRef[reality])),
        );
        if (reality === "REAL") {
          assert.ok(
            event.evidenceRefs.some((ref) => (
              ref.startsWith(expected[status].realPhaseRef)
            )),
          );
        }
        assert.equal(
          result.diagnostics.some((item) => item.blocksObservation),
          false,
        );

        const snapshot = projectObserverEvents(
          result.observerEvents,
          VERIFIED_CANDIDATE_CONTEXT,
        );
        assert.equal(snapshot.mode, expected[status].mode);
        assert.equal(snapshot.motion, false);
        assert.equal(snapshot.reality, reality);
        assert.equal(snapshot.reasonCode, "observed");
      });
    }
  }
});

test("completed never upgrades a TEST backend to REAL or human sign-off", () => {
  const result = adaptRuntimeFactsToObserver(makeVerifiedStatusFacts("completed"));
  const [event] = result.observerEvents;

  assert.equal(event.reality, "TEST");
  assert.equal(event.kind, "preview");
  assert.doesNotMatch(event.title, /REAL|已签发|人工批准/);
  assert.doesNotMatch(event.detail, /REAL|已签发|人工批准/);
  assert.equal(event.evidenceRefs.some((ref) => ref.includes("human-signoff")), false);
});

test("a cancelled run requires a termination-phase witness", () => {
  const facts = makeVerifiedStatusFacts("cancelled", { reality: "REAL" });
  facts.executionRun.reality_witness.phase = "activity";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(
    diagnosticCodes(result).includes("execution_reality_witness_state_conflict"),
  );
});

test("a REAL cancelled run without termination evidence cannot report stopped", () => {
  const facts = makeVerifiedStatusFacts("cancelled", { reality: "REAL" });
  facts.executionRun.reality_witness.evidence_refs = (
    facts.executionRun.reality_witness.evidence_refs
      .filter((ref) => !ref.startsWith("termination-witness:"))
  );

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(
    diagnosticCodes(result).includes(
      "execution_reality_witness_phase_evidence_missing",
    ),
  );
});

test("Adapter output passes the existing observer contract and enables motion only there", () => {
  const result = adaptRuntimeFactsToObserver(makeVerifiedCandidateFacts());
  const snapshot = projectObserverEvents(result.observerEvents, VERIFIED_CANDIDATE_CONTEXT);

  assert.equal(snapshot.reasonCode, "observed");
  assert.equal(snapshot.mode, "working");
  assert.equal(snapshot.motion, true);
  assert.equal(snapshot.reality, "REAL");
  assert.equal(snapshot.preview.title, "APU_inlet_case.zip");
  assert.equal(snapshot.stepLabel, "核对规则与对象");
});

test("replaying the same immutable read snapshot stays byte-idempotent", () => {
  const first = adaptRuntimeFactsToObserver(makeVerifiedCandidateFacts()).observerEvents[0];
  const second = adaptRuntimeFactsToObserver(makeVerifiedCandidateFacts()).observerEvents[0];
  const snapshot = projectObserverEvents([first, second], VERIFIED_CANDIDATE_CONTEXT);

  assert.deepEqual(first, second);
  assert.equal(snapshot.reasonCode, "observed");
  assert.equal(snapshot.eventId, "observer:run-cfd-7:17");
});

test("an unresolved current object blocks the observer instead of inventing a preview", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.current_object_ref = "file:missing";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("current_object_unresolved"));
});

test("a cross-task Artifact poisons the read set and cannot reach the right rail", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.artifacts[0].task_id = "task-other";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("artifact_identity_mismatch"));
});

test("one task event id with conflicting facts fails closed", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.taskEvents.items.push({
    ...facts.taskEvents.items.at(-1),
    level: "error",
  });

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("task_event_id_conflict"));
});

test("task_events appended after the declared read snapshot cannot be mixed into one observation", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.taskEvents.items.push({
    event_id: "evt-late-5",
    task_id: facts.binding.taskId,
    agent_id: "cfd_case_inspector",
    event_type: "agent_log",
    level: "info",
    message: "晚到事件",
    payload: {},
    created_at: "2026-07-23T05:00:04.500Z",
  });

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("a mutable poll label cannot masquerade as an immutable fact-set digest", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.readSnapshot.factSetDigest = "poll-2026-07-23T05:00:05Z";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_invalid"));
});

test("an ExecutionRun observation revision cannot drift past its read snapshot", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.observation_revision = 18;

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("an ExecutionRun observation newer than capturedAt cannot belong to the read snapshot", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.executionRun.observed_at = "2026-07-23T05:00:06.000Z";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_time_inconsistent"));
});

test("an Artifact digest from a later read cannot replace the snapshotted object", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.artifacts[0].sha256 = "1".repeat(64);

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("Knowledge citation source drift cannot be hidden behind the same chunk id", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.knowledgeEvidence[0].payload.hit_citations[0].source = "other-source.md";

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("knowledge_evidence_event_mismatch"));
});

test("matching Knowledge rows from a later read still cannot replace the snapshot citation", () => {
  const facts = makeVerifiedCandidateFacts();
  const laterFingerprint = "b".repeat(64);
  facts.taskEvents.items.at(-1).payload.hit_citations[0].fingerprint = laterFingerprint;
  facts.knowledgeEvidence[0].payload.hit_citations[0].fingerprint = laterFingerprint;

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("snapshot_manifest_mismatch"));
});

test("an evidence reference too long for the observer contract is blocked at the Adapter", () => {
  const facts = makeVerifiedCandidateFacts();
  facts.artifacts[0].id = "a".repeat(120);
  facts.executionRun.current_object_ref = `file:${facts.artifacts[0].id}`;
  facts.readSnapshot.artifactFacts[0].artifactId = facts.artifacts[0].id;

  const result = adaptRuntimeFactsToObserver(facts);

  assert.deepEqual(result.observerEvents, []);
  assert.ok(diagnosticCodes(result).includes("observer_reference_too_long"));
});

test("out-of-order Adapter deliveries still select the highest observation revision", () => {
  const olderFacts = makeVerifiedCandidateFacts();
  olderFacts.executionRun.observation_revision = 16;
  olderFacts.executionRun.observed_at = "2026-07-23T05:00:03.000Z";
  olderFacts.executionRun.reality_witness.observed_at = "2026-07-23T05:00:03.000Z";
  olderFacts.readSnapshot.factSetDigest = `sha256:${"e".repeat(64)}`;
  olderFacts.readSnapshot.executionFact.observationRevision = 16;
  olderFacts.readSnapshot.executionFact.realityWitnessObservedAt = (
    "2026-07-23T05:00:03.000Z"
  );
  const newerFacts = makeVerifiedCandidateFacts();
  newerFacts.executionRun.observation_revision = 18;
  newerFacts.executionRun.observed_at = "2026-07-23T05:00:05.000Z";
  newerFacts.executionRun.reality_witness.observed_at = "2026-07-23T05:00:05.000Z";
  newerFacts.readSnapshot.factSetDigest = `sha256:${"f".repeat(64)}`;
  newerFacts.readSnapshot.executionFact.observationRevision = 18;
  newerFacts.readSnapshot.executionFact.realityWitnessObservedAt = (
    "2026-07-23T05:00:05.000Z"
  );

  const older = adaptRuntimeFactsToObserver(olderFacts).observerEvents[0];
  const newer = adaptRuntimeFactsToObserver(newerFacts).observerEvents[0];
  const snapshot = projectObserverEvents([newer, older], {
    ...VERIFIED_CANDIDATE_CONTEXT,
    nowMs: Date.parse("2026-07-23T05:00:06.000Z"),
  });

  assert.equal(snapshot.reasonCode, "observed");
  assert.equal(snapshot.eventId, "observer:run-cfd-7:18");
  assert.equal(snapshot.motion, true);
});
