import { request, unwrapDetail } from "./client.js";
import {
  buildCandidateSelectionPayload,
  buildComparisonCreatePayload,
  buildPublishPayload,
  buildReleaseDecisionPayload,
  buildReleaseRequestPayload,
  buildRollbackPayload,
  validateDesignComparisonEnvelope,
  validateDesignPublishResult,
  validateDesignReleaseDecision,
  validateDesignReleaseRequest,
  validateDesignRollbackResult,
  validateDesignSelection,
  validateDesignPathId,
} from "../utils/designPromotionCore.js";

function pathId(value, field) {
  return encodeURIComponent(validateDesignPathId(value, field));
}

export function sensitiveCandidateRoleAxisMessage(err) {
  if (err?.status !== 403) return null;
  const detail = unwrapDetail(err.detail);
  if (!detail || typeof detail !== "object" || Array.isArray(detail)) return null;
  const keys = Object.keys(detail).sort();
  if (keys.length !== 2 || keys[0] !== "code" || keys[1] !== "message") return null;
  if (
    detail.code !== "sensitive_candidate_requires_role_axis" ||
    typeof detail.message !== "string" ||
    detail.message.trim() === ""
  ) {
    return null;
  }
  return detail.message;
}

export async function createDesignComparison(input) {
  const response = await request("/api/design-comparisons", {
    method: "POST",
    json: buildComparisonCreatePayload(input),
  });
  return validateDesignComparisonEnvelope(response);
}

export async function getDesignComparison(comparisonId) {
  const response = await request(
    `/api/design-comparisons/${pathId(comparisonId, "comparison_id")}`,
    { cache: "no-store" },
  );
  return validateDesignComparisonEnvelope(response);
}

export async function submitDesignSelection(comparisonId, input) {
  const response = await request(
    `/api/design-comparisons/${pathId(comparisonId, "comparison_id")}/selection`,
    { method: "POST", json: buildCandidateSelectionPayload(input) },
  );
  return validateDesignSelection(response);
}

export async function createDesignReleaseRequest(input) {
  const response = await request("/api/design-release-requests", {
    method: "POST",
    json: buildReleaseRequestPayload(input),
  });
  return validateDesignReleaseRequest(response);
}

export async function decideDesignReleaseRequest(releaseRequestId, input) {
  const response = await request(
    `/api/design-release-requests/${pathId(releaseRequestId, "release_request_id")}/decision`,
    { method: "POST", json: buildReleaseDecisionPayload(input) },
  );
  return validateDesignReleaseDecision(response);
}

export async function publishDesignRelease(releaseRequestId, input) {
  const response = await request(
    `/api/design-release-requests/${pathId(releaseRequestId, "release_request_id")}/publish`,
    { method: "POST", json: buildPublishPayload(input) },
  );
  return validateDesignPublishResult(response);
}

export async function rollbackDesignRelease(releaseRequestId, input) {
  const response = await request(
    `/api/design-release-requests/${pathId(releaseRequestId, "release_request_id")}/rollback`,
    { method: "POST", json: buildRollbackPayload(input) },
  );
  return validateDesignRollbackResult(response);
}
