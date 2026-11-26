import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { messages } from '../i18n'
import WishlistView from './WishlistView.vue'

const { request, ApiError } = vi.hoisted(() => ({
  request: vi.fn(),
  ApiError: class extends Error {
    code: string
    constructor(code: string) {
      super(code)
      this.code = code
    }
  },
}))
vi.mock('../api', () => ({ request, ApiError }))

async function mountWishlist(path = '/wishlist', i18n = createI18n({ legacy: false, locale: 'en', messages })) {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/wishlist', component: WishlistView },
      { path: '/events/:eventId/participants/:participantId/wishlist', component: WishlistView },
      { path: '/events/:eventId', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount({ template: '<RouterView />' }, {
    global: { plugins: [router, i18n] },
  })
  await flushPromises()
  return wrapper
}

describe('wishlist views', () => {
  beforeEach(() => {
    request.mockReset()
  })

  it('adds an owner gift and displays unknown prices explicitly', async () => {
    request.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/wishlist' && !body) return Promise.resolve({ gifts: [], order_version: 0 })
      if (path === '/wishlist/gifts') return Promise.resolve({
        gift: {
          id: 'gift-1', name: 'A book', description: null, price: null, currency: null, link: null, position: 0,
        },
        order_version: 1,
      })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const wrapper = await mountWishlist()

    await wrapper.get('button.add-gift-button').trigger('click')
    await wrapper.get('input[name="gift_name"]').setValue('A book')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/wishlist/gifts', expect.objectContaining({
      name: 'A book', price: null, currency: null,
    }))
    expect(request.mock.calls.map(([path]) => path)).toEqual(['/wishlist', '/wishlist/gifts'])
    expect(wrapper.text()).toContain('A book')
    expect(wrapper.text()).toContain('Price unknown')
    wrapper.unmount()
  })

  it.each([
    ['en', 'EUR'],
    ['pl', 'PLN'],
  ])('defaults new gifts to the %s language currency', async (locale, currency) => {
    request.mockImplementation((path: string) => {
      if (path === '/wishlist') return Promise.resolve({ gifts: [], order_version: 0 })
      if (path === '/wishlist/gifts') return Promise.resolve({
        gift: { id: 'gift-1', name: 'Book', description: null, price: '10', currency, link: null, position: 0 },
        order_version: 1,
      })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const i18n = createI18n({ legacy: false, locale, messages })
    const wrapper = await mountWishlist('/wishlist', i18n)

    await wrapper.get('button.add-gift-button').trigger('click')
    await wrapper.get('input[name="gift_name"]').setValue('Book')
    await wrapper.get('input[name="gift_price"]').setValue('10')
    expect((wrapper.get('select[name="gift_currency"]').element as HTMLSelectElement).value).toBe(currency)
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/wishlist/gifts', expect.objectContaining({ price: 10, currency }))
    wrapper.unmount()
  })

  it('updates the default when language changes without overriding a chosen currency', async () => {
    request.mockResolvedValue({ gifts: [], order_version: 0 })
    const i18n = createI18n({ legacy: false, locale: 'en', messages })
    const wrapper = await mountWishlist('/wishlist', i18n)

    await wrapper.get('button.add-gift-button').trigger('click')
    await wrapper.get('input[name="gift_price"]').setValue('10')
    i18n.global.locale.value = 'pl'
    await flushPromises()
    const select = wrapper.get('select[name="gift_currency"]')
    expect((select.element as HTMLSelectElement).value).toBe('PLN')
    await select.setValue('EUR')
    i18n.global.locale.value = 'en'
    await flushPromises()
    i18n.global.locale.value = 'pl'
    await flushPromises()
    expect((select.element as HTMLSelectElement).value).toBe('EUR')
    await wrapper.get('button.secondary-button').trigger('click')
    await wrapper.get('button.add-gift-button').trigger('click')
    expect((wrapper.get('select[name="gift_currency"]').element as HTMLSelectElement).value).toBe('PLN')
    wrapper.unmount()
  })

  it('preserves the saved currency when editing a gift', async () => {
    request.mockResolvedValue({
      gifts: [{ id: 'gift-1', name: 'Book', description: null, price: '10.00', currency: 'EUR', link: null, position: 0 }],
      order_version: 0,
    })
    const i18n = createI18n({ legacy: false, locale: 'pl', messages })
    const wrapper = await mountWishlist('/wishlist', i18n)

    await wrapper.get('button[aria-label^="Edytuj prezent"]').trigger('click')
    i18n.global.locale.value = 'en'
    await flushPromises()
    i18n.global.locale.value = 'pl'
    await flushPromises()
    expect((wrapper.get('select[name="gift_currency"]').element as HTMLSelectElement).value).toBe('EUR')
    wrapper.unmount()
  })

  it('moves gifts through a versioned owner reorder request', async () => {
    const gifts = [
      { id: 'gift-1', name: 'First', description: null, price: '10.00', currency: 'EUR', link: null, position: 0 },
      { id: 'gift-2', name: 'Second', description: null, price: null, currency: null, link: null, position: 1 },
    ]
    request.mockImplementation((path: string, body?: Record<string, unknown>) => {
      if (path === '/wishlist' && !body) return Promise.resolve({ gifts, order_version: 2 })
      if (path === '/wishlist/order') return Promise.resolve({
        gifts: [gifts[1], { ...gifts[0], position: 1 }], order_version: 3,
      })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const wrapper = await mountWishlist()

    await wrapper.get('button[aria-label="Move up Second"]').trigger('click')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/wishlist/order', {
      gift_ids: ['gift-2', 'gift-1'], order_version: 2,
    }, true, 'PATCH')
    expect(request.mock.calls.map(([path]) => path)).toEqual(['/wishlist', '/wishlist/order'])
    expect(wrapper.findAll('.wishlist-gift strong').map((element) => element.text())).toEqual(['Second', 'First'])
    wrapper.unmount()
  })

  it('shows another participant wishlist read-only and highlights only matching over-budget prices', async () => {
    request.mockResolvedValue({
      event: { id: 'event-1', name: 'Winter exchange', budget: '30.00', currency: 'EUR' },
      participant: { id: 'participant-1', name: 'Morgan' },
      gifts: [
        { id: 'gift-1', name: 'Over budget', description: '<img src=x onerror=alert(1)>', price: '45.00', currency: 'EUR', link: null, position: 0 },
        { id: 'gift-2', name: 'Other currency', description: null, price: '50.00', currency: 'PLN', link: null, position: 1 },
        { id: 'gift-3', name: 'Exactly at budget', description: null, price: '30.00', currency: 'EUR', link: null, position: 2 },
        { id: 'gift-4', name: 'Unknown price', description: null, price: null, currency: null, link: null, position: 3 },
      ],
    })
    const wrapper = await mountWishlist('/events/event-1/participants/participant-1/wishlist')

    expect(request).toHaveBeenCalledWith(
      '/events/event-1/participants/participant-1/wishlist', undefined, true, 'POST', true, expect.any(AbortSignal),
    )
    expect(wrapper.text()).toContain('Morgan')
    expect(wrapper.text()).toContain('Winter exchange')
    expect(wrapper.text()).toContain('<img src=x onerror=alert(1)>')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.findAll('.over-budget')).toHaveLength(1)
    expect(wrapper.find('button.add-gift-button').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="Move up Second"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label^="Edit gift"]').exists()).toBe(false)
    expect(wrapper.find('button[aria-label^="Delete gift"]').exists()).toBe(false)
    expect(wrapper.text()).not.toMatch(/reserved|purchased|reservation/i)
    expect(wrapper.find('a[href="/events/event-1"]').exists()).toBe(true)
    wrapper.unmount()
  })
})