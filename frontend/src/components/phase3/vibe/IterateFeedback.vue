<template>
  <div class="iterate">
    <textarea v-model="feedback" rows="3" placeholder="例如：加入 H4 趋势过滤，把止损收紧到 10 pips。" />
    <button :disabled="!strategyId || loading || !feedback.trim()" @click="submit">{{ loading ? '迭代中...' : '迭代策略' }}</button>
  </div>
</template>
<script setup>
import { ref } from 'vue'
const props = defineProps({ strategyId: { type: String, default: '' }, loading: Boolean })
const emit = defineEmits(['iterate'])
const feedback = ref('')
function submit() { emit('iterate', feedback.value); feedback.value = '' }
</script>
<style scoped>
.iterate { display:grid; gap:8px; }
textarea { border:1px solid #3a4656; background:#15191f; color:#f3f3f3; border-radius:6px; padding:10px; }
button { border:1px solid #3a4656; border-radius:6px; background:#1b2027; color:#d7dde7; padding:10px 14px; cursor:pointer; }
button:disabled { opacity:.5; cursor:not-allowed; }
</style>
