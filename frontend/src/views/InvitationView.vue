<script setup lang="ts">
import { ArrowRight, Gift, UserRound } from '@lucide/vue'
import { computed, onMounted, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, currentUser, publicRequest, refreshUser, request } from '../api'
import AppHeader from '../components/AppHeader.vue'

interface Invitation {
  event_id: string
  participants: { id: string; name: string; available: boolean }[]
}

const { t } = useI18n()
const route = useRoute()
const router = useRouter()
const invitation = ref<Invitation | null>(null)
const loading = ref(true)
const submitting = ref(false)
const error = ref('')
const claimError = ref('')
const eventId = computed(() => String(route.params.eventId || ''))
const token = ref('')
const availableParticipants = computed(() => invitation.value?.participants.filter((participant) => participant.available) || [])
const signInDestination = computed(() => ({ path: '/login', query: { next: `/invite/${eventId.value}` } }))
const registerDestination = computed(() => ({ path: '/register', query: { next: `/invite/${eventId.value}` } }))

async function loadInvitation() {
  loading.value = true
  error.value = ''
  try {
    const fragmentToken = new URLSearchParams(route.hash.slice(1)).get('token') || ''
    const storageKey = `givvi-invite-${eventId.value}`
    token.value = fragmentToken || sessionStorage.getItem(storageKey) || ''
    if (fragmentToken) {
      sessionStorage.setItem(storageKey, fragmentToken)
      await router.replace({ path: route.path, query: route.query, hash: '' })
    }
    if (!token.value) throw new ApiError('invite_invalid')
    try {
      await refreshUser()
    } catch (failure) {
      if (!(failure instanceof ApiError) || failure.code !== 'unauthenticated') {
        error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
      }
    }
    const result = await publicRequest<{ invitation: Invitation }>(`/events/${eventId.value}/invitation-preview`, {
      token: token.value,
    })
    invitation.value = result.invitation
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    loading.value = false
  }
}

async function claim(participantId: string) {
  submitting.value = true
  claimError.value = ''
  try {
    await request(`/events/${eventId.value}/claim`, { participant_id: participantId, token: token.value })
    sessionStorage.removeItem(`givvi-invite-${eventId.value}`)
    await router.replace(`/events/${eventId.value}`)
  } catch (failure) {
    if (failure instanceof ApiError && failure.code === 'entry_unavailable') {
      await loadInvitation()
      claimError.value = failure.code
      return
    }
    if (failure instanceof ApiError && failure.code === 'already_claimed') {
      sessionStorage.removeItem(`givvi-invite-${eventId.value}`)
      await router.replace(`/events/${eventId.value}`)
      return
    }
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    submitting.value = false
  }
}

onMounted(loadInvitation)
</script>

<template>
  <div class="page-shell">
    <AppHeader />
    <main class="auth-main invitation-main">
      <p class="eyebrow">
        {{ t('invitation') }}
      </p>
      <h1 tabindex="-1">
        {{ t('chooseYourName') }}
      </h1>
      <p
        v-if="loading"
        class="empty-state"
        role="status"
      >
        {{ t('loading') }}
      </p>
      <p
        v-if="error"
        class="feedback error"
        role="alert"
      >
        {{ t(`errors.${error}`) }}
      </p>
      <p
        v-if="claimError"
        class="feedback error"
        role="alert"
      >
        {{ t(`errors.${claimError}`) }}
      </p>
      <template v-if="invitation && !error">
        <p class="invitation-intro">
          {{ t('invitationRosterIntro') }}
        </p>
        <ul class="invitation-roster">
          <li
            v-for="participant in invitation.participants"
            :key="participant.id"
          >
            <span><UserRound
              :size="18"
              aria-hidden="true"
            />{{ participant.name }}</span>
            <button
              v-if="participant.available && currentUser"
              class="primary-button"
              type="button"
              :disabled="submitting"
              @click="claim(participant.id)"
            >
              <Gift
                :size="18"
                aria-hidden="true"
              />{{ t('claimEntry') }}
            </button>
            <span
              v-else
              class="claim-state"
            >{{ participant.available ? t('available') : t('entryUnavailable') }}</span>
          </li>
        </ul>
        <div
          v-if="!currentUser"
          class="auth-links invitation-auth-links"
        >
          <RouterLink :to="signInDestination">
            {{ t('actions.login') }}<ArrowRight
              :size="18"
              aria-hidden="true"
            />
          </RouterLink>
          <RouterLink :to="registerDestination">
            {{ t('actions.register') }}<ArrowRight
              :size="18"
              aria-hidden="true"
            />
          </RouterLink>
        </div>
        <p
          v-else-if="!availableParticipants.length"
          class="feedback"
        >
          {{ t('noAvailableEntries') }}
        </p>
      </template>
    </main>
  </div>
</template>