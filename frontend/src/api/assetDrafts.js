import { request } from "./client.js";
import {
  buildAssetDraftPreviewRequest,
  normalizeAssetDraftPreview,
} from "../utils/assetDrafts.js";

export async function previewConversationAssetDraft(
  conversationId,
  generalization,
) {
  if (typeof conversationId !== "string" || conversationId.trim() === "") {
    throw new TypeError("生成资产草稿前必须绑定已保存会话");
  }
  const normalizedConversationId = conversationId.trim();
  const response = await request(
    `/api/conversations/${encodeURIComponent(normalizedConversationId)}/asset-draft-preview`,
    {
      method: "POST",
      json: buildAssetDraftPreviewRequest(generalization),
    },
  );
  return normalizeAssetDraftPreview(response, {
    expectedConversationId: normalizedConversationId,
  });
}
