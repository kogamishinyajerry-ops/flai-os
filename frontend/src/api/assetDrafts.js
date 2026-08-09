import { request } from "./client.js";
import {
  buildAssetDraftPreviewRequest,
  normalizeAssetDraftPreview,
} from "../utils/assetDrafts.js";
import {
  normalizeGeneralizationDraftRecord,
  normalizeGeneralizationDraftRecordPreviewEnvelope,
} from "../utils/lifeDraft.js";

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

/**
 * 持久化 Generalization Draft 的只读投影入口。
 * 与上面的手工 AssetBuilderDrawer v1 入口并存：这里绝不回传 payload，只提交
 * record content digest 作为 CAS，响应还必须逐项咬合原 record。
 */
export async function previewGeneralizationDraftRecord(conversationId, record) {
  if (typeof conversationId !== "string" || conversationId.trim() === "") {
    throw new TypeError("投影持久草稿前必须绑定已保存会话");
  }
  const normalizedConversationId = conversationId.trim();
  const normalizedRecord = normalizeGeneralizationDraftRecord(record, {
    conversationId: normalizedConversationId,
    assistantMessageId: record?.lineage?.assistant_message_id ?? null,
  });
  const response = await request(
    `/api/conversations/${encodeURIComponent(normalizedConversationId)}` +
      `/generalization-draft-records/${encodeURIComponent(normalizedRecord.id)}` +
      "/asset-draft-preview",
    {
      method: "POST",
      json: {
        schema_version: "generalization_draft_record_preview_request.v1",
        expected_content_digest: normalizedRecord.content_digest,
      },
    },
  );
  const envelope = normalizeGeneralizationDraftRecordPreviewEnvelope(response, {
    expectedRecord: normalizedRecord,
  });
  return {
    ...envelope,
    asset_draft: normalizeAssetDraftPreview(envelope.asset_draft, {
      expectedConversationId: normalizedConversationId,
    }),
  };
}
