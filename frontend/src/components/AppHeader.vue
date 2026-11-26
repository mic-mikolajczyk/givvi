<script setup lang="ts">
import { CalendarDays, Gift, UserRound } from '@lucide/vue'
import { ref } from 'vue'
import { useI18n } from 'vue-i18n'

import { ApiError, currentUser, request, type User } from '../api'
import LanguageSwitch from './LanguageSwitch.vue'

const { t, locale } = useI18n()
const error = ref('')

async function changeLanguage(language: 'en' | 'pl') {
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
    <div class="page-header-inner container">
      <RouterLink
        class="wordmark"
        to="/"
        aria-label="GIVVI"
      >
        <span class="brand-mark">
          <Gift
            :size="22"
            aria-hidden="true"
          />
        </span>
        <span>GIVVI</span>
      </RouterLink>
      <nav
        v-if="currentUser"
        class="desktop-navigation"
        :aria-label="t('navigation')"
      >
        <RouterLink to="/events">
          <CalendarDays
            :size="17"
            aria-hidden="true"
          />{{ t('events') }}
        </RouterLink>
        <RouterLink to="/wishlist">
          <Gift
            :size="17"
            aria-hidden="true"
          />{{ t('wishlist') }}
        </RouterLink>
        <RouterLink to="/profile">
          <UserRound
            :size="17"
            aria-hidden="true"
          />{{ t('profile') }}
        </RouterLink>
      </nav>
      <div class="header-actions">
        <div class="language-control">
          <LanguageSwitch
            :model-value="locale === 'en' ? 'en' : 'pl'"
            :label="t('language')"
            @update:model-value="changeLanguage"
          />
        </div>
        <p
          v-if="error"
          class="header-error"
          role="alert"
        >
          {{ t(`errors.${error}`) }}
        </p>
      </div>
    </div>
  </header>
</template>
