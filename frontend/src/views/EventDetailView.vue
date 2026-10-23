<script setup lang="ts">
import { ArrowLeft, Copy, Gift, Mail, Pencil, Plus, Save, Trash2, Unlink, UserRound, X } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { ApiError, request, type EventParticipant, type EventRecord } from '../api'

const { t, locale } = useI18n()
const route = useRoute()
const event = ref<EventRecord | null>(null)
const loading = ref(true)
const saving = ref(false)
const editingDetails = ref(false)
const error = ref('')
const notice = ref('')
const participantName = ref('')
const inviteEmail = ref('')
const inviteLink = ref('')
const editingParticipant = ref('')
const editingName = ref('')
const form = reactive({
  name: '', exchange_date: '', exchange_time: '', time_zone: 'UTC', location: '', description: '',
  currency: 'EUR' as 'EUR' | 'PLN', budget: '',
})
const eventId = computed(() => String(route.params.eventId || ''))
const readOnly = computed(() => Boolean(event.value && (event.value.archived || event.value.cancelled || event.value.drawing_enabled)))

function applyEvent(value: EventRecord) {
  event.value = value
  Object.assign(form, {
    name: value.name,
    exchange_date: value.exchange_date,
    exchange_time: value.exchange_time || '',
    time_zone: value.time_zone,
    location: value.location || '',
    description: value.description || '',
    currency: value.currency,
    budget: value.budget || '',
  })
}

async function loadEvent() {
  loading.value = true
  error.value = ''
  try {
    const payload = await request<{ event: EventRecord }>(`/events/${eventId.value}`)
    applyEvent(payload.event)
    await loadInviteLink()
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    loading.value = false
  }
}

async function loadInviteLink() {
  inviteLink.value = ''
  if (readOnly.value) return
  try {
    const payload = await request<{ link: string }>(`/events/${eventId.value}/invite-link`)
    inviteLink.value = payload.link
  } catch (failure) {
    if (failure instanceof ApiError && ['invite_link_missing', 'not_found'].includes(failure.code)) return
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function saveEvent() {
  if (!event.value) return
  saving.value = true
  error.value = ''
  try {
    const payload = await request<{ event: EventRecord }>(`/events/${eventId.value}`, {
      ...form,
      exchange_time: form.exchange_time || null,
      location: form.location || null,
      description: form.description || null,
      budget: form.budget || null,
    }, true, 'PATCH')
    applyEvent(payload.event)
    editingDetails.value = false
    notice.value = 'saved'
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    saving.value = false
  }
}

function beginEdit() {
  notice.value = ''
  editingDetails.value = true
}

function cancelEdit() {
  if (event.value) applyEvent(event.value)
  error.value = ''
  editingDetails.value = false
}

function formatDate(value: string) {
  return new Intl.DateTimeFormat(locale.value, { dateStyle: 'long', timeZone: 'UTC' }).format(new Date(`${value}T00:00:00Z`))
}

async function addParticipant() {
  if (!event.value) return
  error.value = ''
  try {
    const payload = await request<{ participant: EventParticipant }>(`/events/${eventId.value}/participants`, {
      name: participantName.value,
    })
    event.value.participants.push(payload.participant)
    event.value.participants.sort((left, right) => left.name.localeCompare(right.name))
    participantName.value = ''
    notice.value = 'participant_added'
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

function beginRename(participant: EventParticipant) {
  editingParticipant.value = participant.id
  editingName.value = participant.name
}

async function saveRename(participant: EventParticipant) {
  try {
    const payload = await request<{ participant: EventParticipant }>(
      `/events/${eventId.value}/participants/${participant.id}`, { name: editingName.value }, true, 'PATCH',
    )
    Object.assign(participant, payload.participant)
    event.value?.participants.sort((left, right) => left.name.localeCompare(right.name))
    editingParticipant.value = ''
    notice.value = 'saved'
    error.value = ''
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function removeParticipant(participant: EventParticipant) {
  try {
    await request(`/events/${eventId.value}/participants/${participant.id}`, {}, true, 'DELETE')
    if (event.value) event.value.participants = event.value.participants.filter((item) => item.id !== participant.id)
    notice.value = 'participant_removed'
    error.value = ''
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function updateInviteLink() {
  error.value = ''
  try {
    const payload = await request<{ link: string }>(`/events/${eventId.value}/invite-link`, {}, true, 'POST')
    inviteLink.value = payload.link
    notice.value = 'invite_link_created'
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function revokeInviteLink() {
  if (!window.confirm(t('confirmRevokeInviteLink'))) return
  try {
    await request(`/events/${eventId.value}/invite-link`, {}, true, 'DELETE')
    inviteLink.value = ''
    notice.value = 'invite_link_revoked'
    error.value = ''
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function copyInviteLink() {
  try {
    await navigator.clipboard.writeText(inviteLink.value)
    notice.value = 'invite_link_copied'
    error.value = ''
  } catch {
    error.value = 'clipboard_unavailable'
  }
}

async function sendInvitation() {
  try {
    await request(`/events/${eventId.value}/invitations`, { email: inviteEmail.value })
    inviteEmail.value = ''
    notice.value = 'invitation_queued'
    error.value = ''
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function releaseClaim(participant: EventParticipant) {
  if (!window.confirm(t('confirmReleaseClaim'))) return
  try {
    await request(`/events/${eventId.value}/participants/${participant.id}/claim`, {}, true, 'DELETE')
    participant.claimed = false
    notice.value = 'claim_released'
    error.value = ''
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

watch(eventId, loadEvent, { immediate: true })
</script>

<template>
  <section class="event-detail-view">
    <RouterLink
      class="back-link"
      to="/events"
    >
      <ArrowLeft
        :size="18"
        aria-hidden="true"
      />{{ t('backToEvents') }}
    </RouterLink>
    <p
      v-if="loading"
      class="empty-state"
      role="status"
    >
      {{ t('loading') }}
    </p>
    <template v-else-if="event">
      <div class="view-heading event-detail-heading">
        <div>
          <p class="eyebrow">
            {{ t('eventDetails') }}
          </p>
          <h1 tabindex="-1">
            {{ event.name }}
          </h1>
        </div>
        <div class="event-statuses">
          <span
            v-if="event.cancelled"
            class="state-label cancelled-state"
          >{{ t('cancelled') }}</span>
          <span
            v-else-if="event.archived"
            class="state-label"
          >{{ t('archived') }}</span>
          <span
            v-if="event.drawing_enabled"
            class="state-label"
          >{{ t('drawingEnabled') }}</span>
        </div>
      </div>
      <p
        v-if="error"
        class="feedback error"
        role="alert"
      >
        {{ t(`errors.${error}`) }}
      </p>
      <p
        v-if="notice"
        class="feedback success"
        role="status"
      >
        {{ t(`notices.${notice}`) }}
      </p>

      <section v-if="!editingDetails" class="event-form detail-summary">
        <div class="section-heading">
          <h2>{{ t('eventDetails') }}</h2>
          <button v-if="event.is_admin && !readOnly" class="secondary-button edit-event-button" type="button" @click="beginEdit">
            <Pencil :size="18" aria-hidden="true" />{{ t('editEvent') }}
          </button>
        </div>
        <dl class="event-facts">
          <div><dt>{{ t('exchangeDate') }}</dt><dd>{{ formatDate(event.exchange_date) }}</dd></div>
          <div><dt>{{ t('exchangeTime') }}</dt><dd>{{ event.exchange_time || t('notSet') }}</dd></div>
          <div><dt>{{ t('timeZone') }}</dt><dd>{{ event.time_zone }}</dd></div>
          <div><dt>{{ t('budget') }}</dt><dd>{{ event.budget ? `${event.budget} ${event.currency}` : `${t('notSet')} (${event.currency})` }}</dd></div>
          <div><dt>{{ t('location') }}</dt><dd>{{ event.location || t('notSet') }}</dd></div>
          <div class="event-fact-wide"><dt>{{ t('description') }}</dt><dd>{{ event.description || t('notSet') }}</dd></div>
        </dl>
      </section>

      <form v-else class="event-form detail-form" @submit.prevent="saveEvent">
        <div class="section-heading"><h2>{{ t('editEvent') }}</h2></div>
        <fieldset :disabled="saving">
          <label><span>{{ t('eventName') }}</span><input v-model="form.name" name="name" maxlength="120" required></label>
          <div class="event-form-grid">
            <label><span>{{ t('exchangeDate') }}</span><input v-model="form.exchange_date" name="exchange_date" type="date" required></label>
            <label><span>{{ t('exchangeTime') }}</span><input v-model="form.exchange_time" name="exchange_time" type="time"></label>
            <label><span>{{ t('timeZone') }}</span><input v-model="form.time_zone" name="time_zone" maxlength="64" required></label>
            <label>
              <span>{{ t('currency') }}</span>
              <select v-model="form.currency" name="currency"><option value="EUR">EUR</option><option value="PLN">PLN</option></select>
            </label>
            <label><span>{{ t('budget') }}</span><input v-model="form.budget" name="budget" type="number" min="0" max="999999.99" step="0.01"></label>
            <label><span>{{ t('location') }}</span><input v-model="form.location" name="location" maxlength="255"></label>
          </div>
          <label><span>{{ t('description') }}</span><textarea v-model="form.description" name="description" maxlength="2000" rows="3" /></label>
          <div class="form-actions">
            <button class="primary-button" type="submit">
              <Save :size="18" aria-hidden="true" />{{ saving ? t('working') : t('saveEvent') }}
            </button>
            <button class="secondary-button cancel-edit-button" type="button" @click="cancelEdit">{{ t('cancel') }}</button>
          </div>
        </fieldset>
      </form>

      <section
        v-if="!readOnly"
        class="invitation-section"
        aria-labelledby="invitation-heading"
      >
        <div class="section-heading">
          <h2 id="invitation-heading">
            {{ t('shareInviteLink') }}
          </h2>
          <button
            v-if="event.is_admin"
            class="secondary-button"
            type="button"
            @click="updateInviteLink"
          >
            {{ inviteLink ? t('regenerateInviteLink') : t('generateInviteLink') }}
          </button>
        </div>
        <div
          v-if="inviteLink"
          class="invite-link-row"
        >
          <label
            class="sr-only"
            :for="`invite-link-${event.id}`"
          >{{ t('shareInviteLink') }}</label>
          <input
            :id="`invite-link-${event.id}`"
            :value="inviteLink"
            readonly
          >
          <button
            class="icon-button"
            type="button"
            :aria-label="t('copyInviteLink')"
            :title="t('copyInviteLink')"
            @click="copyInviteLink"
          >
            <Copy
              :size="18"
              aria-hidden="true"
            />
          </button>
          <button
            v-if="event.is_admin"
            class="icon-button danger-button"
            type="button"
            :aria-label="t('revokeInviteLink')"
            :title="t('revokeInviteLink')"
            @click="revokeInviteLink"
          >
            <Unlink
              :size="18"
              aria-hidden="true"
            />
          </button>
        </div>
        <form
          v-if="event.is_admin"
          class="invitation-email-form"
          @submit.prevent="sendInvitation"
        >
          <label :for="`invite-email-${event.id}`">{{ t('inviteByEmail') }}</label>
          <div class="invite-link-row">
            <input
              :id="`invite-email-${event.id}`"
              v-model="inviteEmail"
              type="email"
              name="invite_email"
              maxlength="254"
              autocomplete="email"
              required
              :placeholder="t('invitationEmail')"
            >
            <button
              class="primary-button"
              type="submit"
            >
              <Mail
                :size="18"
                aria-hidden="true"
              />{{ t('sendInvitation') }}
            </button>
          </div>
        </form>
      </section>

      <section class="roster-section">
        <div class="section-heading"><h2>{{ t('roster') }}</h2><span>{{ event.participants.length }}/100</span></div>
        <form v-if="event.is_admin && !readOnly" class="roster-add-form" @submit.prevent="addParticipant">
          <label class="sr-only" for="participant-name">{{ t('participantName') }}</label>
          <input id="participant-name" v-model="participantName" name="participant_name" maxlength="120" required :placeholder="t('participantName')">
          <button class="primary-button" type="submit"><Plus :size="18" aria-hidden="true" />{{ t('addToRoster') }}</button>
        </form>
        <p v-if="!event.participants.length" class="roster-empty">{{ t('noParticipants') }}</p>
        <ul v-else class="roster-list">
          <li v-for="participant in event.participants" :key="participant.id" class="roster-row">
            <template v-if="editingParticipant === participant.id">
              <label class="sr-only" :for="`rename-${participant.id}`">{{ t('participantName') }}</label>
              <input :id="`rename-${participant.id}`" v-model="editingName" maxlength="120">
              <button class="icon-button" type="button" :aria-label="t('save')" :title="t('save')" @click="saveRename(participant)">
                <Save :size="18" aria-hidden="true" />
              </button>
              <button class="icon-button" type="button" :aria-label="t('cancel')" :title="t('cancel')" @click="editingParticipant = ''">
                <X :size="18" aria-hidden="true" />
              </button>
            </template>
            <template v-else>
              <span class="roster-name"><UserRound :size="18" aria-hidden="true" />{{ participant.name }}</span>
              <span :class="['claim-state', participant.claimed ? 'is-claimed' : '']">{{ participant.claimed ? t('claimed') : t('notClaimed') }}</span>
              <RouterLink
                v-if="event.is_participant && participant.claimed"
                class="icon-button wishlist-participant-link"
                :to="`/events/${event.id}/participants/${participant.id}/wishlist`"
                :aria-label="`${t('viewWishlist')} ${participant.name}`"
                :title="t('viewWishlist')"
              >
                <Gift :size="18" aria-hidden="true" />
              </RouterLink>
              <button
                v-if="event.is_admin && !readOnly && participant.claimed"
                class="icon-button danger-button"
                type="button"
                :aria-label="`${t('releaseClaim')} ${participant.name}`"
                :title="t('releaseClaim')"
                @click="releaseClaim(participant)"
              >
                <X :size="18" aria-hidden="true" />
              </button>
              <button v-if="event.is_admin && !readOnly" class="icon-button" type="button" :aria-label="`${t('rename')} ${participant.name}`" :title="t('rename')" @click="beginRename(participant)">
                <Pencil :size="18" aria-hidden="true" />
              </button>
              <button v-if="event.is_admin && !readOnly" class="icon-button danger-button" type="button" :aria-label="`${t('remove')} ${participant.name}`" :title="t('remove')" :disabled="participant.claimed" @click="removeParticipant(participant)">
                <Trash2 :size="18" aria-hidden="true" />
              </button>
            </template>
          </li>
        </ul>
      </section>
    </template>
    <p v-else class="empty-state">{{ t(`errors.${error || 'not_found'}`) }}</p>
  </section>
</template>