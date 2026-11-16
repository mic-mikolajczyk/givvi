<script setup lang="ts">
import { CalendarDays, Gift, UserRound } from '@lucide/vue'
import { useI18n } from 'vue-i18n'

import AppHeader from '../components/AppHeader.vue'

const { t } = useI18n()
</script>

<template>
  <div class="page-shell account-shell">
    <AppHeader />
    <main class="account-main">
      <RouterView />
    </main>
    <nav
      class="bottom-navigation"
      :aria-label="t('navigation')"
    >
      <RouterLink to="/events">
        <CalendarDays
          :size="22"
          aria-hidden="true"
        />{{ t('events') }}
      </RouterLink>
      <RouterLink to="/wishlist">
        <Gift
          :size="22"
          aria-hidden="true"
        />{{ t('wishlist') }}
      </RouterLink>
      <RouterLink to="/profile">
        <UserRound
          :size="22"
          aria-hidden="true"
        />{{ t('profile') }}
      </RouterLink>
    </nav>
  </div>
</template>
