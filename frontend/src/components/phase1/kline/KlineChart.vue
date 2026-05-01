<template>
  <div class="kline-chart">
    <div ref="chartEl" class="kline-chart__canvas" />
    <p v-if="!bars.length" class="kline-chart__empty">暂无 K 线数据</p>
  </div>
</template>

<script setup>
import { init, dispose } from 'klinecharts';
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const props = defineProps({
  bars: { type: Array, default: () => [] },
  indicators: { type: Array, default: () => ['EMA', 'RSI', 'MACD', 'BOLL', 'VOL'] },
  trades: { type: Array, default: () => [] },
  shadowSignals: { type: Array, default: () => [] },
});

const chartEl = ref(null);
let chart = null;

onMounted(async () => {
  await nextTick();
  createChart();
  renderAll();
});

onBeforeUnmount(() => {
  if (chart) {
    try { dispose(chart); } catch (error) { /* noop */ }
    chart = null;
  }
});

watch(() => [props.bars, props.indicators, props.trades, props.shadowSignals], renderAll, { deep: true });

function createChart() {
  if (chart || !chartEl.value) return;
  chart = init(chartEl.value);
}

function renderAll() {
  if (!chart) return;
  const data = props.bars.map(normalizeBar).filter((bar) => bar.timestamp && Number.isFinite(bar.close));
  chart.applyNewData(data);
  applyIndicators();
  applySignalOverlays();
}

function normalizeBar(row) {
  return {
    timestamp: Number(row.timestamp || Date.parse(row.timeIso || row.time || 0)),
    open: Number(row.open),
    high: Number(row.high),
    low: Number(row.low),
    close: Number(row.close),
    volume: Number(row.volume || row.tick_volume || 0),
  };
}

function applyIndicators() {
  if (!chart) return;
  try {
    if (typeof chart.removeIndicator === 'function') {
      ['EMA_FAST', 'EMA_SLOW', 'RSI_PANE', 'MACD_PANE', 'BOLL_MAIN', 'VOL_PANE'].forEach((id) => {
        try { chart.removeIndicator(id); } catch (error) { /* noop */ }
      });
    }
    const selected = new Set(props.indicators || []);
    if (selected.has('EMA')) {
      chart.createIndicator({ name: 'EMA', id: 'EMA_FAST', calcParams: [9] }, false, { id: 'candle_pane' });
      chart.createIndicator({ name: 'EMA', id: 'EMA_SLOW', calcParams: [21] }, false, { id: 'candle_pane' });
    }
    if (selected.has('BOLL')) chart.createIndicator({ name: 'BOLL', id: 'BOLL_MAIN', calcParams: [20, 2] }, false, { id: 'candle_pane' });
    if (selected.has('VOL')) chart.createIndicator({ name: 'VOL', id: 'VOL_PANE' }, false, { id: 'vol_pane', height: 80 });
    if (selected.has('RSI')) chart.createIndicator({ name: 'RSI', id: 'RSI_PANE', calcParams: [14] }, false, { id: 'rsi_pane', height: 90 });
    if (selected.has('MACD')) chart.createIndicator({ name: 'MACD', id: 'MACD_PANE', calcParams: [12, 26, 9] }, false, { id: 'macd_pane', height: 90 });
  } catch (error) {
    console.warn('[QuantGod Phase1] indicator render skipped:', error);
  }
}

function applySignalOverlays() {
  if (!chart || typeof chart.createOverlay !== 'function') return;
  try {
    if (typeof chart.removeOverlay === 'function') {
      chart.removeOverlay({ groupId: 'qg_phase1_signals' });
    }
    const overlays = [];
    props.trades.forEach((item, index) => {
      const point = overlayPoint(item);
      if (!point) return;
      overlays.push({
        name: 'simpleAnnotation',
        id: `qg_trade_${index}`,
        groupId: 'qg_phase1_signals',
        lock: true,
        points: [point],
        extendData: { text: `${item.side || item.event || 'TRADE'} ${item.route || ''}`.trim() },
      });
    });
    props.shadowSignals.forEach((item, index) => {
      const point = overlayPoint(item);
      if (!point) return;
      overlays.push({
        name: 'simpleTag',
        id: `qg_shadow_${index}`,
        groupId: 'qg_phase1_signals',
        lock: true,
        points: [point],
        extendData: { text: `${item.side || item.signal || 'SHADOW'} ${item.route || ''}`.trim() },
      });
    });
    if (overlays.length) chart.createOverlay(overlays);
  } catch (error) {
    console.warn('[QuantGod Phase1] overlay render skipped:', error);
  }
}

function overlayPoint(item) {
  const timestamp = Number(item.timestamp || Date.parse(item.timeIso || item.time || 0));
  const value = Number(item.price || item.close || item.entry_price);
  if (!timestamp || !Number.isFinite(value)) return null;
  return { timestamp, value };
}
</script>

<style scoped>
.kline-chart {
  position: relative;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  min-height: 520px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 18px;
  overflow: hidden;
  background: rgba(15, 23, 42, 0.8);
}
.kline-chart__canvas {
  width: 100%;
  height: 620px;
}
.kline-chart__empty {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  margin: 0;
  color: #94a3b8;
  pointer-events: none;
}

@media (max-width: 640px) {
  .kline-chart {
    min-height: 380px;
  }

  .kline-chart__canvas {
    height: 420px;
  }
}
</style>
