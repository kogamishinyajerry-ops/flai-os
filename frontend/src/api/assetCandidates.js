import { request } from "./client.js";
import {
  buildAssetCandidateDecisionRequest,
  buildSkillPackageDecisionRequest,
  normalizeSkillPackage,
  normalizeSkillPackageReviewContent,
  verifySkillPackageDecisionResponse,
  verifyAssetCandidateIntegrity,
} from "../utils/assetCandidates.js";


function taskIdValue(taskId) {
  if (typeof taskId !== "string" || taskId.trim() === "") {
    throw new TypeError("资产候选必须绑定已完成任务");
  }
  return taskId.trim();
}


export async function createTaskAssetCandidate(taskId) {
  const normalizedTaskId = taskIdValue(taskId);
  const response = await request(
    `/api/tasks/${encodeURIComponent(normalizedTaskId)}/asset-candidate`,
    { method: "POST" },
  );
  return verifyAssetCandidateIntegrity(response, {
    expectedTaskId: normalizedTaskId,
  });
}


export async function getTaskAssetCandidate(taskId) {
  const normalizedTaskId = taskIdValue(taskId);
  const response = await request(
    `/api/tasks/${encodeURIComponent(normalizedTaskId)}/asset-candidate`,
  );
  return verifyAssetCandidateIntegrity(response, {
    expectedTaskId: normalizedTaskId,
  });
}


export async function decideAssetCandidate(candidateValue, action) {
  const candidate = await verifyAssetCandidateIntegrity(candidateValue, {
    expectedTaskId: candidateValue?.source?.task_id,
  });
  const candidateId = candidate.id;
  const response = await request(
    `/api/asset-candidates/${encodeURIComponent(candidateId)}/decision`,
    {
      method: "POST",
      json: buildAssetCandidateDecisionRequest(candidate, action),
    },
  );
  return verifyAssetCandidateIntegrity(response, {
    expectedTaskId: candidate.source.task_id,
  });
}


export async function decideSkillPackage(packageValue, action) {
  const packageRevision = normalizeSkillPackage(packageValue);
  const packageId = packageRevision.id;
  const response = await request(
    `/api/skill-packages/${encodeURIComponent(packageId)}/decision`,
    {
      method: "POST",
      json: buildSkillPackageDecisionRequest(packageRevision, action),
    },
  );
  return verifySkillPackageDecisionResponse(packageRevision, response, action);
}


export async function getSkillPackageReviewContent(packageValue) {
  const packageRevision = normalizeSkillPackage(packageValue);
  const response = await request(
    `/api/skill-packages/${encodeURIComponent(packageRevision.id)}/review-content`,
  );
  return normalizeSkillPackageReviewContent(response, {
    expectedPackageId: packageRevision.id,
    expectedPackageDigest: packageRevision.package_digest,
    expectedFiles: packageRevision.files,
  });
}
