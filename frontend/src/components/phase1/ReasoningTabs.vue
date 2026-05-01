<template>
  <section class="reasoning-tabs">
    <div class="reasoning-tabs__buttons">
      <button v-for="tab in tabs" :key="tab.key" :class="{ active: active === tab.key }" @click="active = tab.key">
        {{ tab.label }}
      </button>
    </div>
    <pre class="reasoning-tabs__body">{{ currentText }}</pre>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue';

const props = defineProps({
  report: { type: Object, default: null },
});

const active = ref('technical');
const tabs = [
  { key: 'technical', label: '技术分析' },
  { key: 'risk', label: '风险评估' },
  { key: 'decision', label: '综合决策' },
  { key: 'snapshot', label: '快照' },
];

const currentText = computed(() => {
  const report = props.report || {};
  const value = report[active.value] || {};
  return JSON.stringify(value, null, 2);
});
</script>

<style scoped>
.reasoning-tabs {
  box-sizing: border-box;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.72);
}
.reasoning-tabs__buttons {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 10px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
}
.reasoning-tabs__buttons button {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 999px;
  padding: 7px 12px;
  background: rgba(15, 23, 42, 0.9);
  color: #cbd5e1;
  cursor: pointer;
}
.reasoning-tabs__buttons button.active {
  background: rgba(59, 130, 246, 0.22);
  color: #dbeafe;
}
.reasoning-tabs__body {
  max-height: 360px;
  margin: 0;
  padding: 14px;
  overflow: auto;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: #cbd5e1;
  font-size: 12px;
  line-height: 1.5;
}
</style>
