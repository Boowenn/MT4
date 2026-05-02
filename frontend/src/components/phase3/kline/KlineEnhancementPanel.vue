<template>
  <div class="kline-panel">
    <div class="controls">
      <input v-model="symbol" placeholder="EURUSDc" />
      <button @click="loadAll">加载叠加</button>
    </div>
    <AiSignalOverlayPanel :overlays="overlays" @refresh="loadOverlays" />
    <div class="card">
      <h4>策略工坊自定义指标</h4>
      <div v-if="!indicators.length" class="muted">暂无已注册指标。</div>
      <div v-for="item in indicators" :key="`${item.strategy_id}-${item.version}`" class="indicator">
        {{ item.name }} · {{ item.version }} · {{ item.indicatorKeys?.join(', ') }}
      </div>
    </div>
    <div class="card">
      <h4>实时轮询</h4>
      <p>传输：{{ realtime.transport || 'polling' }} · 间隔：{{ realtime.pollSeconds || 30 }}s · 增量更新：{{ realtime.incrementalUpdatePreferred }}</p>
    </div>
  </div>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import phase3Api from '../../../services/phase3Api.js'
import AiSignalOverlayPanel from './AiSignalOverlayPanel.vue'
const symbol = ref('EURUSDc')
const overlays = ref([])
const indicators = ref([])
const realtime = ref({})
async function loadOverlays() { const payload = await phase3Api.klineAiOverlays({ symbol: symbol.value, limit: 50 }); overlays.value = payload.overlays || [] }
async function loadAll() { await loadOverlays(); const ind = await phase3Api.klineVibeIndicators(); indicators.value = ind.strategies || []; realtime.value = await phase3Api.klineRealtimeConfig() }
onMounted(loadAll)
</script>
<style scoped>
.kline-panel { display:grid; gap:12px; }
.controls { display:flex; gap:8px; }
input { border:1px solid #3a4656; background:#15191f; color:#f3f3f3; border-radius:6px; padding:10px; }
button { border:1px solid #8fd0ff; border-radius:6px; background:#8fd0ff; color:#07111d; padding:10px 14px; cursor:pointer; }
.card { border:1px solid #303846; border-radius:8px; padding:12px; background:#20242b; }
h4 { margin:0 0 8px; color:#f3f3f3; } .muted { color:#a1a1aa; } .indicator { color:#d7dde7; padding:6px 0; border-bottom:1px solid rgba(148,163,184,.12); overflow-wrap:anywhere; }
</style>
