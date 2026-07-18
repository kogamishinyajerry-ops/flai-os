// Agent 人话名册（批次四 Q1）：agent_id → 注册表显示名（agents API 投影的
// name 字段，与 ⌘K Agent 结果同源）。模块级单例懒加载——行级扫读面共享一份，
// 不随任务轮询重拉。拉取失败=没有名册：map 保持为空，消费方经 taskDisplayName
// 诚实回退 id 切片，**绝不编名字**；loaded 不置位，下一个消费面挂载时可再试
// 一次（inflight 单发防抖，无重试风暴）。
//
// 批七 §3-9：同源扩投 meta = agent_id → { domain, clearance, charter, … }
// （expertise/clearance 为 S1 additive 投影，存量包缺省 → 字段 undefined，
// 消费面条件渲染零占位）。map 保持纯 name 字符串不动——既有消费者
// （taskDisplayName 等）零改。
import { reactive } from "vue";
import { listAgents } from "../api/agents";

const state = reactive({ map: {}, meta: {} });
let loaded = false;
let inflight = null;

export function useAgentNames() {
  if (!loaded && !inflight) {
    inflight = listAgents()
      .then((rows) => {
        const next = {};
        const nextMeta = {};
        for (const a of rows || []) {
          if (a && a.id && a.name) next[a.id] = a.name;
          if (a && a.id) {
            nextMeta[a.id] = {
              domain: a.expertise?.domain,
              specialty: a.expertise?.specialty,
              usefulness: a.expertise?.usefulness_level,
              charter: a.expertise?.charter,
              clearance: a.clearance,
              evidenceRequired: a.evidence_policy_required === true,
            };
          }
        }
        state.map = next;
        state.meta = nextMeta;
        loaded = true;
      })
      .catch(() => {
        // 失败静默：名册是增益层不是数据层，缺位时行级主文本回退 id 切片。
      })
      .finally(() => {
        inflight = null;
      });
  }
  return state;
}
