import { request } from "./client";

export function fetchMyContributions(since) {
  return request(`/api/me/contributions?since=${encodeURIComponent(since)}`);
}

export function fetchMyTasks(limit = 20) {
  return request(`/api/me/tasks?limit=${limit}`);
}
