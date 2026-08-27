<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: string
    multiline?: boolean
    rows?: number
    placeholder?: string
    disabled?: boolean
    compact?: boolean
  }>(),
  {
    multiline: false,
    rows: 4,
    placeholder: '',
    disabled: false,
    compact: false,
  },
)

const emit = defineEmits<{ 'update:modelValue': [value: string] }>()
const overlay = ref<HTMLElement | null>(null)

const tokens = computed(() => {
  const parts = String(props.modelValue || '').split(/({{[\s\S]*?}}|{%[\s\S]*?%}|{#[\s\S]*?#})/g)
  return parts.filter(Boolean).map((text) => ({
    text,
    template: /^(?:{{|{%|{#)/.test(text),
  }))
})

function updateValue(event: Event) {
  emit('update:modelValue', (event.target as HTMLInputElement | HTMLTextAreaElement).value)
}

function syncScroll(event: Event) {
  if (!overlay.value) return
  const input = event.target as HTMLInputElement | HTMLTextAreaElement
  overlay.value.scrollLeft = input.scrollLeft
  overlay.value.scrollTop = input.scrollTop
}
</script>

<template>
  <div
    class="template-text-input"
    :class="{
      'template-text-input--multiline': multiline,
      'template-text-input--disabled': disabled,
      'template-text-input--compact': compact && !multiline,
    }"
  >
    <div ref="overlay" class="template-text-input__overlay" :aria-hidden="true">
      <template v-if="tokens.length">
        <span v-for="(token, index) in tokens" :key="index" :class="{ 'template-token': token.template }">
          {{ token.text }}
        </span>
      </template>
      <span v-else class="template-placeholder">{{ placeholder }}</span>
    </div>
    <textarea
      v-if="multiline"
      class="template-text-input__control"
      :value="modelValue"
      :rows="rows"
      :disabled="disabled"
      spellcheck="false"
      @input="updateValue"
      @scroll="syncScroll"
    />
    <input
      v-else
      class="template-text-input__control"
      :value="modelValue"
      :disabled="disabled"
      spellcheck="false"
      @input="updateValue"
      @scroll="syncScroll"
    />
  </div>
</template>

<style scoped>
.template-text-input {
  position: relative;
  width: 100%;
  min-width: 0;
  height: 34px;
  color: rgb(31 41 55);
  background: var(--n-color, #fff);
  border: 1px solid rgb(224 224 230);
  border-radius: 3px;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.template-text-input:focus-within {
  border-color: rgb(24 160 88);
  box-shadow: 0 0 0 2px rgb(24 160 88 / 12%);
}

.template-text-input--multiline {
  height: auto;
  min-height: 132px;
}

.template-text-input--compact {
  height: 26px;
}

.template-text-input--compact .template-text-input__overlay,
.template-text-input--compact .template-text-input__control {
  padding-top: 2px;
  padding-bottom: 2px;
}

.template-text-input--disabled {
  opacity: 0.55;
  background: rgb(250 250 252);
}

.template-text-input__overlay,
.template-text-input__control {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  margin: 0;
  padding: 6px 10px;
  border: 0;
  font: inherit;
  font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
  font-size: 13px;
  line-height: 20px;
  letter-spacing: 0;
  white-space: pre;
}

.template-text-input__overlay {
  position: absolute;
  inset: 0;
  overflow: hidden;
  color: rgb(31 41 55);
  pointer-events: none;
}

.template-text-input__control {
  position: relative;
  display: block;
  overflow: auto;
  color: transparent;
  caret-color: rgb(31 41 55);
  background: transparent;
  outline: none;
  resize: none;
  -webkit-text-fill-color: transparent;
}

.template-text-input--multiline .template-text-input__overlay,
.template-text-input--multiline .template-text-input__control {
  min-height: 132px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.template-token {
  color: rgb(3 105 161);
  background: rgb(14 165 233 / 16%);
  border-radius: 2px;
  font-weight: 600;
}

.template-placeholder {
  color: rgb(156 163 175);
}

:global(html.dark .template-text-input) {
  color: rgb(229 231 235);
  background: rgb(24 24 28);
  border-color: rgb(63 63 70);
}

:global(html.dark .template-text-input__control) {
  caret-color: rgb(229 231 235);
}

:global(html.dark .template-text-input__overlay) {
  color: rgb(243 244 246);
}

:global(html.dark .template-token) {
  color: rgb(125 211 252);
  background: rgb(14 165 233 / 24%);
}

:global(html.dark .template-placeholder) {
  color: rgb(161 161 170);
}
</style>
