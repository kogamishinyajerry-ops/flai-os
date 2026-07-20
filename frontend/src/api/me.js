import { request } from "./client.js";
import { validateReviewInboxPage } from "../utils/reviewInboxCore.js";

export function fetchMyContributions(since) {
  return request(`/api/me/contributions?since=${encodeURIComponent(since)}`);
}

export function fetchMyTasks(limit = 20) {
  return request(`/api/me/tasks?limit=${limit}`);
}

export function fetchReviewRoutingUsers() {
  return request("/api/me/review-routing-users", { cache: "no-store" });
}

export function fetchReviewInboxPage({ limit = 100, offset = 0, snapshotId = null } = {}) {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (snapshotId !== null) params.set("snapshot_id", snapshotId);
  return request(`/api/me/review-inbox?${params.toString()}`, { cache: "no-store" });
}

export async function fetchAllReviewInbox() {
  for (let attempt = 0; attempt < 3; attempt += 1) {
    const items = [];
    const seenIds = new Set();
    let offset = 0;
    let snapshotId = null;
    try {
      while (true) {
        const raw = await fetchReviewInboxPage({ limit: 100, offset, snapshotId });
        const page = validateReviewInboxPage(raw, {
          expectedOffset: offset,
          expectedSnapshotId: snapshotId,
          seenIds,
        });
        if (snapshotId === null) snapshotId = page.snapshot_id;
        for (const item of page.items) {
          seenIds.add(item.id);
          items.push(item);
        }
        if (page.has_more === false) return items;
        offset = page.next_offset;
      }
    } catch (error) {
      if (error?.status === 409 && attempt < 2) continue;
      throw error;
    }
  }
  throw new Error("签收件箱快照持续变化，请稍后重试");
}
