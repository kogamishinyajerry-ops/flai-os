// Agent 人话名册（批次四 Q1）：agent_id → 注册表显示名（agents API 投影的
// name 字段，与 ⌘K Agent 结果同源）。模块级单例懒加载——行级扫读面共享一份，
// 不随任务轮询重拉。拉取失败=没有名册：map 保持为空，消费方经 taskDisplayName
// 诚实回退 id 切片，**绝不编名字**；loaded 不置位，下一个消费面挂载时可再试
// 一次（inflight 单发防抖，无重试风暴）。
import { reactive } from "vue";
import { listAgents } from "../api/agents";

const state = reactive({ map: {} });
let loaded = false;
let inflight = null;

export function useAgentNames() {
  if (!loaded && !inflight) {
    inflight = listAgents()
      .then((rows) => {
        const next = {};
        for (const a of rows || []) {
          if (a && a.id && a.name) next[a.id] = a.name;
        }
        state.map = next;
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
