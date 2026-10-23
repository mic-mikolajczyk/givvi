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
  archived: boolean
  cancelled: boolean
  period: 'upcoming' | 'ongoing' | 'past'
  participants: EventParticipant[]
}

export const currentUser = ref<User | null>(null)
let csrfToken = ''
let csrfRequest: Promise<void> | undefined

export class ApiError extends Error {
  constructor(public code: string, public fields: Record<string, string> = {}, public requestId = '') {
    super(code)
  }
}

export function clearSession() {
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
): Promise<T> {
  try {
    if (body && csrfRequired) await ensureCsrf()
    const response = await fetch(`/api${path}`, {
      method: body ? method : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      signal: AbortSignal.timeout(10000),
      headers: body ? {
        'Content-Type': 'application/json',
        ...(csrfRequired ? { 'X-CSRF-Token': csrfToken } : {}),
      } : {},
      body: body ? JSON.stringify(body) : undefined,
    })
    const payload = await response.json()
    if (!response.ok) {
      if (payload.code === 'csrf_invalid' && body && retryCsrf && csrfRequired) {
        csrfToken = ''
        return await request<T>(path, body, false, method, csrfRequired)
      }
      if (payload.code === 'unauthenticated') clearSession()
      throw new ApiError(payload.code || 'internal_error', payload.field_errors || {}, payload.request_id || '')
    }
    if (payload.csrf_token) csrfToken = payload.csrf_token
    return payload as T
  } catch (error) {
    if (error instanceof ApiError) throw error
    throw new ApiError('service_unavailable')
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
