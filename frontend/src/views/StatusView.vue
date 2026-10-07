<script setup lang="ts">
import { CircleCheck, CloudOff, Gift, RefreshCw } from '@lucide/vue'
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'

const { t, locale } = useI18n()
const status = ref<'checking' | 'connected' | 'unavailable'>('checking')
const requestTimeoutMilliseconds = 5000
let activeRequest: AbortController | undefined

watch(locale, (language) => { document.documentElement.lang = language }, { immediate: true })

async function checkReadiness() {
  activeRequest?.abort()
  const controller = new AbortController()
  activeRequest = controller
  status.value = 'checking'
  const timeout = setTimeout(() => controller.abort(), requestTimeoutMilliseconds)
  try {
    const response = await fetch('/api/health/ready', { signal: controller.signal, cache: 'no-store' })
    const payload = response.ok ? await response.json() : null
    status.value = payload?.status === 'ready' ? 'connected' : 'unavailable'
  } catch {
    status.value = 'unavailable'
  } finally {
    clearTimeout(timeout)
  }
}

onMounted(checkReadiness)
onUnmounted(() => activeRequest?.abort())
</script>

<template>
  <div class="page-shell">
    <header class="page-header">
      <a
        class="wordmark"
        href="/"
        aria-label="GIVVI"
      >
        <Gift
          :size="28"
          aria-hidden="true"
        />
        <span>GIVVI</span>
      </a>
      <label class="language-control">
        <span class="sr-only">{{ t('language') }}</span>
        <select v-model="locale">
          <option value="en">English</option>
          <option value="pl">Polski</option>
        </select>
      </label>
    </header>
    <main class="status-main">
      <h1>{{ t('statusTitle') }}</h1>
      <div class="status-row">
        <p
          role="status"
          :class="['status-value', status]"
        >
          <CircleCheck
            v-if="status === 'connected'"
            :size="22"
            aria-hidden="true"
          />
          <CloudOff
            v-else-if="status === 'unavailable'"
            :size="22"
            aria-hidden="true"
          />
          <RefreshCw
            v-else
            :size="22"
            aria-hidden="true"
          />
          {{ t(status) }}
        </p>
        <button
          class="icon-button"
          type="button"
          :disabled="status === 'checking'"
          :title="t('retry')"
          :aria-label="t('retry')"
          @click="checkReadiness"
        >
          <RefreshCw
            :size="20"
            aria-hidden="true"
          />
        </button>
      </div>
    </main>
  </div>
</template>
