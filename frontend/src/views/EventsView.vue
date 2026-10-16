<script setup lang="ts">
import { CalendarDays, ChevronLeft, ChevronRight, Plus, X } from '@lucide/vue'
import { computed, onMounted, reactive, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError, request, type EventRecord } from '../api'

const { t, locale } = useI18n()
const router = useRouter()
const events = ref<EventRecord[]>([])
const loading = ref(true)
const saving = ref(false)
const formOpen = ref(false)
const error = ref('')
const page = ref(1)
const totalEvents = ref(0)
const pageSize = 50
const totalPages = computed(() => Math.max(1, Math.ceil(totalEvents.value / pageSize)))
const form = reactive({
  name: '', exchange_date: '', exchange_time: '', time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC',
  location: '', description: '', currency: 'EUR' as 'EUR' | 'PLN', budget: '',
})

const periods = computed(() => ['upcoming', 'ongoing', 'past'] as const)

async function loadEvents(targetPage = page.value) {
  loading.value = true
  try {
    const payload = await request<{ events: EventRecord[]; page: number; total: number }>(
      `/events?page=${targetPage}&page_size=${pageSize}`,
    )
    events.value = payload.events
    page.value = payload.page
    totalEvents.value = payload.total
    error.value = ''
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    loading.value = false
  }
}

function changePage(targetPage: number) {
  if (targetPage >= 1 && targetPage <= totalPages.value && targetPage !== page.value) {
    void loadEvents(targetPage)
  }
}

function openForm() {
  form.currency = locale.value === 'pl' ? 'PLN' : 'EUR'
  formOpen.value = true
}

async function createEvent() {
  saving.value = true
  error.value = ''
  try {
    const payload = await request<{ event: EventRecord }>('/events', {
      ...form,
      exchange_time: form.exchange_time || null,
      location: form.location || null,
      description: form.description || null,
      budget: form.budget || null,
    })
    await router.push(`/events/${payload.event.id}`)
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    saving.value = false
  }
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`))
}

onMounted(loadEvents)
</script>

<template>
  <section class="events-view">
    <div class="view-heading">
      <div>
        <p class="eyebrow">GIVVI</p>
        <h1 tabindex="-1">{{ t('events') }}</h1>
      </div>
      <button
        v-if="!formOpen"
        class="primary-button create-event-button"
        type="button"
        @click="openForm"
      >
        <Plus :size="18" aria-hidden="true" />{{ t('createEvent') }}
      </button>
    </div>

    <p v-if="error" class="feedback error" role="alert">{{ t(`errors.${error}`) }}</p>

    <form v-if="formOpen" class="event-form" @submit.prevent="createEvent">
      <div class="section-heading">
        <h2>{{ t('createEvent') }}</h2>
        <button class="icon-button" type="button" :aria-label="t('cancel')" :title="t('cancel')" @click="formOpen = false">
          <X :size="18" aria-hidden="true" />
        </button>
      </div>
      <label>
        <span>{{ t('eventName') }}</span>
        <input v-model="form.name" name="name" maxlength="120" required autocomplete="off">
      </label>
      <div class="event-form-grid">
        <label>
          <span>{{ t('exchangeDate') }}</span>
          <input v-model="form.exchange_date" name="exchange_date" type="date" required>
        </label>
        <label>
          <span>{{ t('exchangeTime') }}</span>
          <input v-model="form.exchange_time" name="exchange_time" type="time">
        </label>
        <label>
          <span>{{ t('timeZone') }}</span>
          <input v-model="form.time_zone" name="time_zone" maxlength="64" required>
        </label>
        <label>
          <span>{{ t('currency') }}</span>
          <select v-model="form.currency" name="currency">
            <option value="EUR">EUR</option>
            <option value="PLN">PLN</option>
          </select>
        </label>
        <label>
          <span>{{ t('budget') }}</span>
          <input v-model="form.budget" name="budget" type="number" min="0" max="999999.99" step="0.01">
        </label>
        <label>
          <span>{{ t('location') }}</span>
          <input v-model="form.location" name="location" maxlength="255">
        </label>
      </div>
      <label>
        <span>{{ t('description') }}</span>
        <textarea v-model="form.description" name="description" maxlength="2000" rows="3" />
      </label>
      <div class="form-actions">
        <button class="primary-button" type="submit" :disabled="saving">
          {{ saving ? t('working') : t('saveEvent') }}
        </button>
        <button class="text-button" type="button" @click="formOpen = false">{{ t('cancel') }}</button>
      </div>
    </form>

    <div v-if="loading" class="empty-state" role="status">{{ t('loading') }}</div>
    <div v-else-if="!events.length" class="empty-state">
      <CalendarDays :size="36" aria-hidden="true" />
      <p>{{ t('noEvents') }}</p>
    </div>
    <div v-else class="event-groups">
      <section v-for="period in periods" v-show="events.some((event) => event.period === period)" :key="period" class="event-group">
        <h2>{{ t(period) }}</h2>
        <RouterLink
          v-for="event in events.filter((item) => item.period === period)"
          :key="event.id"
          class="event-row"
          :to="`/events/${event.id}`"
        >
          <span class="event-row-main">
            <strong>{{ event.name }}</strong>
            <span>{{ formatDate(event.exchange_date) }}<template v-if="event.exchange_time"> · {{ event.exchange_time }}</template></span>
          </span>
          <span class="event-row-meta">
            <span>{{ event.participants.length }}</span>
            <span v-if="event.archived" class="state-label">{{ t('archived') }}</span>
            <span v-if="event.cancelled" class="state-label">{{ t('cancelled') }}</span>
          </span>
        </RouterLink>
      </section>
    </div>
    <nav v-if="!loading && totalEvents > pageSize" class="event-pagination" :aria-label="t('eventPages')">
      <button
        class="icon-button"
        type="button"
        :aria-label="t('previousPage')"
        :title="t('previousPage')"
        :disabled="page <= 1"
        @click="changePage(page - 1)"
      >
        <ChevronLeft :size="20" aria-hidden="true" />
      </button>
      <span>{{ page }} / {{ totalPages }}</span>
      <button
        class="icon-button"
        type="button"
        :aria-label="t('nextPage')"
        :title="t('nextPage')"
        :disabled="page >= totalPages"
        @click="changePage(page + 1)"
      >
        <ChevronRight :size="20" aria-hidden="true" />
      </button>
    </nav>
  </section>
</template>