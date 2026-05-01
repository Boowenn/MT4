<template>
  <label class="qg-symbol-selector">
    <span>{{ label }}</span>
    <select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)">
      <option v-for="item in symbols" :key="item.symbol" :value="item.symbol">
        {{ item.label || item.symbol }}{{ item.assetClass ? ` · ${item.assetClass}` : '' }}
      </option>
    </select>
  </label>
</template>

<script setup>
defineProps({
  modelValue: { type: String, required: true },
  symbols: { type: Array, default: () => [] },
  label: { type: String, default: '交易对' },
});

defineEmits(['update:modelValue']);
</script>

<style scoped>
.qg-symbol-selector {
  min-width: 0;
  display: grid;
  gap: 6px;
  font-size: 13px;
  color: #9aa8bd;
}
.qg-symbol-selector select {
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  border: 1px solid rgba(148, 163, 184, 0.28);
  border-radius: 10px;
  padding: 9px 10px;
  background: rgba(15, 23, 42, 0.9);
  color: #e5eefc;
}
</style>
