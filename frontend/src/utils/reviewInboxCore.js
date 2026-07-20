export function isReviewRequestedFrom(task, username) {
  return Boolean(
    task
    && typeof username === "string"
    && username.length > 0
    && task.review_requested_from_username === username
  );
}

export function validateReviewInboxPage(page, {
  expectedOffset,
  expectedSnapshotId = null,
  seenIds = new Set(),
} = {}) {
  if (!page || typeof page !== "object" || Array.isArray(page)) {
    throw new Error("review-inbox envelope is invalid");
  }
  if (page.schema_version !== "review-inbox/v1") {
    throw new Error("review-inbox schema_version is invalid");
  }
  if (!Array.isArray(page.items)) throw new Error("review-inbox items is invalid");
  if (typeof page.has_more !== "boolean") {
    throw new Error("review-inbox has_more must be boolean");
  }
  if (!Number.isInteger(expectedOffset) || expectedOffset < 0) {
    throw new Error("review-inbox expected offset is invalid");
  }
  if (typeof page.snapshot_id !== "string" || !/^[0-9a-f]{64}$/.test(page.snapshot_id)) {
    throw new Error("review-inbox snapshot is invalid");
  }
  if (expectedSnapshotId !== null && page.snapshot_id !== expectedSnapshotId) {
    throw new Error("review-inbox snapshot changed during pagination");
  }
  if (!Number.isInteger(page.total) || page.total < 0) {
    throw new Error("review-inbox total is invalid");
  }
  const pageIds = new Set();
  for (const item of page.items) {
    if (!item || typeof item !== "object" || typeof item.id !== "string" || !item.id) {
      throw new Error("review-inbox item id is invalid");
    }
    if (pageIds.has(item.id) || seenIds.has(item.id)) {
      throw new Error("review-inbox duplicate task id");
    }
    pageIds.add(item.id);
  }
  const consumed = expectedOffset + page.items.length;
  if (page.has_more === true) {
    if (!Number.isInteger(page.next_offset) || page.next_offset !== consumed || consumed >= page.total) {
      throw new Error("review-inbox next_offset is invalid");
    }
  } else if (page.next_offset !== null || consumed !== page.total) {
    throw new Error("review-inbox terminal page is inconsistent");
  }
  return page;
}
