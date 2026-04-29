<script setup>
import { compactJson, first } from '../utils/format';

defineProps({
  title: { type: String, required: true },
  payload: { type: [Object, Array, String, Number, Boolean], default: null },
  note: { type: String, default: '' }
});
</script>

<template>
  <details class="evidence-drawer">
    <summary>
      <span>{{ title }}</span>
      <small>{{ first(note, '展开 raw evidence') }}</small>
    </summary>
    <pre>{{ compactJson(payload, 2600) }}</pre>
  </details>
</template>
