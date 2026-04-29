<script setup>
import { first, shortText } from '../utils/format';

defineProps({
  title: { type: String, default: '' },
  rows: { type: Array, default: () => [] },
  columns: { type: Array, default: () => [] },
  empty: { type: String, default: '暂无证据。' }
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
</script>

<template>
  <article class="panel data-table-card">
    <div v-if="title" class="panel-title split">
      <span>{{ title }}</span>
      <small>{{ rows.length }} 条</small>
    </div>
    <div class="table-panel embedded">
      <table>
        <thead>
          <tr>
            <th v-for="column in columns" :key="column.label" :style="{ width: column.width || 'auto' }">
              {{ column.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, index) in rows" :key="first(row?.id, row?.candidateId, row?.marketId, row?.ticket, row?.versionId, index)">
            <td v-for="column in columns" :key="column.label" :title="String(first(cellValue(row, column), '--'))">
              <span v-if="column.badge" class="pill">{{ first(cellValue(row, column), '--') }}</span>
              <span v-else>{{ shortText(first(cellValue(row, column), '--'), column.max || 72) }}</span>
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
