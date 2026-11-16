import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'

import { messages } from '../i18n'
import StatusView from './StatusView.vue'

function renderStatus(locale = 'en') {
  return mount(StatusView, {
    global: { plugins: [createI18n({ legacy: false, locale, fallbackLocale: 'en', messages })] },
  })
}

afterEach(() => vi.unstubAllGlobals())

describe('service status', () => {
  it('checks readiness and displays a successful result', async () => {
    const request = vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ready' })))
    vi.stubGlobal('fetch', request)
    const wrapper = renderStatus()

    expect(wrapper.get('[role="status"]').text()).toContain('Checking')
    await flushPromises()

    expect(request).toHaveBeenCalledWith('/api/health/ready', expect.any(Object))
    expect(wrapper.get('[role="status"]').text()).toContain('Connected')
    wrapper.unmount()
  })

  it('shows database unavailability and permits retry', async () => {
    vi.stubGlobal('fetch', vi.fn()
      .mockResolvedValueOnce(new Response('{}', { status: 503 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ status: 'ready' }))))
    const wrapper = renderStatus()
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('Unavailable')

    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('Connected')
    wrapper.unmount()
  })

  it('handles a network failure without exposing details', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private connection detail')))
    const wrapper = renderStatus()
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('Unavailable')
    expect(wrapper.text()).not.toContain('private connection detail')
    wrapper.unmount()
  })

  it('rejects an unexpected readiness response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'unknown' }))))
    const wrapper = renderStatus()
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('Unavailable')
    wrapper.unmount()
  })

  it('supports Polish and language switching', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ status: 'ready' }))))
    const wrapper = renderStatus('pl')
    await flushPromises()
    expect(wrapper.get('[role="status"]').text()).toContain('Połączono')

    await wrapper.get('select').setValue('en')

    expect(wrapper.get('[role="status"]').text()).toContain('Connected')
    wrapper.unmount()
  })
})
