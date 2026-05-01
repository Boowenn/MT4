<template>
  <article class="decision-card" :class="`decision-card--${actionClass}`">
    <header class="decision-card__header">
      <span>综合决策</span>
      <strong>{{ action }}</strong>
    </header>
    <div class="decision-card__confidence">
      <span>置信度</span>
      <div class="decision-card__bar"><i :style="{ width: confidencePct + '%' }" /></div>
      <b>{{ confidencePct }}%</b>
    </div>
    <dl class="decision-card__grid">
      <div><dt>Entry</dt><dd>{{ formatPrice(decision.entry_price) }}</dd></div>
      <div><dt>SL</dt><dd>{{ formatPrice(decision.stop_loss) }}</dd></div>
      <div><dt>TP</dt><dd>{{ formatPrice(decision.take_profit) }}</dd></div>
      <div><dt>R/R</dt><dd>{{ decision.risk_reward_ratio ?? '-' }}</dd></div>
    </dl>
    <p class="decision-card__reasoning">{{ decision.reasoning || '等待 DecisionAgent 综合 Technical + Risk 输出。' }}</p>
    <ul v-if="Array.isArray(decision.key_factors) && decision.key_factors.length" class="decision-card__factors">
      <li v-for="factor in decision.key_factors" :key="factor">{{ factor }}</li>
    </ul>
  </article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  decision: { type: Object, default: () => ({}) },
});

const action = computed(() => props.decision.action || 'HOLD');
const actionClass = computed(() => String(action.value).toLowerCase());
const confidencePct = computed(() => Math.round(Math.max(0, Math.min(1, Number(props.decision.confidence || 0))) * 100));

function formatPrice(value) {
  return value === null || value === undefined || value === '' ? '-' : value;
}
</script>

<style scoped>
.decision-card {
  box-sizing: border-box;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 18px;
  background: linear-gradient(145deg, rgba(15, 23, 42, 0.95), rgba(30, 41, 59, 0.78));
  padding: 16px;
  color: #e5eefc;
}
.decision-card__header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 12px;
  font-size: 14px;
  color: #a8b5c7;
}
.decision-card__header strong {
  font-size: 28px;
  letter-spacing: 0.04em;
  color: #f8fafc;
}
.decision-card__confidence {
  display: grid;
  grid-template-columns: auto 1fr auto;
  align-items: center;
  gap: 10px;
  margin: 14px 0;
  font-size: 13px;
}
.decision-card__bar {
  height: 8px;
  overflow: hidden;
  border-radius: 999px;
  background: rgba(148, 163, 184, 0.18);
}
.decision-card__bar i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: currentColor;
}
.decision-card__grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}
.decision-card__grid div {
  min-width: 0;
  border-radius: 12px;
  background: rgba(15, 23, 42, 0.72);
  padding: 10px;
}
.decision-card__grid dt {
  color: #94a3b8;
  font-size: 12px;
}
.decision-card__grid dd {
  margin: 4px 0 0;
  font-weight: 700;
  overflow-wrap: anywhere;
}
.decision-card__reasoning {
  line-height: 1.6;
  color: #cbd5e1;
  overflow-wrap: anywhere;
}
.decision-card__factors {
  margin: 0;
  padding-left: 18px;
  color: #a8b5c7;
  line-height: 1.5;
}
.decision-card--buy { color: #86efac; }
.decision-card--sell { color: #fca5a5; }
.decision-card--hold { color: #fde68a; }

@media (max-width: 640px) {
  .decision-card__header {
    display: grid;
    align-items: start;
  }

  .decision-card__header strong {
    font-size: 22px;
  }

  .decision-card__confidence,
  .decision-card__grid {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
