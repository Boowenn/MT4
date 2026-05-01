<template>
  <main class="phase1-workspace">
    <AiAnalysisWorkspace />
    <KlineWorkspace />
  </main>
</template>

<script setup>
import AiAnalysisWorkspace from './AiAnalysisWorkspace.vue';
import KlineWorkspace from './kline/KlineWorkspace.vue';
</script>

<style scoped>
.phase1-workspace {
  box-sizing: border-box;
  display: grid;
  gap: 22px;
  width: 100%;
  min-width: 0;
  padding: clamp(10px, 2vw, 22px);
  background: #020617;
}

.phase1-workspace > * {
  min-width: 0;
}
</style>
