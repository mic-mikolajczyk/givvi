import { beforeEach, describe, expect, it, vi } from 'vitest'

import { ApiError, clearSession, publicRequest, request, safeReturnTo } from './api'

beforeEach(() => clearSession())

describe('account API client', () => {
  it('obtains CSRF and sends it only to the same-origin API', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'test-csrf' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ user: { email: 'alice@example.com' }, csrf_token: 'new-csrf' }), { status: 201 }))
    vi.stubGlobal('fetch', fetch)

    await request('/auth/register', { email: 'alice@example.com' })

    expect(fetch.mock.calls[1][0]).toBe('/api/auth/register')
    expect(fetch.mock.calls[1][1].headers['X-CSRF-Token']).toBe('test-csrf')
    expect(fetch.mock.calls[1][1].credentials).toBe('same-origin')
  })

  it('returns safe domain errors rather than private exception text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('private connection detail')))

    await expect(request('/auth/me')).rejects.toEqual(expect.objectContaining({ code: 'service_unavailable' }))
  })

  it('preserves API validation field errors', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({
      code: 'validation_error', field_errors: { email: 'invalid_email' },
    }), { status: 422 })))

    try {
      await request('/auth/me')
      throw new Error('Expected failure')
    } catch (error) {
      expect(error).toBeInstanceOf(ApiError)
      expect((error as ApiError).fields.email).toBe('invalid_email')
    }
  })

  it('sends invite previews without obtaining or attaching a CSRF token', async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(JSON.stringify({ invitation: { participants: [] } })))
    vi.stubGlobal('fetch', fetch)

    await publicRequest('/events/event-1/invitation-preview', { token: 'invite-secret' })

    expect(fetch).toHaveBeenCalledOnce()
    expect(fetch.mock.calls[0][1].headers).toEqual({ 'Content-Type': 'application/json' })
    expect(fetch.mock.calls[0][1].body).toBe(JSON.stringify({ token: 'invite-secret' }))
  })

  it('revalidates event reads and invalidates them after a mutation', async () => {
    const fetch = vi.fn()
      .mockResolvedValueOnce(new Response(JSON.stringify({ event: { name: 'Before' } }), { headers: { ETag: '"v1"' } }))
      .mockResolvedValueOnce(new Response(null, { status: 304 }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ csrf_token: 'csrf' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ code: 'saved' })))
      .mockResolvedValueOnce(new Response(JSON.stringify({ event: { name: 'After' } })))
    vi.stubGlobal('fetch', fetch)

    await request('/events/event-1')
    expect(await request('/events/event-1')).toEqual({ event: { name: 'Before' } })
    expect(fetch.mock.calls[1][1].headers['If-None-Match']).toBe('"v1"')
    await request('/events/event-1', { name: 'After' }, true, 'PATCH')
    expect(await request('/events/event-1')).toEqual({ event: { name: 'After' } })
    expect(fetch.mock.calls[4][1].headers['If-None-Match']).toBeUndefined()
  })

  it('does not revalidate secret-bearing responses or retain caches across sessions', async () => {
    const fetch = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify({ link: 'secret' }), {
      headers: { ETag: '"private"' },
    })))
    vi.stubGlobal('fetch', fetch)

    await request('/events/event-1/invite-link')
    await request('/events/event-1/invite-link')
    expect(fetch.mock.calls[1][1].headers['If-None-Match']).toBeUndefined()
    await request('/events/event-1')
    clearSession()
    await request('/events/event-1')
    expect(fetch.mock.calls[3][1].headers['If-None-Match']).toBeUndefined()
  })
})

describe('return navigation', () => {
  it.each(['https://evil.example', '//evil.example', '/\\evil.example', '%2f%2fevil.example', '/%2f/evil.example'])('rejects %s', (path) => {
    expect(safeReturnTo(path)).toBe('/events')
  })

  it('keeps an internal invitation destination', () => {
    expect(safeReturnTo('/invite/event?entry=alice')).toBe('/invite/event?entry=alice')
  })
})
