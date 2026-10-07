<script setup lang="ts">
import { LogOut, Save } from '@lucide/vue'
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRouter } from 'vue-router'

import { ApiError, clearSession, currentUser, request, type User } from '../api'

const { t, locale } = useI18n()
const router = useRouter()
const name = ref(currentUser.value?.name || '')
const language = ref(currentUser.value?.language || 'en')
watch(() => currentUser.value?.language, (value) => { if (value) language.value = value })
const email = ref('')
const emailPassword = ref('')
const currentPassword = ref('')
const password = ref('')
const busy = ref(false)
const notice = ref('')
const error = ref('')
const fields = ref<Record<string, string>>({})

async function submit(operation: 'profile' | 'change-email' | 'change-password' | 'logout') {
  busy.value = true
  notice.value = ''
  error.value = ''
  fields.value = {}
  try {
    const payload = operation === 'profile' ? { name: name.value, language: language.value }
      : operation === 'change-email' ? { email: email.value, current_password: emailPassword.value }
        : operation === 'change-password' ? { current_password: currentPassword.value, password: password.value } : {}
    const result = await request<{ user?: User; code: string }>(`/auth/${operation}`, payload)
    notice.value = result.code
    if (result.user) { currentUser.value = result.user; locale.value = result.user.language }
    if (operation === 'logout' || operation === 'change-password') {
      clearSession()
      await router.replace('/login')
    } else if (operation === 'change-email' && currentUser.value) {
      currentUser.value.pending_email = email.value
    }
    emailPassword.value = ''
    currentPassword.value = ''
    password.value = ''
  } catch (failure) {
    const apiError = failure instanceof ApiError ? failure : new ApiError('service_unavailable')
    error.value = apiError.code
    fields.value = apiError.fields
    if (apiError.code === 'unauthenticated') await router.replace('/login?next=/profile')
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <h1 tabindex="-1">
    {{ t('profile') }}
  </h1>
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
  <form
    class="account-form profile-section"
    @submit.prevent="submit('profile')"
  >
    <label><span>{{ t('name') }}</span><input
      v-model="name"
      name="name"
      required
      maxlength="120"
      autocomplete="name"
    ><small
      v-if="fields.name"
      class="error"
    >{{ t(`errors.${fields.name}`) }}</small></label>
    <label><span>{{ t('language') }}</span><select
      v-model="language"
      name="language"
    ><option value="en">English</option><option value="pl">Polski</option></select></label>
    <button
      class="primary-button"
      type="submit"
      :disabled="busy"
    >
      <Save
        :size="18"
        aria-hidden="true"
      />{{ t('save') }}
    </button>
  </form>
  <section class="profile-section">
    <h2>{{ t('email') }}</h2>
    <p class="profile-email">
      {{ currentUser?.email }}
    </p>
    <p v-if="currentUser?.pending_email">
      {{ t('pendingEmail') }}: {{ currentUser.pending_email }}
    </p>
    <form
      class="account-form"
      @submit.prevent="submit('change-email')"
    >
      <label><span>{{ t('newEmail') }}</span><input
        v-model="email"
        name="email"
        type="email"
        required
        maxlength="254"
        autocomplete="email"
      ><small
        v-if="fields.email"
        class="error"
      >{{ t(`errors.${fields.email}`) }}</small></label>
      <label><span>{{ t('currentPassword') }}</span><input
        v-model="emailPassword"
        name="email-password"
        type="password"
        required
        maxlength="128"
        autocomplete="current-password"
      ></label>
      <button
        class="secondary-button"
        type="submit"
        :disabled="busy"
      >
        {{ t('changeEmail') }}
      </button>
    </form>
  </section>
  <section class="profile-section">
    <h2>{{ t('password') }}</h2>
    <form
      class="account-form"
      @submit.prevent="submit('change-password')"
    >
      <label><span>{{ t('currentPassword') }}</span><input
        v-model="currentPassword"
        name="current-password"
        type="password"
        required
        maxlength="128"
        autocomplete="current-password"
      ></label>
      <label><span>{{ t('newPassword') }}</span><input
        v-model="password"
        name="new-password"
        type="password"
        required
        minlength="12"
        maxlength="128"
        autocomplete="new-password"
      ><small>{{ t('passwordHint') }}</small><small
        v-if="fields.password"
        class="error"
      >{{ t(`errors.${fields.password}`) }}</small></label>
      <button
        class="secondary-button"
        type="submit"
        :disabled="busy"
      >
        {{ t('changePassword') }}
      </button>
    </form>
  </section>
  <button
    class="secondary-button logout-button"
    type="button"
    :disabled="busy"
    @click="submit('logout')"
  >
    <LogOut
      :size="18"
      aria-hidden="true"
    />{{ t('logout') }}
  </button>
</template>
