import { ref } from 'vue'

export interface User {
  id: string
  name: string
  email: string
  language: 'en' | 'pl'
  pending_email: string | null
}

export interface EventParticipant {
  id: string
  name: string
  claimed: boolean
}

export interface DrawingStatus {
  enabled: boolean
  participant_count: number
  revealed_count: number | null
  has_revealed: boolean
}

export interface GiftRecord {
  id: string
  name: string
  description: string | null
  price: string | null
  currency: 'EUR' | 'PLN' | null
  link: string | null
  position: number
}

export interface EventRecord {
  id: string
  name: string
  exchange_date: string
  exchange_time: string | null
  time_zone: string
  location: string | null
  description: string | null
  currency: 'EUR' | 'PLN'
  budget: string | null
  is_admin: boolean
  is_participant?: boolean
  drawing_enabled: boolean
  can_delete: boolean
  archived: boolean
  cancelled: boolean
  period: 'upcoming' | 'ongoing' | 'past'
  participants: EventParticipant[]
}

export const currentUser = ref<User | null>(null)
let csrfToken = ''
let csrfRequest: Promise<void> | undefined
const readCache = new Map<string, { etag: string; payload: unknown }>()
let cacheVersion = 0

function invalidateReads() {
  cacheVersion += 1
  readCache.clear()
}

export class ApiError extends Error {
  constructor(public code: string, public fields: Record<string, string> = {}, public requestId = '') {
    super(code)
  }
}

export function clearSession() {
  invalidateReads()
  currentUser.value = null
  csrfToken = ''
  csrfRequest = undefined
}

async function ensureCsrf() {
  if (csrfToken) return
  csrfRequest ??= request<{ csrf_token: string }>('/auth/csrf').then((payload) => {
    csrfToken = payload.csrf_token
  }).finally(() => { csrfRequest = undefined })
  await csrfRequest
}

export async function request<T = Record<string, unknown>>(
  path: string,
  body?: object,
  retryCsrf = true,
  method: 'POST' | 'PATCH' | 'DELETE' = 'POST',
  csrfRequired = true,
  signal?: AbortSignal,
): Promise<T> {
  const conditional = !body && /^\/events(?:\?|$|\/[^/]+(?:\/drawing|\/participants\/[^/]+\/wishlist)?$)/.test(path)
  if (body) {
    invalidateReads()
    window.dispatchEvent(new Event('givvi:mutation-start'))
  }
  const version = cacheVersion
  const cached = conditional ? readCache.get(path) : undefined
  try {
    if (body && csrfRequired) await ensureCsrf()
    const response = await fetch(`/api${path}`, {
      method: body ? method : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal: signal ? AbortSignal.any([signal, AbortSignal.timeout(10000)]) : AbortSignal.timeout(10000),
      headers: body ? {
        'Content-Type': 'application/json',
        ...(csrfRequired ? { 'X-CSRF-Token': csrfToken } : {}),
      } : (cached ? { 'If-None-Match': cached.etag } : {}),
      body: body ? JSON.stringify(body) : undefined,
    })
    if (response.status === 304 && cached && version === cacheVersion) return structuredClone(cached.payload) as T
    const payload = await response.json()
    if (!response.ok) {
      if (payload.code === 'csrf_invalid' && body && retryCsrf && csrfRequired) {
        csrfToken = ''
        return await request<T>(path, body, false, method, csrfRequired, signal)
      }
      if (payload.code === 'unauthenticated') clearSession()
      throw new ApiError(payload.code || 'internal_error', payload.field_errors || {}, payload.request_id || '')
    }
    if (payload.csrf_token) csrfToken = payload.csrf_token
    const etag = response.headers.get('ETag')
    if (conditional && etag && version === cacheVersion && !signal?.aborted) {
      if (readCache.size >= 20) readCache.delete(readCache.keys().next().value!)
      readCache.set(path, { etag, payload: structuredClone(payload) })
    }
    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('service_unavailable')
  } finally {
    if (body) {
      invalidateReads()
      window.dispatchEvent(new Event('givvi:mutation'))
    }
  }
}

export function publicRequest<T = Record<string, unknown>>(path: string, body: object): Promise<T> {
  return request<T>(path, body, false, 'POST', false)
}

export async function refreshUser() {
  const payload = await request<{ user: User }>('/auth/me')
  currentUser.value = payload.user
  return payload.user
}

export function safeReturnTo(value: unknown): string {
  if (typeof value !== 'string') return '/events'
  try {
    const decoded = decodeURIComponent(value)
    const unsafeCharacters = decoded.includes('\\') || Array.from(decoded).some((character) => character.charCodeAt(0) < 32)
    if (!decoded.startsWith('/') || decoded.startsWith('//') || unsafeCharacters) return '/events'
    const parsed = new URL(decoded, 'https://givvi.invalid')
    return parsed.origin === 'https://givvi.invalid' ? parsed.pathname + parsed.search + parsed.hash : '/events'
  } catch {
    return '/events'
  }
}
