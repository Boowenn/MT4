<script setup>
import { first } from '../utils/format';

defineProps({
  title: { type: String, default: '' },
  rows: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  empty: { type: String, default: '暂无证据。' },
  dense: { type: Boolean, default: false }
});

function cellValue(row, column) {
  if (typeof column.value === 'function') {
    return column.value(row);
  }
  if (Array.isArray(column.key)) {
    return first(...column.key.map((key) => row?.[key]));
  }
  return row?.[column.key];
}

function humanizeToken(value) {
  const raw = String(first(value, '--')).trim();
  if (!raw || raw === '--') return '--';
  const key = raw.toUpperCase().replace(/[\s/.-]+/g, '_');
  const exact = {
    PENDING_REPORT: '等报告',
    WAIT_REPORT: '等报告',
    WAITING_REPORT: '等报告',
    RUN_PENDING_REPORT_FIRST: '先等报告',
    CONFIG_ONLY: '仅配置',
    CONFIG_READY: '可运行',
    FILE_ONLY_REPORT_WATCHER: '报告文件',
    FILE_ONLY_RUN_HISTORY: '运行历史',
    EVALUATE_ONLY: '只评估',
    EXISTING_PARAMLAB_TASKS: '已有任务',
    EXISTING_PARAMLAB_TASK: '已有任务',
    EXISTING_PARAMLAB: '已有任务',
    MT5_RESEARCH_STATS: 'MT5研究',
    POLYMARKET_AI_SCORE: 'AI评分',
    POLYMARKET_MARKET_RADAR: '市场雷达',
    POLYMARKET_SINGLE_MARKET: '单市场',
    POLYMARKET_HISTORY_API: '历史API',
    OK: '正常',
    READY: '可运行',
    PARSED: '已解析',
    SCORED: '已评分',
    RED: '红灯',
    YELLOW: '黄灯',
    GREEN: '绿灯'
  };
  if (exact[key]) return exact[key];
  if (/existing\s+paramlab/i.test(raw)) return '已有任务';
  if (key.includes('PENDING_REPORT') || key.includes('WAIT_REPORT')) return '等报告';
  if (key.includes('PARAMLAB')) return '参数任务';
  if (key.includes('REPORT_WATCH')) return '报告文件';
  if (key.includes('RUN_HIST')) return '运行历史';
  if (key.includes('REPORT')) return '等报告';
  return raw;
}

function displayValue(row, column) {
  const value = first(cellValue(row, column), '--');
  if (typeof column.format === 'function') {
    return column.format(value, row);
  }
  if (column.badge) {
    return humanizeToken(value);
  }
  return value;
}

function cellClass(row, column) {
  const dynamic = typeof column.tone === 'function' ? column.tone(row) : '';
  return [column.class || '', dynamic].filter(Boolean).join(' ');
}
</script>

<template>
  <article class="panel data-table-card" :class="{ 'is-dense': dense }">
    <div v-if="title" class="panel-title split">
      <span>{{ title }}</span>
      <small>{{ rows.length }} 条</small>
    </div>
    <div class="table-panel embedded">
      <table class="data-table">
        <colgroup>
          <col v-for="column in columns" :key="column.label" :style="{ width: column.width || 'auto' }" />
        </colgroup>
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.label" :class="column.class || ''">
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="first(row?.id, row?.candidateId, row?.marketId, row?.ticket, row?.versionId, index)">
            <td v-for="column in columns" :key="column.label" :class="cellClass(row, column)" :title="String(first(cellValue(row, column), '--'))">
              <span v-if="column.badge && displayValue(row, column) !== '--'" class="pill" :title="String(first(cellValue(row, column), '--'))">
                {{ displayValue(row, column) }}
              </span>
              <span v-else class="cell-text">{{ displayValue(row, column) }}</span>
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="columns.length || 1">{{ empty }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </article>
</template>
