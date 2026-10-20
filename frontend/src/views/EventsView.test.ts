import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { messages } from '../i18n'
import EventsView from './EventsView.vue'
import EventDetailView from './EventDetailView.vue'

const { ApiError, request } = vi.hoisted(() => ({
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

const event = {
  id: 'event-1', name: 'Winter exchange', exchange_date: '2026-12-20', exchange_time: null,
  time_zone: 'Europe/Warsaw', location: null, description: null, currency: 'EUR', budget: null,
  is_admin: true, drawing_enabled: false, archived: false, cancelled: false, period: 'upcoming',
  participants: [],
}

describe('event management views', () => {
  beforeEach(() => {
    request.mockReset()
  })

  it('creates an event and opens its detail view', async () => {
    request.mockImplementation((path: string, body?: object) => {
      if (path === '/events?page=1&page_size=50' && !body) {
        return Promise.resolve({ events: [], page: 1, page_size: 50, total: 0 })
      }
      if (path === '/events' && body) return Promise.resolve({ event })
      if (path === '/events/event-1') return Promise.resolve({ event })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/events', component: EventsView },
        { path: '/events/:eventId', component: EventDetailView },
      ],
    })
    await router.push('/events')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('button').trigger('click')
    await wrapper.get('input[name="name"]').setValue('Winter exchange')
    await wrapper.get('input[name="exchange_date"]').setValue('2026-12-20')
    await wrapper.get('input[name="time_zone"]').setValue('Europe/Warsaw')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events', expect.objectContaining({
      name: 'Winter exchange', exchange_date: '2026-12-20', time_zone: 'Europe/Warsaw',
    }))
    expect(router.currentRoute.value.path).toBe('/events/event-1')
    expect(wrapper.text()).toContain('Winter exchange')
    wrapper.unmount()
  })

  it('adds a roster entry without claiming it', async () => {
    request.mockImplementation((path: string, body?: object) => {
      if (path === '/events/event-1' && !body) return Promise.resolve({ event })
      if (path === '/events/event-1/participants') {
        return Promise.resolve({ participant: { id: 'participant-1', name: 'Morgan', claimed: false } })
      }
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/events', component: { template: '<div />' } },
      { path: '/events/:eventId', component: EventDetailView },
    ] })
    await router.push('/events/event-1')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('input[name="participant_name"]').setValue('Morgan')
    await wrapper.get('form.roster-add-form').trigger('submit')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events/event-1/participants', { name: 'Morgan' })
    expect(wrapper.text()).toContain('Morgan')
    expect(wrapper.text()).toContain('Not claimed')
    wrapper.unmount()
  })

  it('shows event details read-only until the admin chooses to edit', async () => {
    const updated = { ...event, name: 'Renamed exchange' }
    request.mockImplementation((path: string, body?: object) => {
      if (path === '/events/event-1' && !body) return Promise.resolve({ event })
      if (path === '/events/event-1' && body) return Promise.resolve({ event: updated })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/events', component: { template: '<div />' } },
      { path: '/events/:eventId', component: EventDetailView },
    ] })
    await router.push('/events/event-1')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    expect(wrapper.find('input[name="name"]').exists()).toBe(false)
    await wrapper.get('button.edit-event-button').trigger('click')
    await wrapper.get('input[name="name"]').setValue('Renamed exchange')
    await wrapper.get('form.detail-form').trigger('submit')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events/event-1', expect.objectContaining({ name: 'Renamed exchange' }), true, 'PATCH')
    expect(wrapper.find('input[name="name"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Renamed exchange')
    wrapper.unmount()
  })

  it('discards unsaved detail changes on cancel', async () => {
    request.mockImplementation((path: string, body?: object) => {
      if (path === '/events/event-1' && !body) return Promise.resolve({ event })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/events', component: { template: '<div />' } },
      { path: '/events/:eventId', component: EventDetailView },
    ] })
    await router.push('/events/event-1')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('button.edit-event-button').trigger('click')
    await wrapper.get('input[name="name"]').setValue('Unsaved name')
    await wrapper.get('button.cancel-edit-button').trigger('click')
    await wrapper.get('button.edit-event-button').trigger('click')

    expect((wrapper.get('input[name="name"]').element as HTMLInputElement).value).toBe('Winter exchange')
    wrapper.unmount()
  })

  it('loads the next page of events when requested', async () => {
    request.mockImplementation((path: string) => {
      if (path === '/events?page=1&page_size=50') {
        return Promise.resolve({ events: [event], page: 1, page_size: 50, total: 51 })
      }
      if (path === '/events?page=2&page_size=50') {
        return Promise.resolve({ events: [{ ...event, id: 'event-2', name: 'Second exchange' }], page: 2, page_size: 50, total: 51 })
      }
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/events', component: EventsView },
    ] })
    await router.push('/events')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('button[aria-label="Next page"]').trigger('click')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events?page=2&page_size=50')
    expect(wrapper.text()).toContain('Second exchange')
    expect(wrapper.get('[aria-label="Event pages"]').text()).toContain('2 / 2')
    wrapper.unmount()
  })
})
