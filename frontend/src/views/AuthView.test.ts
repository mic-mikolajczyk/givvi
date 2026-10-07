import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createI18n } from 'vue-i18n'
import { createMemoryHistory, createRouter } from 'vue-router'

import { clearSession } from '../api'
import { messages } from '../i18n'
import AuthView from './AuthView.vue'

describe('registration page', () => {
  it('submits registration and displays the generic inbox response', async () => {
    clearSession()
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'csrf' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'check_email' }), { status: 202 }))
    vi.stubGlobal('fetch', fetch)
    const router = createRouter({ history: createMemoryHistory(), routes: [{ path: '/register', name: 'register', component: AuthView }] })
    await router.push('/register')
    await router.isReady()
    const wrapper = mount(AuthView, { global: { plugins: [router, createI18n({ legacy: false, locale: 'en', messages })] } })
    await wrapper.get('input[name="name"]').setValue('Alice')
    await wrapper.get('input[name="email"]').setValue('alice@example.com')
    await wrapper.get('input[name="password"]').setValue('correct horse battery staple')

    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[role="status"]').text()).toContain('Check your inbox')
    expect(JSON.parse(fetch.mock.calls[1][1].body).language).toBe('en')
    wrapper.unmount()
  })
})
