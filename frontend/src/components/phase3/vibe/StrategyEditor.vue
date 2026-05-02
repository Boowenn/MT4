<template>
  <div class="editor-card">
    <div class="editor-head">
      <strong>策略代码</strong>
      <span>{{ monacoReady ? 'Monaco Editor' : '文本编辑器' }}</span>
    </div>
    <div ref="editorHost" class="monaco-host" />
    <textarea v-if="!monacoReady" :value="code" spellcheck="false" rows="24" @input="$emit('update:code', $event.target.value)" />
    <div v-if="validation" class="validation" :class="{ ok: validation.ok, bad: !validation.ok }">
      安全校验：{{ validation.ok ? '通过' : '失败' }}
      <span v-if="validation.issues?.length"> · {{ validation.issues.length }} 个问题</span>
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
const props = defineProps({ code: { type: String, default: '' }, validation: { type: Object, default: null } })
const emit = defineEmits(['update:code'])
const editorHost = ref(null)
const monacoReady = ref(false)
let editor = null
let suppress = false

onMounted(async () => {
  await nextTick()
  try {
    const monaco = await import('monaco-editor')
    if (!editorHost.value) return
    editor = monaco.editor.create(editorHost.value, {
      value: props.code || '',
      language: 'python',
      minimap: { enabled: false },
      automaticLayout: true,
      theme: 'vs-dark',
      scrollBeyondLastLine: false,
    })
    editor.onDidChangeModelContent(() => {
      if (suppress) return
      emit('update:code', editor.getValue())
    })
    monacoReady.value = true
  } catch (_) {
    monacoReady.value = false
  }
})

watch(() => props.code, (value) => {
  if (!editor || editor.getValue() === value) return
  suppress = true
  editor.setValue(value || '')
  suppress = false
})

onBeforeUnmount(() => {
  if (editor) editor.dispose()
})
</script>

<style scoped>
.editor-card { min-width:0; border: 1px solid #303846; border-radius: 8px; overflow: hidden; background: #20242b; }
.editor-head { display: flex; justify-content: space-between; gap:8px; padding: 10px 12px; color: #f3f3f3; border-bottom: 1px solid rgba(255,255,255,.08); }
.editor-head span { color: #a1a1aa; font-size: 12px; }
.monaco-host { min-height: 460px; }
textarea { width: 100%; min-height: 460px; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; border: 0; outline: 0; background: #020617; color: #bfdbfe; padding: 14px; }
.validation { padding: 8px 12px; font-size: 13px; }
.validation.ok { color: #86efac; }
.validation.bad { color: #fca5a5; }
</style>
