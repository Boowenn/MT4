<template>
  <section class="phase3-workspace">
    <div class="phase3-header">
      <div>
        <p class="eyebrow">策略研究 / 只读闭环</p>
        <h2>策略工坊</h2>
        <p class="muted">自然语言生成策略、research-only 回测、AI 多智能体辩论与 K 线叠加。任何策略进入实盘前都必须经过回测、ParamLab、Governance、Version Gate 和人工授权。</p>
      </div>
      <div class="safety-pill">只做研究 · 不改实盘</div>
    </div>
    <div class="phase3-tabs">
      <button :class="{ active: tab === 'vibe' }" @click="tab = 'vibe'">策略生成</button>
      <button :class="{ active: tab === 'ai' }" @click="tab = 'ai'">AI 辩论</button>
      <button :class="{ active: tab === 'kline' }" @click="tab = 'kline'">K 线叠加</button>
    </div>
    <VibeCodingWorkspace v-if="tab === 'vibe'" />
    <AiV2DebateWorkspace v-else-if="tab === 'ai'" />
    <KlineEnhancementPanel v-else />
  </section>
</template>

<script setup>
import { ref } from 'vue'
import VibeCodingWorkspace from './vibe/VibeCodingWorkspace.vue'
import AiV2DebateWorkspace from './ai/AiV2DebateWorkspace.vue'
import KlineEnhancementPanel from './kline/KlineEnhancementPanel.vue'

const tab = ref('vibe')
</script>

<style scoped>
.phase3-workspace {
  display: grid;
  gap: 16px;
  width: 100%;
  min-width: 0;
  margin: 0;
  padding: 18px;
  color: #f3f3f3;
  background: #1b1b1b;
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 8px;
}
.phase3-header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  min-width: 0;
}
.eyebrow {
  margin: 0 0 6px;
  color: #8fd0ff;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: .08em;
}
h2 {
  margin: 0 0 8px;
  font-size: 28px;
  line-height: 1.15;
}
.muted {
  max-width: 820px;
  margin: 0;
  color: #a1a1aa;
  line-height: 1.5;
}
.safety-pill {
  flex: 0 0 auto;
  max-width: 100%;
  border: 1px solid rgba(143, 208, 255, .35);
  color: #8fd0ff;
  border-radius: 6px;
  padding: 8px 12px;
  background: rgba(143, 208, 255, .12);
}
.phase3-tabs {
  display: flex;
  gap: 8px;
  margin: 0;
  flex-wrap: wrap;
}
.phase3-tabs button {
  border: 1px solid #3a4656;
  border-radius: 6px;
  background: #1b2027;
  color: #d7dde7;
  padding: 9px 12px;
  cursor: pointer;
}
.phase3-tabs button.active {
  background: #8fd0ff;
  color: #07111d;
  border-color: #8fd0ff;
}
@media (max-width: 760px) {
  .phase3-header {
    display: grid;
  }
  h2 {
    font-size: 24px;
  }
}
</style>
