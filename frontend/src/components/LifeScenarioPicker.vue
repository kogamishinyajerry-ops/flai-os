<template>
  <!--
    本体论教学 demo 的场景选择入口(ADR-0033 合规)。
    纯按钮级动作:三选一(做饭/旅行/装修),选完 emit select,父组件进 life_guide_agent 对话。
    不是表单、不是字段编辑器、不绑参数——只是 ADR-0033 允许的"清晰按钮动作"。

    受众:FDE 团队(纯动力工程师,不写代码)。三比喻写在 prompt.md 里,
    这个组件只做"今天想用哪段经历学本体论"的单一选择。
  -->
  <div class="life-picker">
    <header class="life-picker__head fx-rise">
      <FlaiBloom class="life-picker__mark" :size="34" />
      <p class="life-picker__greeting">本体论教学 demo</p>
      <h1 class="life-picker__title">挑一段生活经历,走一遍建模闭环</h1>
      <p class="life-picker__hint">
        本体论不是玄学。把一段做饭、旅行、装修的真实经历讲清楚,系统会把它投影成
        一份带钢印的待审候选——审核权在你手里。这是 5 分钟看懂 {{ PLATFORM_NAME }} 本体论的入口。
      </p>
    </header>

    <div class="life-picker__grid">
      <button
        v-for="s in scenarios"
        :key="s.id"
        type="button"
        class="life-card"
        :class="['life-card--' + s.id]"
        @click="$emit('select', s.id)"
      >
        <span class="life-card__emoji" aria-hidden="true">{{ s.emoji }}</span>
        <span class="life-card__title">{{ s.title }}</span>
        <span class="life-card__focus">{{ s.focus }}</span>
        <span class="life-card__stars" aria-hidden="true">{{ s.stars }}</span>
        <span class="life-card__cta">讲这段经历 →</span>
      </button>
    </div>

    <footer class="life-picker__foot">
      <p>
        demo 产出的 Skill Package 进隔离区,不进生产复用池。
        工程任务(振动/性能盘/FTA)走
        <router-link to="/" class="life-picker__link">主对话</router-link>。
      </p>
    </footer>
  </div>
</template>

<script setup>
import FlaiBloom from "./artwork/FlaiBloom.vue";
import { PLATFORM_NAME } from "../utils/branding";

// 三个场景渐进设计(详见 docs/design/ONTOLOGY-DEMO-LIFE-SCENARIOS.md):
// cooking ★☆☆ 单 Skill 完整闭环;travel ★★☆ 多 Skill 组合 = Workflow Revision;
// renovation ★★★ 多角色长周期 = Agent Package。
// 场景 id 对应 data/demo_scenarios/{cooking,travel,renovation}.json 的 scenario_id。
defineEmits(["select"]);

const scenarios = [
  {
    id: "cooking",
    emoji: "🍳",
    title: "周末做红烧肉",
    focus: "单 Skill 完整闭环",
    stars: "★☆☆",
  },
  {
    id: "travel",
    emoji: "🧳",
    title: "家庭旅行规划",
    focus: "多 Skill 组合成 Workflow",
    stars: "★★☆",
  },
  {
    id: "renovation",
    emoji: "🔨",
    title: "装修一间厨房",
    focus: "多角色长周期 Agent Package",
    stars: "★★★",
  },
];
</script>

<style scoped>
.life-picker {
  max-width: 980px;
  margin: 0 auto;
  padding: clamp(28px, 6vh, 64px) 22px 48px;
}

.life-picker__head {
  text-align: center;
  margin-bottom: clamp(28px, 5vh, 48px);
}

.life-picker__mark {
  margin: 0 auto 16px;
}

.life-picker__greeting {
  margin: 0 0 6px;
  color: var(--ink-soft);
  font-size: 13px;
  letter-spacing: 0.3px;
}

.life-picker__title {
  margin: 0 0 14px;
  color: var(--ink);
  font-family: var(--serif);
  font-size: clamp(26px, 4vw, 36px);
  font-weight: 600;
  line-height: 1.2;
}

.life-picker__hint {
  margin: 0 auto;
  max-width: 60ch;
  color: var(--ink-soft);
  font-size: 14.5px;
  line-height: 1.75;
}

.life-picker__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-bottom: 28px;
}

.life-card {
  /* 纯按钮——重置原生 button 样式 */
  appearance: none;
  font: inherit;
  border: 1px solid var(--hairline);
  border-radius: var(--radius-lg, 14px);
  background: var(--surface-raised);
  color: var(--ink);
  padding: 22px 18px 18px;
  cursor: pointer;
  text-align: left;
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 8px;
  transition:
    transform var(--motion-fast) var(--ease-out-soft),
    box-shadow var(--motion-fast) var(--ease-out-soft),
    border-color var(--motion-fast) var(--ease-out-soft);
  box-shadow: var(--shadow-card);
}

.life-card:hover {
  transform: translateY(-2px);
  border-color: var(--clay-softer);
  box-shadow: var(--shadow-card-hover, var(--shadow-card));
}

.life-card:focus-visible {
  outline: 2px solid var(--clay);
  outline-offset: 2px;
}

.life-card:active {
  transform: translateY(0);
}

.life-card__emoji {
  font-size: 30px;
  line-height: 1;
}

.life-card__title {
  font-size: 16px;
  font-weight: 600;
  color: var(--ink);
}

.life-card__focus {
  font-size: 12.5px;
  color: var(--ink-soft);
  line-height: 1.4;
}

.life-card__stars {
  font-size: 11.5px;
  color: var(--clay);
  letter-spacing: 1px;
}

.life-card__cta {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--clay);
  border-top: 1px dashed var(--hairline);
  padding-top: 8px;
  width: 100%;
}

.life-picker__foot {
  text-align: center;
  color: var(--ink-faint);
  font-size: 12px;
  line-height: 1.7;
}

.life-picker__foot p {
  margin: 0;
}

.life-picker__link {
  color: var(--clay);
  text-decoration: none;
  border-bottom: 1px solid transparent;
  transition: border-color var(--motion-fast) var(--ease-out-soft);
}

.life-picker__link:hover {
  border-bottom-color: var(--clay);
}

/* 三场景色彩微区分(克制的左边缘色条,不抢主色) */
.life-card--cooking {
  border-left: 3px solid var(--trust-pending, #d6a100);
}
.life-card--travel {
  border-left: 3px solid var(--clay);
}
.life-card--renovation {
  border-left: 3px solid var(--ink-soft);
}

@media (prefers-reduced-motion: reduce) {
  .life-card {
    transition: none;
  }
  .life-card:hover {
    transform: none;
  }
}

@media (max-width: 760px) {
  .life-picker__grid {
    grid-template-columns: 1fr;
    gap: 10px;
  }
  .life-picker__title {
    font-size: 24px;
  }
  .life-picker__hint {
    font-size: 13.5px;
  }
}
</style>
