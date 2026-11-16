<script setup lang="ts">
import { Gift } from '@lucide/vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, currentUser, request, type User } from '../api'

const { t, locale } = useI18n()
const error = ref('')

async function changeLanguage(event: Event) {
  const language = (event.target as HTMLSelectElement).value as 'en' | 'pl'
  locale.value = language
  localStorage.setItem('givvi-language', language)
  if (currentUser.value) {
    try {
      const payload = await request<{ user: User }>('/auth/profile', { name: currentUser.value.name, language })
      currentUser.value = payload.user
      error.value = ''
    } catch (failure) {
      error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
    }
  }
}
</script>

<template>
  <header class="page-header">
    <RouterLink
      class="wordmark"
      to="/"
      aria-label="GIVVI"
    >
      <Gift
        :size="28"
        aria-hidden="true"
      />
      <span>GIVVI</span>
    </RouterLink>
    <label class="language-control">
      <span class="sr-only">{{ t('language') }}</span>
      <select
        :value="locale"
        @change="changeLanguage"
      >
        <option value="en">English</option>
        <option value="pl">Polski</option>
      </select>
    </label>
    <p
      v-if="error"
      role="alert"
    >
      {{ t(`errors.${error}`) }}
    </p>
  </header>
</template>
