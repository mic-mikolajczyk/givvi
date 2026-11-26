<script setup lang="ts">
const props = defineProps<{
  modelValue: 'en' | 'pl'
  label: string
}>()

const emit = defineEmits<{
  'update:modelValue': [language: 'en' | 'pl']
}>()

function toggleLanguage() {
  emit('update:modelValue', props.modelValue === 'pl' ? 'en' : 'pl')
}
</script>

<template>
  <button
    class="language-switch"
    type="button"
    role="switch"
    :aria-label="label"
    :aria-checked="modelValue === 'en'"
    @click="toggleLanguage"
  >
    <span :class="{ 'is-active': modelValue === 'pl' }">PL</span>
    <span :class="{ 'is-active': modelValue === 'en' }">EN</span>
  </button>
</template>
