<template>
  <header class="kline-toolbar">
    <SymbolSelector v-model="innerSymbol" :symbols="symbols" label="品种" />
    <label>
      周期
      <select v-model="innerTf">
        <option v-for="tf in timeframes" :key="tf" :value="tf">{{ tf }}</option>
      </select>
    </label>
    <label>
      Bars
      <input v-model.number="innerBars" type="number" min="50" max="2000" />
    </label>
    <div class="kline-toolbar__toggles">
      <label v-for="item in indicatorOptions" :key="item.key">
        <input v-model="innerIndicators" type="checkbox" :value="item.key" />
        {{ item.label }}
      </label>
    </div>
    <button @click="$emit('refresh')">刷新图表</button>
  </header>
</template>

<script setup>
import { watch, ref } from 'vue';
import SymbolSelector from '../SymbolSelector.vue';

const props = defineProps({
  symbol: { type: String, required: true },
  tf: { type: String, default: 'H1' },
  bars: { type: Number, default: 200 },
  indicators: { type: Array, default: () => ['EMA', 'RSI', 'MACD', 'BOLL', 'VOL'] },
  symbols: { type: Array, default: () => [] },
});

const emit = defineEmits(['update:symbol', 'update:tf', 'update:bars', 'update:indicators', 'refresh']);

const timeframes = ['M15', 'H1', 'H4', 'D1'];
const indicatorOptions = [
  { key: 'EMA', label: 'EMA 9/21' },
  { key: 'RSI', label: 'RSI' },
  { key: 'MACD', label: 'MACD' },
  { key: 'BOLL', label: 'Bollinger' },
  { key: 'VOL', label: 'Volume' },
];

const innerSymbol = ref(props.symbol);
const innerTf = ref(props.tf);
const innerBars = ref(props.bars);
const innerIndicators = ref([...props.indicators]);

watch(() => props.symbol, (value) => { innerSymbol.value = value; });
watch(() => props.tf, (value) => { innerTf.value = value; });
watch(() => props.bars, (value) => { innerBars.value = value; });
watch(() => props.indicators, (value) => { innerIndicators.value = [...value]; });
watch(innerSymbol, (value) => emit('update:symbol', value));
watch(innerTf, (value) => emit('update:tf', value));
watch(innerBars, (value) => emit('update:bars', Number(value) || 200));
watch(innerIndicators, (value) => emit('update:indicators', value));
</script>

<style scoped>
.kline-toolbar {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 12px;
  min-width: 0;
}
.kline-toolbar label {
  display: grid;
  gap: 6px;
  min-width: 0;
  color: #94a3b8;
  font-size: 13px;
}
.kline-toolbar select,
.kline-toolbar input {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 10px;
  padding: 9px 10px;
  background: rgba(15, 23, 42, 0.9);
  color: #e5eefc;
}
.kline-toolbar__toggles {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  max-width: 460px;
  min-width: 0;
}
.kline-toolbar__toggles label {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}
.kline-toolbar button {
  min-width: 0;
  border: 0;
  border-radius: 12px;
  padding: 10px 14px;
  background: #2563eb;
  color: white;
  cursor: pointer;
  font-weight: 700;
}

@media (max-width: 640px) {
  .kline-toolbar > *,
  .kline-toolbar button {
    flex: 1 1 100%;
  }
}
</style>
