<template>
  <div class="ai-v2">
    <div class="controls">
      <input v-model="symbol" placeholder="EURUSDc" />
      <input v-model="timeframes" placeholder="M15,H1,H4,D1" />
      <button :disabled="loading" @click="run">{{ loading ? '运行中...' : '运行 AI 辩论' }}</button>
      <button @click="loadLatest">读取最新</button>
    </div>
    <pre v-if="error" class="error">{{ error }}</pre>
    <div v-if="report" class="grid">
      <div class="decision">
        <p class="eyebrow">AI 裁决</p>
        <h3>{{ report.decision?.action || 'HOLD' }} · {{ report.decision?.confidence ?? 0 }}</h3>
        <p>{{ report.decision?.reasoning }}</p>
      </div>
      <div class="debate bull"><h4>看多论点</h4><p>{{ report.bull_case?.thesis }}</p><ul><li v-for="point in report.bull_case?.evidence || []" :key="point.point">{{ point.source }} · {{ point.point }} · {{ point.weight }}</li></ul></div>
      <div class="debate bear"><h4>看空论点</h4><p>{{ report.bear_case?.thesis }}</p><ul><li v-for="point in report.bear_case?.evidence || []" :key="point.point">{{ point.source }} · {{ point.point }} · {{ point.weight }}</li></ul></div>
      <div class="memory"><h4>本地记忆</h4><p>{{ report.memory?.status?.case_count ?? 0 }} 条案例</p><ol><li v-for="item in report.memory?.similar_cases || []" :key="item.id">{{ item.symbol }} · 相似度 {{ item.similarity }}</li></ol></div>
    </div>
  </div>
</template>
<script setup>
import { ref } from 'vue'
import phase3Api from '../../../services/phase3Api.js'
const symbol = ref('EURUSDc')
const timeframes = ref('M15,H1,H4,D1')
const loading = ref(false)
const report = ref(null)
const error = ref('')
function capture(payload) { if (payload?.ok === false) error.value = payload.error || '请求失败'; else error.value = '' }
async function run() { loading.value = true; try { const payload = await phase3Api.runAiV2({ symbol: symbol.value, timeframes: timeframes.value.split(',').map(v => v.trim()) }); capture(payload); if (payload.ok) report.value = payload } finally { loading.value = false } }
async function loadLatest() { const payload = await phase3Api.aiV2Latest(); capture(payload); if (payload.ok) report.value = payload }
</script>
<style scoped>
.ai-v2 { display:grid; gap:12px; }
.controls { display:flex; gap:8px; flex-wrap:wrap; }
input { border:1px solid #3a4656; background:#15191f; color:#f3f3f3; border-radius:6px; padding:10px; }
button { border:1px solid #3a4656; border-radius:6px; background:#1b2027; color:#d7dde7; padding:10px 14px; cursor:pointer; }
.grid { display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:12px; }
.decision,.debate,.memory { border:1px solid #303846; border-radius:8px; padding:12px; background:#20242b; min-width:0; }
.decision { grid-column:1/-1; }
.eyebrow { color:#8fd0ff; letter-spacing:.08em; font-size:12px; margin:0; }
h3 { margin:6px 0; font-size:26px; color:#fff; }
h4 { color:#f3f3f3; margin:0 0 6px; }
ul,ol { color:#d7dde7; }
.error { color:#fecaca; background:rgba(127,29,29,.25); border-radius:10px; padding:10px; }
.bull { border-color:rgba(34,197,94,.35); } .bear { border-color:rgba(248,113,113,.35); }
@media(max-width:900px){.grid{grid-template-columns:1fr}}
</style>
