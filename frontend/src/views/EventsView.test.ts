import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { messages } from '../i18n'
import EventsView from './EventsView.vue'
import EventDetailView from './EventDetailView.vue'
import ProfileView from './ProfileView.vue'

const { ApiError, clearSession, currentUser, publicRequest, refreshUser, request } = vi.hoisted(() => ({
  request: vi.fn(),
  publicRequest: vi.fn(),
  refreshUser: vi.fn(),
  clearSession: vi.fn(),
  currentUser: {
    __v_isRef: true,
    value: null as null | { id: string; name: string; email: string; language: 'en' | 'pl'; pending_email: null },
  },
  ApiError: class extends Error {
    code: string
    constructor(code: string) {
      super(code)
      this.code = code
    }
  },
}))
vi.mock('../api', () => ({ request, publicRequest, refreshUser, clearSession, currentUser, ApiError }))

const event = {
  id: 'event-1', name: 'Winter exchange', exchange_date: '2026-12-20', exchange_time: null,
  time_zone: 'Europe/Warsaw', location: null, description: null, currency: 'EUR', budget: null,
  is_admin: true, drawing_enabled: false, can_delete: true, archived: false, cancelled: false, period: 'upcoming',
  participants: [],
}

describe('event management views', () => {
  beforeEach(() => {
    request.mockReset()
    publicRequest.mockReset()
    refreshUser.mockReset()
    currentUser.value = null
    event.archived = false
    event.cancelled = false
    event.drawing_enabled = false
    event.participants.splice(0)
    sessionStorage.clear()
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

  it('links claimed participant rows to their event-scoped wishlist', async () => {
    const memberEvent = {
      ...event,
      is_admin: false,
      is_participant: true,
      participants: [{ id: 'participant-1', name: 'Morgan', claimed: true }],
    }
    request.mockImplementation((path: string) => {
      if (path === '/events/event-1') return Promise.resolve({ event: memberEvent })
      if (path === '/events/event-1/invite-link') return Promise.reject(new ApiError('not_found'))
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

    expect(wrapper.get('a[href="/events/event-1/participants/participant-1/wishlist"]').attributes('aria-label'))
      .toBe('View wishlist Morgan')
    wrapper.unmount()
  })

  it('lets the admin enable drawing with unclaimed roster entries', async () => {
    const readyEvent = {
      ...event,
      participants: [
        { id: 'participant-1', name: 'Morgan', claimed: true },
        { id: 'participant-2', name: 'Riley', claimed: true },
        { id: 'participant-3', name: 'Taylor', claimed: false },
      ],
    }
    request.mockImplementation((path: string) => {
      if (path === '/events/event-1') return Promise.resolve({ event: readyEvent })
      if (path === '/events/event-1/invite-link') return Promise.reject(new ApiError('not_found'))
      if (path === '/events/event-1/drawing') {
        return Promise.resolve({ drawing: { enabled: true, participant_count: 3, revealed_count: 0, has_revealed: false } })
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

    expect(wrapper.get('button[aria-label="Enable drawing"]').attributes('disabled')).toBeUndefined()
    await wrapper.get('button[aria-label="Enable drawing"]').trigger('click')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events/event-1/drawing', {})
    expect(wrapper.text()).toContain('Drawing enabled')
    expect(wrapper.find('button[aria-label="Delete event"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('lets the admin reset after a reveal and returns to roster setup', async () => {
    const revealedEvent = {
      ...event,
      drawing_enabled: true,
      can_delete: false,
      participants: [
        { id: 'participant-1', name: 'Morgan', claimed: true },
        { id: 'participant-2', name: 'Riley', claimed: true },
        { id: 'participant-3', name: 'Taylor', claimed: false },
      ],
    }
    request.mockImplementation((path: string, ...args: unknown[]) => {
      if (path === '/events/event-1') return Promise.resolve({ event: revealedEvent })
      if (path === '/events/event-1/invite-link') return Promise.reject(new ApiError('not_found'))
      if (path === '/events/event-1/drawing' && args[2] === 'DELETE') {
        return Promise.resolve({ drawing: { enabled: false, participant_count: 3, revealed_count: 0, has_revealed: false } })
      }
      if (path === '/events/event-1/drawing') {
        return Promise.resolve({ drawing: { enabled: true, participant_count: 3, revealed_count: 1, has_revealed: false } })
      }
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
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

    expect(wrapper.find('button[aria-label="Reset drawing"]').exists()).toBe(true)
    expect(wrapper.get('.drawing-reset-warning').text()).toContain('may already know their old recipient')
    await wrapper.get('button[aria-label="Reset drawing"]').trigger('click')
    await flushPromises()

    expect(confirm).toHaveBeenCalledWith(expect.stringContaining('including revealed ones'))
    expect(request).toHaveBeenCalledWith('/events/event-1/drawing', {}, true, 'DELETE')
    expect(wrapper.find('input[name="participant_name"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Enable drawing"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Delete event"]').exists()).toBe(true)
    wrapper.unmount()
  })

  it('reveals only the signed-in participant recipient on demand', async () => {
    const drawnEvent = {
      ...event,
      is_admin: false,
      is_participant: true,
      drawing_enabled: true,
      participants: [
        { id: 'participant-1', name: 'Morgan', claimed: true },
        { id: 'participant-2', name: 'Riley', claimed: true },
        { id: 'participant-3', name: 'Taylor', claimed: true },
      ],
    }
    request.mockImplementation((path: string) => {
      if (path === '/events/event-1') return Promise.resolve({ event: drawnEvent })
      if (path === '/events/event-1/drawing') {
        return Promise.resolve({ drawing: { enabled: true, participant_count: 3, revealed_count: 0, has_revealed: false } })
      }
      if (path === '/events/event-1/reveal') return Promise.resolve({ recipient: { id: 'participant-2', name: 'Riley' } })
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

    await wrapper.get('button[aria-label="Reveal your recipient"]').trigger('click')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events/event-1/reveal', {})
    expect(wrapper.text()).toContain('Riley')
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

    expect(request).toHaveBeenCalledWith('/events?page=2&page_size=50', undefined, true, 'POST', true, expect.any(AbortSignal))
    expect(wrapper.text()).toContain('Second exchange')
    expect(wrapper.get('[aria-label="Event pages"]').text()).toContain('2 / 2')
    wrapper.unmount()
  })

  it('shows only roster availability and preserves the invite token for sign-in', async () => {
    const { default: InvitationView } = await import('./InvitationView.vue')
    refreshUser.mockRejectedValue(new ApiError('unauthenticated'))
    publicRequest.mockResolvedValue({ invitation: {
      event_id: 'event-1', participants: [
        { id: 'participant-1', name: 'Morgan', available: true },
        { id: 'participant-2', name: 'Riley', available: false },
      ],
    } })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/invite/:eventId', component: InvitationView },
      { path: '/login', component: { template: '<div />' } },
      { path: '/register', component: { template: '<div />' } },
    ] })
    await router.push('/invite/event-1#token=fragment-secret')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    expect(sessionStorage.getItem('givvi-invite-event-1')).toBe('fragment-secret')
    expect(publicRequest).toHaveBeenCalledWith('/events/event-1/invitation-preview', { token: 'fragment-secret' })
    expect(wrapper.text()).toContain('Morgan')
    expect(wrapper.text()).toContain('Unavailable')
    expect(wrapper.text()).not.toContain('Winter exchange')
    expect(wrapper.find('button.primary-button').exists()).toBe(false)
    await wrapper.get('a[href="/login?next=/invite/event-1"]').trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.path).toBe('/login')
    wrapper.unmount()
  })

  it('claims an available roster name and enters the authorized event view', async () => {
    const { default: InvitationView } = await import('./InvitationView.vue')
    currentUser.value = {
      id: 'user-1', name: 'Morgan', email: 'morgan@example.com', language: 'en', pending_email: null,
    }
    refreshUser.mockResolvedValue(currentUser.value)
    publicRequest.mockResolvedValue({ invitation: {
      event_id: 'event-1', participants: [{ id: 'participant-1', name: 'Morgan', available: true }],
    } })
    request.mockResolvedValue({ code: 'claim_completed' })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/invite/:eventId', component: InvitationView },
      { path: '/events/:eventId', component: { template: '<div />' } },
    ] })
    await router.push('/invite/event-1#token=fragment-secret')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events/event-1/claim', {
      participant_id: 'participant-1', token: 'fragment-secret',
    })
    expect(sessionStorage.getItem('givvi-invite-event-1')).toBeNull()
    expect(router.currentRoute.value.path).toBe('/events/event-1')
    wrapper.unmount()
  })

  it('refreshes available names after another user wins the claim race', async () => {
    const { default: InvitationView } = await import('./InvitationView.vue')
    currentUser.value = {
      id: 'user-1', name: 'Morgan', email: 'morgan@example.com', language: 'en', pending_email: null,
    }
    refreshUser.mockResolvedValue(currentUser.value)
    publicRequest
      .mockResolvedValueOnce({ invitation: {
        event_id: 'event-1', participants: [{ id: 'participant-1', name: 'Morgan', available: true }],
      } })
      .mockResolvedValueOnce({ invitation: {
        event_id: 'event-1', participants: [{ id: 'participant-1', name: 'Morgan', available: false }],
      } })
    request.mockRejectedValue(new ApiError('entry_unavailable'))
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/invite/:eventId', component: InvitationView },
      { path: '/events/:eventId', component: { template: '<div />' } },
    ] })
    await router.push('/invite/event-1#token=fragment-secret')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('button.primary-button').trigger('click')
    await flushPromises()

    expect(publicRequest).toHaveBeenCalledTimes(2)
    expect(wrapper.find('button.primary-button').exists()).toBe(false)
    expect(wrapper.text()).toContain('Unavailable')
    expect(wrapper.text()).toContain('That roster entry was just claimed.')
    wrapper.unmount()
  })

  it('lets the admin send invitations, share the link, and release a mistaken claim', async () => {
    const claimedEvent = {
      ...event,
      participants: [{ id: 'participant-1', name: 'Morgan', claimed: true }],
    }
    const activeLink = 'http://givvi.test/invite/event-1#token=secret'
    request.mockImplementation((path: string, body?: object, _retryCsrf?: boolean, method?: string) => {
      if (path === '/events/event-1' && !body) return Promise.resolve({ event: claimedEvent })
      if (path === '/events/event-1/invite-link' && !body) return Promise.resolve({ link: activeLink })
      if (path === '/events/event-1/invitations') return Promise.resolve({ code: 'invitation_queued' })
      if (path.endsWith('/participants/participant-1/claim') && method === 'DELETE') {
        return Promise.resolve({ code: 'claim_released' })
      }
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/events', component: { template: '<div />' } },
      { path: '/events/:eventId', component: EventDetailView },
    ] })
    await router.push('/events/event-1')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    expect((wrapper.get('input[readonly]').element as HTMLInputElement).value).toBe(activeLink)
    await wrapper.get('input[name="invite_email"]').setValue('guest@example.com')
    await wrapper.get('form.invitation-email-form').trigger('submit')
    await flushPromises()
    await wrapper.get('button[aria-label="Release mistaken claim Morgan"]').trigger('click')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/events/event-1/invitations', { email: 'guest@example.com' })
    expect(request).toHaveBeenCalledWith('/events/event-1/participants/participant-1/claim', {}, true, 'DELETE')
    expect(wrapper.text()).toContain('Not claimed')
    wrapper.unmount()
  })

  it('allows a participant to retrieve the active share link without admin controls', async () => {
    const memberEvent = { ...event, is_admin: false }
    request.mockImplementation((path: string) => {
      if (path === '/events/event-1') return Promise.resolve({ event: memberEvent })
      if (path === '/events/event-1/invite-link') return Promise.resolve({ link: 'active-link' })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/', component: { template: '<div />' } },
      { path: '/events', component: { template: '<div />' } },
      { path: '/events/:eventId', component: EventDetailView },
    ] })
    await router.push('/events/event-1')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    expect((wrapper.get('input[readonly]').element as HTMLInputElement).value).toBe('active-link')
    expect(wrapper.find('form.invitation-email-form').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="Revoke link"]').exists()).toBe(false)
    wrapper.unmount()
  })

  it('archives, restores, and cancels an event through lifecycle controls', async () => {
    const archived = { ...event, archived: true }
    const cancelled = { ...event, cancelled: true }
    request.mockImplementation((path: string, _body?: object, _retry?: boolean, method?: string) => {
      if (path === '/events/event-1' && !_body) return Promise.resolve({ event })
      if (path === '/events/event-1/invite-link') return Promise.reject(new ApiError('not_found'))
      if (path === '/events/event-1/archive' && method === 'POST') return Promise.resolve({ event: archived })
      if (path === '/events/event-1/archive' && method === 'DELETE') return Promise.resolve({ event })
      if (path === '/events/event-1/cancel') return Promise.resolve({ event: cancelled })
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
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
    await wrapper.get('button[aria-label="Archive event"]').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Archived')
    expect(wrapper.find('form.detail-form').exists()).toBe(false)
    await wrapper.get('button[aria-label="Unarchive event"]').trigger('click')
    await flushPromises()

    await wrapper.get('button[aria-label="Cancel event"]').trigger('click')
    await flushPromises()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('Cancelled')
    expect(request).toHaveBeenCalledWith('/events/event-1/cancel', {}, true, 'POST')
    wrapper.unmount()
  })

  it('deletes the account only after confirmation and reauthentication', async () => {
    request.mockResolvedValue({ code: 'account_deleted' })
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/profile', component: ProfileView },
      { path: '/login', component: { template: '<div />' } },
    ] })
    await router.push('/profile')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    await wrapper.get('input[name="deletion-password"]').setValue('correct horse battery staple')
    await wrapper.get('.danger-zone form').trigger('submit')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/auth/account', {
      current_password: 'correct horse battery staple',
    }, true, 'DELETE')
    expect(clearSession).toHaveBeenCalledOnce()
    expect(router.currentRoute.value.path).toBe('/login')
    wrapper.unmount()
  })

  it('keeps creator management controls without offering administration transfer', async () => {
    const eventWithMember = {
      ...event,
      participants: [{ id: 'participant-1', name: 'Morgan', claimed: true }],
    }
    request.mockImplementation((path: string) => {
      if (path === '/events/event-1') return Promise.resolve({ event: eventWithMember })
      if (path === '/events/event-1/invite-link') return Promise.reject(new ApiError('not_found'))
      return Promise.reject(new Error(`Unexpected request: ${path}`))
    })
    const router = createRouter({ history: createMemoryHistory(), routes: [
      { path: '/events', component: EventsView },
      { path: '/events/:eventId', component: EventDetailView },
    ] })
    await router.push('/events/event-1')
    await router.isReady()
    const wrapper = mount({ template: '<RouterView />' }, {
      global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] },
    })
    await flushPromises()

    expect(wrapper.find('form.admin-transfer-form').exists()).toBe(false)
    expect(wrapper.find(`#transfer-target-${event.id}`).exists()).toBe(false)
    expect(wrapper.find('button[aria-label="Archive event"]').exists()).toBe(true)
    expect(wrapper.find('button[aria-label="Cancel event"]').exists()).toBe(true)
    expect(router.currentRoute.value.path).toBe('/events/event-1')
    wrapper.unmount()
  })
})
