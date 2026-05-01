<template>
  <aside class="signal-overlay">
    <label><input v-model="innerTrades" type="checkbox" /> 实盘交易点</label>
    <label><input v-model="innerShadow" type="checkbox" /> Shadow 信号</label>
    <p>交易点与影子信号只读叠加，不向 MT5 写入任何状态。</p>
  </aside>
</template>

<script setup>
import { ref, watch } from 'vue';

const props = defineProps({
  trades: { type: Boolean, default: true },
  shadow: { type: Boolean, default: true },
});
const emit = defineEmits(['update:trades', 'update:shadow']);

const innerTrades = ref(props.trades);
const innerShadow = ref(props.shadow);
watch(() => props.trades, (value) => { innerTrades.value = value; });
watch(() => props.shadow, (value) => { innerShadow.value = value; });
watch(innerTrades, (value) => emit('update:trades', value));
watch(innerShadow, (value) => emit('update:shadow', value));
</script>

<style scoped>
.signal-overlay {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 12px;
  color: #cbd5e1;
  font-size: 13px;
}
.signal-overlay label {
  display: inline-flex;
  gap: 6px;
  align-items: center;
}
.signal-overlay p {
  flex-basis: 100%;
  margin: 0;
  color: #94a3b8;
}
</style>
