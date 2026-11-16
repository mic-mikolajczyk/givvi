<script setup lang="ts">
import { CalendarDays, Gift } from '@lucide/vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

const { t } = useI18n()
const route = useRoute()
</script>

<template>
  <section>
    <h1 tabindex="-1">
      {{ t(String(route.name)) }}
    </h1>
    <div class="empty-state">
      <CalendarDays
        v-if="route.name === 'events'"
        :size="40"
        aria-hidden="true"
      />
      <Gift
        v-else
        :size="40"
        aria-hidden="true"
      />
      <p>{{ route.name === 'events' ? t('noEvents') : t('noGifts') }}</p>
    </div>
  </section>
</template>
