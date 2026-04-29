<script setup>
import { computed } from 'vue';

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  items: { type: Array, default: () => [] },
  valueLabel: { type: String, default: '' },
  maxItems: { type: Number, default: 8 }
});

const rows = computed(() => props.items
  .map((item) => ({
    ...item,
    value: Number(item.value)
  }))
  .filter((item) => item.label && Number.isFinite(item.value))
  .slice(0, props.maxItems));

const maxAbs = computed(() => Math.max(1, ...rows.value.map((item) => Math.abs(item.value))));

function widthFor(value) {
  return `${Math.max(4, Math.abs(value) / maxAbs.value * 100)}%`;
}

function display(value) {
  const abs = Math.abs(value);
  if (abs >= 1000) return value.toFixed(0);
  if (abs >= 10) return value.toFixed(1);
  return value.toFixed(2);
}
</script>

<template>
  <article class="viz-card">
    <div class="viz-head">
      <div>
        <p class="eyebrow">{{ subtitle || '分布' }}</p>
        <h3>{{ title }}</h3>
      </div>
      <span class="pill">{{ rows.length }} 项</span>
    </div>

    <div v-if="rows.length" class="bar-list">
      <div v-for="item in rows" :key="item.label" class="bar-row">
        <div class="bar-label">
          <strong>{{ item.label }}</strong>
          <small>{{ item.detail || valueLabel }}</small>
        </div>
        <div class="bar-track">
          <span
            class="bar-fill"
            :class="{ negative: item.value < 0, positive: item.value >= 0 }"
            :style="{ width: widthFor(item.value) }"
          />
        </div>
        <b>{{ display(item.value) }}</b>
      </div>
    </div>
    <div v-else class="empty viz-empty">暂无可聚合样本。</div>
  </article>
</template>
