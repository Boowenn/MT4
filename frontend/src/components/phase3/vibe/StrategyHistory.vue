<template>
  <div class="card">
    <div class="head"><strong>策略历史</strong><button @click="$emit('refresh')">刷新</button></div>
    <div v-if="!strategies.length" class="muted">还没有生成策略。</div>
    <button v-for="item in strategies" :key="item.strategy_id" class="strategy" @click="$emit('select', item.strategy_id)">
      <span>{{ item.latest?.name || item.strategy_id }}</span>
      <small>{{ item.versions?.length || 0 }} 版本</small>
    </button>
  </div>
</template>
<script setup>
defineProps({ strategies: { type: Array, default: () => [] } })
defineEmits(['select', 'refresh'])
</script>
<style scoped>
.card { border:1px solid #303846; border-radius:8px; padding:12px; background:#20242b; }
.head { display:flex; justify-content:space-between; gap:8px; margin-bottom:8px; color:#f3f3f3; }
.head button,.strategy { border:1px solid #3a4656; border-radius:6px; background:#15191f; color:#d7dde7; padding:8px; cursor:pointer; }
.strategy { width:100%; display:flex; justify-content:space-between; margin:6px 0; }
small,.muted { color:#a1a1aa; }
</style>
