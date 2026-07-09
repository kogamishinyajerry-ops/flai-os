import { request } from "./client";

// 与后端 api/feedback.py 契约一致：rating ∈ good|bad；category 见后端 Literal 枚举；
// created_by 必填具名（空白 422）。agent_id/agent_version 服务端自填，前端不传。
export const submitFeedback = ({ taskId, rating, category, message, createdBy }) =>
  request("/api/feedback", {
    method: "POST",
    json: {
      task_id: taskId,
      rating,
      category,
      message: message || null,
      created_by: createdBy,
    },
  });

export const listTaskFeedback = (taskId) => request(`/api/tasks/${taskId}/feedback`);

export const FEEDBACK_CATEGORIES = [
  { value: "result_wrong", label: "结果错误" },
  { value: "result_incomplete", label: "结果不完整" },
  { value: "tool_error", label: "工具报错" },
  { value: "usability", label: "易用性问题" },
  { value: "suggestion", label: "改进建议" },
  { value: "other", label: "其他" },
];
