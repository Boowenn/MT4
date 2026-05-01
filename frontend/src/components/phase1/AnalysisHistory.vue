<template>
  <section class="analysis-history">
    <header>
      <h3>历史分析</h3>
      <button @click="$emit('refresh')">刷新</button>
    </header>
    <button
      v-for="item in items"
      :key="item.id"
      class="analysis-history__item"
      @click="$emit('select', item.id)"
    >
      <span>{{ item.symbol }} · {{ item.action || '-' }}</span>
      <small>{{ item.generatedAtIso || item.id }}</small>
    </button>
    <p v-if="!items.length" class="analysis-history__empty">暂无历史记录</p>
  </section>
</template>

<script setup>
defineProps({
  items: { type: Array, default: () => [] },
});

defineEmits(['refresh', 'select']);
</script>

<style scoped>
.analysis-history {
  box-sizing: border-box;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  padding: 12px;
  background: rgba(15, 23, 42, 0.72);
}
.analysis-history header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}
.analysis-history h3 {
  margin: 0;
  color: #e5eefc;
}
.analysis-history button {
  cursor: pointer;
}
.analysis-history header button {
  border: 1px solid rgba(148, 163, 184, 0.22);
  border-radius: 10px;
  padding: 6px 10px;
  background: rgba(15, 23, 42, 0.85);
  color: #cbd5e1;
}
.analysis-history__item {
  box-sizing: border-box;
  display: grid;
  width: 100%;
  gap: 4px;
  margin-top: 10px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 12px;
  padding: 9px;
  background: rgba(30, 41, 59, 0.55);
  color: #e5eefc;
  text-align: left;
  overflow-wrap: anywhere;
}
.analysis-history__item small,
.analysis-history__empty {
  color: #94a3b8;
}
</style>
