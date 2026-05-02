<template>
  <div class="vibe-grid">
    <div class="left">
      <NlInput v-model:description="description" v-model:symbol="symbol" v-model:timeframe="timeframe" :loading="loading.generate" @generate="generate" />
      <StrategyHistory :strategies="strategies" @refresh="loadHistory" @select="selectStrategy" />
    </div>
    <div class="main">
      <div class="actions">
        <button :disabled="!currentStrategyId || loading.backtest" @click="backtest">{{ loading.backtest ? '回测中...' : '运行回测' }}</button>
        <button :disabled="!backtestResult || loading.analyze" @click="analyze">{{ loading.analyze ? '分析中...' : '分析回测' }}</button>
      </div>
      <StrategyEditor v-model:code="code" :validation="validation" />
      <IterateFeedback :strategy-id="currentStrategyId" :loading="loading.iterate" @iterate="iterate" />
      <BacktestResultCard :result="backtestResult" />
      <AiAnalysisCard :analysis="analysis" />
      <pre v-if="error" class="error">{{ error }}</pre>
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import phase3Api from '../../../services/phase3Api.js'
import NlInput from './NlInput.vue'
import StrategyEditor from './StrategyEditor.vue'
import StrategyHistory from './StrategyHistory.vue'
import IterateFeedback from './IterateFeedback.vue'
import BacktestResultCard from './BacktestResultCard.vue'
import AiAnalysisCard from './AiAnalysisCard.vue'

const description = ref('RSI 超卖后价格从布林下轨反弹时做多，并加入 H1 趋势过滤')
const symbol = ref('EURUSDc')
const timeframe = ref('H1')
const code = ref('')
const validation = ref(null)
const currentStrategyId = ref('')
const strategies = ref([])
const backtestResult = ref(null)
const analysis = ref(null)
const error = ref('')
const loading = reactive({ generate: false, iterate: false, backtest: false, analyze: false })

function capture(payload) { if (payload?.ok === false) error.value = payload.error || '请求失败'; else error.value = '' }
async function loadHistory() { const payload = await phase3Api.listStrategies(); capture(payload); strategies.value = payload.strategies || [] }
async function selectStrategy(id) { const payload = await phase3Api.getStrategy(id); capture(payload); if (payload.ok) { currentStrategyId.value = id; code.value = payload.code || ''; validation.value = payload.strategy?.validation || null } }
async function generate() { loading.generate = true; try { const payload = await phase3Api.generateStrategy({ description: description.value, symbol: symbol.value, timeframe: timeframe.value }); capture(payload); if (payload.ok) { currentStrategyId.value = payload.strategy.strategy_id; code.value = payload.code; validation.value = payload.validation; await loadHistory() } } finally { loading.generate = false } }
async function iterate(feedback) { loading.iterate = true; try { const payload = await phase3Api.iterateStrategy({ strategy_id: currentStrategyId.value, feedback, backtest_result: backtestResult.value }); capture(payload); if (payload.ok) { code.value = payload.code; validation.value = payload.validation; await loadHistory() } } finally { loading.iterate = false } }
async function backtest() { loading.backtest = true; try { const payload = await phase3Api.backtestStrategy({ strategy_id: currentStrategyId.value, symbol: symbol.value, timeframe: timeframe.value, days: 30 }); capture(payload); if (payload.ok) backtestResult.value = payload } finally { loading.backtest = false } }
async function analyze() { loading.analyze = true; try { const payload = await phase3Api.analyzeBacktest({ strategy_id: currentStrategyId.value, backtest_result: backtestResult.value }); capture(payload); if (payload.ok) analysis.value = payload } finally { loading.analyze = false } }
onMounted(loadHistory)
</script>

<style scoped>
.vibe-grid { display:grid; grid-template-columns: 340px minmax(0,1fr); gap:16px; min-width:0; }
.left,.main { display:grid; gap:12px; align-content:start; }
.actions { display:flex; gap:8px; flex-wrap:wrap; }
.actions button { border:1px solid #3a4656; border-radius:6px; background:#1b2027; color:#d7dde7; padding:10px 14px; cursor:pointer; }
.actions button:disabled { opacity:.5; cursor:not-allowed; }
.error { color:#fecaca; background:rgba(127,29,29,.25); border-radius:10px; padding:10px; white-space:pre-wrap; }
@media (max-width: 1100px) { .vibe-grid { grid-template-columns: 1fr; } }
</style>
