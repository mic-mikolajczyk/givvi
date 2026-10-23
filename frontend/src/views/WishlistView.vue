<script setup lang="ts">
import { ArrowDown, ArrowLeft, ArrowUp, ExternalLink, Pencil, Plus, Save, Trash2, X } from '@lucide/vue'
import { computed, reactive, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute } from 'vue-router'

import { ApiError, request, type GiftRecord } from '../api'

interface EventWishlistContext {
  event: { id: string; name: string; budget: string | null; currency: 'EUR' | 'PLN' }
  participant: { id: string; name: string }
  gifts: GiftRecord[]
}

const { t } = useI18n()
const route = useRoute()
const gifts = ref<GiftRecord[]>([])
const orderVersion = ref(0)
const event = ref<EventWishlistContext['event'] | null>(null)
const participant = ref<EventWishlistContext['participant'] | null>(null)
const loading = ref(true)
const saving = ref(false)
const formOpen = ref(false)
const editingGiftId = ref('')
const error = ref('')
const notice = ref('')
const eventId = computed(() => String(route.params.eventId || ''))
const participantId = computed(() => String(route.params.participantId || ''))
const participantView = computed(() => Boolean(eventId.value && participantId.value))
const form = reactive({ name: '', description: '', price: '', currency: 'EUR' as 'EUR' | 'PLN', link: '' })

function resetForm() {
  Object.assign(form, { name: '', description: '', price: '', currency: 'EUR', link: '' })
  editingGiftId.value = ''
}

async function loadWishlist() {
  loading.value = true
  error.value = ''
  try {
    if (participantView.value) {
      const payload = await request<EventWishlistContext>(
        `/events/${eventId.value}/participants/${participantId.value}/wishlist`,
      )
      event.value = payload.event
      participant.value = payload.participant
      gifts.value = payload.gifts
    } else {
      const payload = await request<{ gifts: GiftRecord[]; order_version: number }>('/wishlist')
      gifts.value = payload.gifts
      orderVersion.value = payload.order_version
      event.value = null
      participant.value = null
    }
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    loading.value = false
  }
}

function beginAdd() {
  notice.value = ''
  error.value = ''
  resetForm()
  formOpen.value = true
}

function beginEdit(gift: GiftRecord) {
  Object.assign(form, {
    name: gift.name,
    description: gift.description || '',
    price: gift.price || '',
    currency: gift.currency || 'EUR',
    link: gift.link || '',
  })
  editingGiftId.value = gift.id
  formOpen.value = true
  notice.value = ''
  error.value = ''
}

function cancelForm() {
  formOpen.value = false
  resetForm()
}

async function saveGift() {
  saving.value = true
  error.value = ''
  try {
    const body = {
      name: form.name,
      description: form.description.trim() || null,
      price: form.price || null,
      currency: form.price ? form.currency : null,
      link: form.link.trim() || null,
    }
    if (editingGiftId.value) {
      const payload = await request<{ gift: GiftRecord; order_version: number }>(
        `/wishlist/gifts/${editingGiftId.value}`, body, true, 'PATCH',
      )
      gifts.value = gifts.value.map((gift) => gift.id === payload.gift.id ? payload.gift : gift)
      notice.value = 'gift_updated'
    } else {
      const payload = await request<{ gift: GiftRecord; order_version: number }>('/wishlist/gifts', body)
      gifts.value = [...gifts.value, payload.gift]
      orderVersion.value = payload.order_version
      notice.value = 'gift_added'
    }
    formOpen.value = false
    resetForm()
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  } finally {
    saving.value = false
  }
}

async function removeGift(gift: GiftRecord) {
  if (!window.confirm(t('confirmDeleteGift', { name: gift.name }))) return
  error.value = ''
  try {
    const payload = await request<{ order_version: number }>(`/wishlist/gifts/${gift.id}`, {}, true, 'DELETE')
    gifts.value = gifts.value.filter((item) => item.id !== gift.id).map((item, position) => ({ ...item, position }))
    orderVersion.value = payload.order_version
    notice.value = 'gift_removed'
  } catch (failure) {
    error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
  }
}

async function moveGift(gift: GiftRecord, direction: -1 | 1) {
  const currentIndex = gifts.value.findIndex((item) => item.id === gift.id)
  const targetIndex = currentIndex + direction
  if (targetIndex < 0 || targetIndex >= gifts.value.length) return
  const reordered = [...gifts.value]
  reordered.splice(currentIndex, 1)
  reordered.splice(targetIndex, 0, gift)
  error.value = ''
  try {
    const payload = await request<{ gifts: GiftRecord[]; order_version: number }>('/wishlist/order', {
      gift_ids: reordered.map((item) => item.id), order_version: orderVersion.value,
    }, true, 'PATCH')
    gifts.value = payload.gifts
    orderVersion.value = payload.order_version
  } catch (failure) {
    if (failure instanceof ApiError && failure.code === 'order_stale') {
      await loadWishlist()
      error.value = failure.code
    } else {
      error.value = failure instanceof ApiError ? failure.code : 'service_unavailable'
    }
  }
}

function exceedsBudget(gift: GiftRecord): boolean {
  if (!event.value?.budget || !gift.price || gift.currency !== event.value.currency) return false
  const toCents = (amount: string) => {
    const [units, fraction = ''] = amount.split('.')
    return BigInt(units) * 100n + BigInt(fraction.padEnd(2, '0'))
  }
  return toCents(gift.price) > toCents(event.value.budget)
}

watch([eventId, participantId], loadWishlist, { immediate: true })
</script>

<template>
  <section class="wishlist-view">
    <RouterLink
      v-if="participantView"
      class="back-link"
      :to="`/events/${eventId}`"
    >
      <ArrowLeft
        :size="18"
        aria-hidden="true"
      />{{ t('backToEvent') }}
    </RouterLink>
    <p
      v-if="loading"
      class="empty-state"
      role="status"
    >
      {{ t('loading') }}
    </p>
    <template v-else>
      <div class="view-heading">
        <div>
          <p class="eyebrow">
            {{ participantView ? event?.name : t('wishlist') }}
          </p>
          <h1 tabindex="-1">
            {{ participantView ? participant?.name : t('wishlist') }}
          </h1>
        </div>
        <button
          v-if="!participantView && !formOpen"
          class="primary-button add-gift-button"
          type="button"
          @click="beginAdd"
        >
          <Plus
            :size="18"
            aria-hidden="true"
          />{{ t('addGift') }}
        </button>
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

      <form
        v-if="formOpen"
        class="event-form gift-form"
        @submit.prevent="saveGift"
      >
        <div class="section-heading">
          <h2>{{ t(editingGiftId ? 'editGift' : 'addGift') }}</h2>
          <button
            class="icon-button"
            type="button"
            :aria-label="t('cancel')"
            :title="t('cancel')"
            @click="cancelForm"
          >
            <X
              :size="18"
              aria-hidden="true"
            />
          </button>
        </div>
        <fieldset :disabled="saving">
          <label><span>{{ t('giftName') }}</span><input
            v-model="form.name"
            name="gift_name"
            maxlength="120"
            required
          ></label>
          <label><span>{{ t('giftDescription') }}</span><textarea
            v-model="form.description"
            name="gift_description"
            maxlength="2000"
            rows="3"
          /></label>
          <div class="gift-form-grid">
            <label><span>{{ t('giftPrice') }}</span><input
              v-model="form.price"
              name="gift_price"
              type="number"
              min="0"
              max="999999.99"
              step="0.01"
            ></label>
            <label>
              <span>{{ t('giftCurrency') }}</span>
              <select
                v-model="form.currency"
                name="gift_currency"
                :disabled="!form.price"
              >
                <option value="EUR">EUR</option><option value="PLN">PLN</option>
              </select>
            </label>
          </div>
          <label><span>{{ t('giftLink') }}</span><input
            v-model="form.link"
            name="gift_link"
            type="url"
            maxlength="2048"
            placeholder="https://"
          ></label>
          <div class="form-actions">
            <button
              class="primary-button"
              type="submit"
              :disabled="saving"
            >
              <Save
                :size="18"
                aria-hidden="true"
              />{{ saving ? t('working') : t('saveGift') }}
            </button>
            <button
              class="secondary-button"
              type="button"
              @click="cancelForm"
            >
              {{ t('cancel') }}
            </button>
          </div>
        </fieldset>
      </form>

      <p
        v-if="!gifts.length"
        class="empty-state"
      >
        <span>{{ t('noGifts') }}</span>
      </p>
      <ul
        v-else
        class="wishlist-list"
      >
        <li
          v-for="(gift, index) in gifts"
          :key="gift.id"
          class="wishlist-gift"
          :class="{ 'over-budget': participantView && exceedsBudget(gift) }"
        >
          <div class="gift-details">
            <strong>{{ gift.name }}</strong>
            <p
              v-if="gift.description"
              class="gift-description"
            >
              {{ gift.description }}
            </p>
            <p class="gift-price">
              {{ gift.price === null ? t('unknownPrice') : `${gift.price} ${gift.currency}` }}
            </p>
            <p
              v-if="participantView && exceedsBudget(gift)"
              class="gift-budget-warning"
            >
              {{ t('overBudget') }}
            </p>
            <a
              v-if="gift.link"
              :href="gift.link"
              target="_blank"
              rel="noopener noreferrer"
              class="gift-link"
            >
              <ExternalLink
                :size="16"
                aria-hidden="true"
              />{{ t('openGiftLink') }}
            </a>
          </div>
          <div
            v-if="!participantView"
            class="gift-actions"
          >
            <button
              class="icon-button"
              type="button"
              :aria-label="`${t('moveGiftUp')} ${gift.name}`"
              :title="t('moveGiftUp')"
              :disabled="index === 0"
              @click="moveGift(gift, -1)"
            >
              <ArrowUp
                :size="18"
                aria-hidden="true"
              />
            </button>
            <button
              class="icon-button"
              type="button"
              :aria-label="`${t('moveGiftDown')} ${gift.name}`"
              :title="t('moveGiftDown')"
              :disabled="index === gifts.length - 1"
              @click="moveGift(gift, 1)"
            >
              <ArrowDown
                :size="18"
                aria-hidden="true"
              />
            </button>
            <button
              class="icon-button"
              type="button"
              :aria-label="`${t('editGift')} ${gift.name}`"
              :title="t('editGift')"
              @click="beginEdit(gift)"
            >
              <Pencil
                :size="18"
                aria-hidden="true"
              />
            </button>
            <button
              class="icon-button danger-button"
              type="button"
              :aria-label="`${t('deleteGift')} ${gift.name}`"
              :title="t('deleteGift')"
              @click="removeGift(gift)"
            >
              <Trash2
                :size="18"
                aria-hidden="true"
              />
            </button>
          </div>
        </li>
      </ul>
    </template>
  </section>
</template>