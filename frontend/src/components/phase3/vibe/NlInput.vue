<template>
  <div class="nl-input">
    <label>自然语言策略想法</label>
    <textarea v-model="localDescription" rows="5" placeholder="例如：RSI 低位反弹且价格触及布林下轨时买入，并加入 H1 趋势过滤。" />
    <div class="row">
      <input v-model="localSymbol" placeholder="EURUSDc" />
      <select v-model="localTimeframe">
        <option>M15</option><option>H1</option><option>H4</option><option>D1</option>
      </select>
      <button :disabled="loading || !localDescription.trim()" @click="emitGenerate">{{ loading ? '生成中...' : '生成策略' }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
const props = defineProps({ description: { type: String, default: '' }, symbol: { type: String, default: 'EURUSDc' }, timeframe: { type: String, default: 'H1' }, loading: Boolean })
const emit = defineEmits(['update:description', 'update:symbol', 'update:timeframe', 'generate'])
const localDescription = ref(props.description)
const localSymbol = ref(props.symbol)
const localTimeframe = ref(props.timeframe)
watch(localDescription, v => emit('update:description', v))
watch(localSymbol, v => emit('update:symbol', v))
watch(localTimeframe, v => emit('update:timeframe', v))
function emitGenerate() { emit('generate') }
</script>

<style scoped>
.nl-input { display: grid; gap: 10px; }
label { font-weight: 700; color: #f3f3f3; }
textarea, input, select { width: 100%; min-width:0; border: 1px solid #3a4656; background: #15191f; color: #f3f3f3; border-radius: 6px; padding: 10px; }
.row { display: grid; grid-template-columns: 1fr 120px auto; gap: 8px; }
button { border: 1px solid #8fd0ff; border-radius: 6px; background: #8fd0ff; color: #07111d; padding: 10px 14px; cursor: pointer; }
button:disabled { opacity: .5; cursor: not-allowed; }
@media (max-width: 720px) { .row { grid-template-columns: 1fr; } }
</style>
