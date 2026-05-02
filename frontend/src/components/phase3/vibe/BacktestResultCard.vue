<template>
  <div class="card">
    <div class="head">
      <strong>回测结果</strong>
      <span v-if="result?.generatedAt">{{ result.generatedAt }}</span>
    </div>
    <div v-if="!result" class="empty">还没有回测结果。</div>
    <template v-else>
      <div class="metrics">
        <div><b>{{ metrics.trades ?? 0 }}</b><span>交易数</span></div>
        <div><b>{{ metrics.win_rate ?? 0 }}</b><span>胜率</span></div>
        <div><b>{{ metrics.profit_factor ?? 0 }}</b><span>PF</span></div>
        <div><b>{{ metrics.net_pips ?? 0 }}</b><span>净 pips</span></div>
      </div>
      <details>
        <summary>近期交易</summary>
        <table>
          <thead><tr><th>时间</th><th>方向</th><th>Pips</th><th>置信度</th></tr></thead>
          <tbody>
            <tr v-for="trade in trades" :key="`${trade.time}-${trade.index}`">
              <td>{{ trade.time }}</td><td>{{ trade.action }}</td><td>{{ trade.pnl_pips }}</td><td>{{ trade.confidence }}</td>
            </tr>
          </tbody>
        </table>
      </details>
    </template>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({ result: { type: Object, default: null } })
const metrics = computed(() => props.result?.metrics || {})
const trades = computed(() => (props.result?.trades || []).slice(-20).reverse())
</script>
<style scoped>
.card { border: 1px solid #303846; border-radius: 8px; padding: 12px; background: #20242b; }
.head { display:flex; justify-content:space-between; gap:8px; color:#f3f3f3; margin-bottom:10px; }
.head span, .empty { color:#a1a1aa; }
.metrics { display:grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap:8px; }
.metrics div { background:#15191f; border-radius:6px; padding:10px; display:grid; gap:4px; min-width:0; }
b { font-size:20px; color:#fff; } span { color:#94a3b8; }
table { width:100%; border-collapse: collapse; margin-top:8px; font-size:12px; }
th,td { border-bottom:1px solid rgba(148,163,184,.18); padding:6px; text-align:left; }
summary { margin-top:10px; cursor:pointer; color:#8fd0ff; }
@media (max-width: 720px) { .metrics { grid-template-columns: repeat(2,minmax(0,1fr)); } }
</style>
