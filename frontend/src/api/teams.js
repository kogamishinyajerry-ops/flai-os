import { request } from "./client";

// 批八 ADR-0031：团队蓝本必须源自导引会话方案——只传会话 id，成员由服务端
// 从 recommendation 快照抽取并重验（前端绝不直传成员列表）。
export const createTeam = ({ name, conversationId }) =>
  request("/api/teams", {
    method: "POST",
    json: { name, conversation_id: conversationId },
  });

export const listTeams = () => request("/api/teams");

export const getTeam = (teamId) => request(`/api/teams/${teamId}`);

// 召集：items 逐席位补参；顺序无关（服务端按 seq 升序重排，绝不信任提交序）。
// 对账不过 → 422 detail.summon_errors 逐席位清单（整单拒发零写入）。
export const summonTeam = ({ teamId, items, conversationId, reviewRequestedFromUsername }) =>
  request(`/api/teams/${teamId}/summon`, {
    method: "POST",
    json: {
      conversation_id: conversationId || null,
      review_requested_from_username: reviewRequestedFromUsername || null,
      items: (items || []).map((it) => ({
        seq: it.seq,
        inputs: it.inputs || {},
        // 键名与 wire 格式同名（Codex R1 P1：此前读 camelCase 别名，调用方传
        // input_file_ids 被静默丢弃——file 席位上传后仍发空列表）。
        input_file_ids: it.input_file_ids || [],
      })),
    },
  });
