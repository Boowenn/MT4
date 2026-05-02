<template>
  <div class="card">
    <div class="head"><strong>AI 信号叠加</strong><button @click="$emit('refresh')">刷新</button></div>
    <div v-if="!overlays.length" class="muted">暂无 AI overlay。</div>
    <div v-for="item in overlays" :key="item.id" class="row">
      <b :class="item.action?.toLowerCase()">{{ item.action }}</b>
      <span>{{ item.symbol }}</span>
      <span>{{ item.confidence }}</span>
      <small>{{ item.reasoning }}</small>
    </div>
  </div>
</template>
<script setup>
defineProps({ overlays: { type: Array, default: () => [] } })
defineEmits(['refresh'])
</script>
<style scoped>
.card { border:1px solid #303846; border-radius:8px; padding:12px; background:#20242b; }
.head { display:flex; justify-content:space-between; gap:8px; margin-bottom:8px; color:#f3f3f3; }
.head button { border:1px solid #3a4656; border-radius:6px; background:#15191f; color:#d7dde7; padding:8px; cursor:pointer; }
.row { display:grid; grid-template-columns:70px 90px 70px minmax(0,1fr); gap:8px; padding:7px 0; border-bottom:1px solid rgba(148,163,184,.15); min-width:0; overflow-wrap:anywhere; }
.buy { color:#86efac; } .sell { color:#fca5a5; } .hold { color:#cbd5e1; }
small,.muted { color:#a1a1aa; }
@media(max-width:720px){.row{grid-template-columns:1fr 1fr}}
</style>
