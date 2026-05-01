<template>
  <section class="kline-workspace">
    <header class="kline-workspace__header">
      <div>
        <h2>专业 K 线图表</h2>
        <p>KlineCharts + MT5 read-only K 线 + 交易/Shadow 信号叠加。</p>
      </div>
      <SignalOverlay v-model:trades="showTrades" v-model:shadow="showShadow" />
    </header>

    <KlineToolbar
      v-model:symbol="symbol"
      v-model:tf="tf"
      v-model:bars="barsCount"
      v-model:indicators="indicators"
      :symbols="symbols"
      @refresh="loadChart"
    />

    <p v-if="error" class="kline-workspace__error">{{ error }}</p>
    <KlineChart
      :bars="bars"
      :indicators="indicators"
      :trades="showTrades ? trades : []"
      :shadow-signals="showShadow ? shadowSignals : []"
    />
  </section>
</template>

<script setup>
import { onMounted, ref, watch } from 'vue';
import { getChartTrades, getKline, getShadowSignals, getSymbolRegistry } from '../../../services/phase1Api';
import KlineChart from './KlineChart.vue';
import KlineToolbar from './KlineToolbar.vue';
import SignalOverlay from './SignalOverlay.vue';

const symbols = ref([]);
const symbol = ref('EURUSDc');
const tf = ref('H1');
const barsCount = ref(200);
const indicators = ref(['EMA', 'RSI', 'MACD', 'BOLL', 'VOL']);
const showTrades = ref(true);
const showShadow = ref(true);
const bars = ref([]);
const trades = ref([]);
const shadowSignals = ref([]);
const error = ref('');

async function bootstrap() {
  symbols.value = await getSymbolRegistry();
  if (!symbols.value.find((item) => item.symbol === symbol.value) && symbols.value[0]) {
    symbol.value = symbols.value[0].symbol;
  }
  await loadChart();
}

async function loadChart() {
  error.value = '';
  try {
    const [klinePayload, tradesPayload, shadowPayload] = await Promise.all([
      getKline({ symbol: symbol.value, tf: tf.value, bars: barsCount.value }),
      getChartTrades({ symbol: symbol.value, days: 30 }),
      getShadowSignals({ symbol: symbol.value, days: 7 }),
    ]);
    bars.value = klinePayload.bars || [];
    trades.value = tradesPayload.items || [];
    shadowSignals.value = shadowPayload.items || [];
  } catch (loadError) {
    error.value = loadError.message || String(loadError);
  }
}

watch([symbol, tf], loadChart);
onMounted(bootstrap);
</script>

<style scoped>
.kline-workspace {
  box-sizing: border-box;
  display: grid;
  gap: 16px;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 22px;
  padding: 18px;
  background: rgba(2, 6, 23, 0.72);
}
.kline-workspace__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 0.8fr);
  gap: 14px;
  align-items: end;
  min-width: 0;
}
.kline-workspace h2 {
  margin: 0 0 6px;
  color: #f8fafc;
}
.kline-workspace p {
  margin: 0;
  color: #94a3b8;
}
.kline-workspace__error {
  border: 1px solid rgba(239, 68, 68, 0.28);
  border-radius: 12px;
  padding: 10px 12px;
  color: #fecaca !important;
  background: rgba(127, 29, 29, 0.22);
}
@media (max-width: 1000px) {
  .kline-workspace__header {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .kline-workspace {
    padding: 12px;
    border-radius: 16px;
  }

  .kline-workspace h2 {
    font-size: 20px;
    line-height: 1.2;
  }
}
</style>
