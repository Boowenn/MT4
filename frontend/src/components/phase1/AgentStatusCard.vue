<template>
  <article class="agent-card">
    <div class="agent-card__header">
      <span class="agent-card__name">{{ title }}</span>
      <span class="agent-card__badge" :class="badgeClass">{{ statusLabel }}</span>
    </div>
    <p class="agent-card__primary">{{ primary }}</p>
    <p class="agent-card__secondary">{{ secondary }}</p>
  </article>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  title: { type: String, required: true },
  report: { type: Object, default: null },
  status: { type: String, default: 'idle' },
});

const statusLabel = computed(() => {
  if (props.status === 'running') return '运行中';
  if (props.status === 'error') return '异常';
  if (props.report) return '完成';
  return '待机';
});

const badgeClass = computed(() => `agent-card__badge--${props.status || (props.report ? 'done' : 'idle')}`);

const primary = computed(() => {
  const report = props.report || {};
  if (report.direction) return `方向：${report.direction}`;
  if (report.risk_level) return `风险：${report.risk_level} (${report.risk_score ?? '-'})`;
  if (report.action) return `决策：${report.action} · 置信度 ${Math.round((report.confidence || 0) * 100)}%`;
  return props.status === 'running' ? '正在分析行情与风控状态…' : '等待分析结果';
});

const secondary = computed(() => {
  const report = props.report || {};
  return report.reasoning || report.summary || 'AI 输出只作为 Governance evidence，不会直接触发交易。';
});
</script>

<style scoped>
.agent-card {
  box-sizing: border-box;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.72);
  padding: 14px;
}
.agent-card__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}
.agent-card__name {
  min-width: 0;
  overflow-wrap: anywhere;
  font-weight: 700;
  color: #e5eefc;
}
.agent-card__badge {
  flex: 0 0 auto;
  border-radius: 999px;
  padding: 3px 9px;
  font-size: 12px;
  background: rgba(148, 163, 184, 0.16);
  color: #cbd5e1;
}
.agent-card__badge--running { background: rgba(234, 179, 8, 0.18); color: #fde68a; }
.agent-card__badge--done { background: rgba(34, 197, 94, 0.14); color: #bbf7d0; }
.agent-card__badge--error { background: rgba(239, 68, 68, 0.16); color: #fecaca; }
.agent-card__primary {
  margin: 12px 0 6px;
  color: #f8fafc;
  font-size: 15px;
}
.agent-card__secondary {
  margin: 0;
  color: #94a3b8;
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}
</style>
