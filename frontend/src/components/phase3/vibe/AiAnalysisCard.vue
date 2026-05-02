<template>
  <div class="card">
    <div class="head"><strong>AI 回测分析</strong><span>{{ analysis?.readiness || '未分析' }}</span></div>
    <p v-if="analysis?.summary">{{ analysis.summary }}</p>
    <div class="cols" v-if="analysis">
      <div><h4>优点</h4><ul><li v-for="item in analysis.strengths" :key="item">{{ item }}</li></ul></div>
      <div><h4>弱点</h4><ul><li v-for="item in analysis.weaknesses" :key="item">{{ item }}</li></ul></div>
      <div><h4>建议</h4><ul><li v-for="item in analysis.recommendations" :key="item">{{ item }}</li></ul></div>
    </div>
    <p v-else class="muted">先运行回测，再点击分析回测。</p>
  </div>
</template>
<script setup>
defineProps({ analysis: { type: Object, default: null } })
</script>
<style scoped>
.card { border:1px solid #303846; border-radius:8px; padding:12px; background:#20242b; }
.head { display:flex; justify-content:space-between; gap:8px; color:#f3f3f3; }
.head span,.muted { color:#a1a1aa; }
.cols { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:10px; }
h4 { margin:10px 0 4px; color:#8fd0ff; } ul { margin:0; padding-left:18px; color:#d7dde7; }
@media (max-width: 900px) { .cols { grid-template-columns:1fr; } }
</style>
