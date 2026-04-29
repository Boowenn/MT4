<script setup>
import { computed } from 'vue';

const props = defineProps({
  title: { type: String, required: true },
  subtitle: { type: String, default: '' },
  points: { type: Array, default: () => [] },
  labels: { type: Array, default: () => [] },
  tone: { type: String, default: 'blue' },
  unit: { type: String, default: '' },
  precision: { type: Number, default: 2 }
});

const width = 420;
const height = 128;
const padding = 16;

const values = computed(() => props.points.map((value) => Number(value)).filter((value) => Number.isFinite(value)));
const hasData = computed(() => values.value.length > 0);
const min = computed(() => (hasData.value ? Math.min(...values.value) : 0));
const max = computed(() => (hasData.value ? Math.max(...values.value) : 0));

function format(value) {
  if (!Number.isFinite(value)) return '--';
  return `${value.toFixed(props.precision)}${props.unit}`;
}

const coordinates = computed(() => {
  if (!hasData.value) return [];
  const span = max.value - min.value || 1;
  const usableWidth = width - padding * 2;
  const usableHeight = height - padding * 2;
  return values.value.map((value, index) => {
    const x = padding + (values.value.length === 1 ? usableWidth : (index / (values.value.length - 1)) * usableWidth);
    const y = padding + (1 - (value - min.value) / span) * usableHeight;
    return { x, y, value, label: props.labels[index] || '' };
  });
});

const polyline = computed(() => coordinates.value.map((point) => `${point.x},${point.y}`).join(' '));
const areaPath = computed(() => {
  if (coordinates.value.length < 2) return '';
  const start = coordinates.value[0];
  const end = coordinates.value[coordinates.value.length - 1];
  return `M ${start.x} ${height - padding} L ${polyline.value.replaceAll(',', ' ')} L ${end.x} ${height - padding} Z`;
});
</script>

<template>
  <article class="viz-card">
    <div class="viz-head">
      <div>
        <p class="eyebrow">{{ subtitle || '趋势' }}</p>
        <h3>{{ title }}</h3>
      </div>
      <div class="viz-stat">
        <strong>{{ format(values.at(-1)) }}</strong>
        <span>{{ format(min) }} / {{ format(max) }}</span>
      </div>
    </div>

    <div v-if="hasData" class="spark-shell">
      <svg :viewBox="`0 0 ${width} ${height}`" role="img" :aria-label="title">
        <path v-if="areaPath" :d="areaPath" class="spark-area" :class="tone" />
        <polyline :points="polyline" class="spark-line" :class="tone" />
        <circle
          v-for="point in coordinates"
          :key="`${point.x}-${point.y}`"
          :cx="point.x"
          :cy="point.y"
          r="2.8"
          class="spark-dot"
          :class="tone"
        />
      </svg>
    </div>
    <div v-else class="empty viz-empty">暂无可绘制样本。</div>
  </article>
</template>
