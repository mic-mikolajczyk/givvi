<script setup lang="ts">
import { ArrowRight, Mail } from '@lucide/vue'
import { computed, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'

import { ApiError, currentUser, request, safeReturnTo, type User } from '../api'
import AppHeader from '../components/AppHeader.vue'

const { t, locale } = useI18n()
const route = useRoute()
const router = useRouter()
const mode = computed(() => String(route.name))
const name = ref('')
const email = ref('')
const password = ref('')
const token = ref('')
const busy = ref(false)
const success = ref('')
const error = ref('')
const fields = ref<Record<string, string>>({})
const next = computed(() => safeReturnTo(route.query.next))
const emailRequired = computed(() => ['login', 'register', 'forgot-password'].includes(mode.value))
const passwordRequired = computed(() => ['login', 'register', 'reset-password'].includes(mode.value))

watch(() => route.name, () => {
  token.value = new URLSearchParams(window.location.hash.slice(1)).get('token') || ''
  if (token.value) window.history.replaceState(window.history.state, '', window.location.pathname + window.location.search)
  success.value = ''
  fields.value = {}
  error.value = typeof route.query.error === 'string' ? route.query.error : ''
  password.value = ''
}, { immediate: true })

async function submit() {
  busy.value = true
  error.value = ''
  fields.value = {}
  try {
    const result = await request<{ code?: string; user?: User }>(`/auth/${mode.value}`, {
      name: name.value, email: email.value, password: password.value, language: locale.value, token: token.value,
    })
    if (['login', 'register'].includes(mode.value) && result.user) {
      currentUser.value = result.user
      locale.value = result.user.language
      await router.replace(next.value)
    } else {
      success.value = result.code || 'check_email'
      password.value = ''
    }
  } catch (failure) {
    const apiError = failure instanceof ApiError ? failure : new ApiError('service_unavailable')
    error.value = apiError.code
    fields.value = apiError.fields
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="page-shell">
    <AppHeader />
    <main class="auth-main">
      <h1 tabindex="-1">
        {{ t(`pages.${mode}`) }}
      </h1>
      <p
        v-if="error"
        class="feedback error"
        role="alert"
      >
        {{ t(`errors.${error}`) }}
      </p>
      <p
        v-if="success"
        class="feedback success"
        role="status"
      >
        <Mail
          :size="20"
          aria-hidden="true"
        />
        {{ t(`notices.${success}`) }}
      </p>
      <form
        v-if="!success || mode === 'login'"
        class="account-form"
        @submit.prevent="submit()"
      >
        <label v-if="mode === 'register'">
          <span>{{ t('name') }}</span>
          <input
            v-model="name"
            name="name"
            autocomplete="name"
            required
            maxlength="120"
            :aria-invalid="Boolean(fields.name)"
          >
          <small
            v-if="fields.name"
            class="error"
          >{{ t(`errors.${fields.name}`) }}</small>
        </label>
        <label v-if="emailRequired">
          <span>{{ t('email') }}</span>
          <input
            v-model="email"
            name="email"
            type="email"
            autocomplete="email"
            required
            maxlength="254"
            :aria-invalid="Boolean(fields.email)"
          >
          <small
            v-if="fields.email"
            class="error"
          >{{ t(`errors.${fields.email}`) }}</small>
        </label>
        <label v-if="passwordRequired">
          <span>{{ mode === 'reset-password' ? t('newPassword') : t('password') }}</span>
          <input
            v-model="password"
            name="password"
            type="password"
            :autocomplete="mode === 'login' ? 'current-password' : 'new-password'"
            required
            :minlength="mode === 'login' ? 1 : 12"
            maxlength="128"
            :aria-invalid="Boolean(fields.password)"
          >
          <small v-if="mode !== 'login'">{{ t('passwordHint') }}</small>
          <small
            v-if="fields.password"
            class="error"
          >{{ t(`errors.${fields.password}`) }}</small>
        </label>
        <button
          class="primary-button"
          type="submit"
          :disabled="busy"
        >
          {{ busy ? t('working') : t(`actions.${mode}`) }}
          <ArrowRight
            :size="18"
            aria-hidden="true"
          />
        </button>
      </form>
      <div class="auth-links">
        <RouterLink
          v-if="mode !== 'login'"
          :to="{ path: '/login', query: { next } }"
        >
          {{ t('actions.login') }}
        </RouterLink>
        <RouterLink
          v-if="mode === 'login'"
          :to="{ path: '/register', query: { next } }"
        >
          {{ t('actions.register') }}
        </RouterLink>
        <RouterLink
          v-if="mode === 'login'"
          to="/forgot-password"
        >
          {{ t('forgotPassword') }}
        </RouterLink>
      </div>
    </main>
  </div>
</template>
