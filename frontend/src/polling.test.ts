import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'

import { usePolling } from './polling'

beforeEach(() => {
  vi.useFakeTimers()
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
})
afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
})

it('pauses while hidden, refreshes on visibility and mutations, and stops on unmount', async () => {
  const load = vi.fn().mockResolvedValue(undefined)
  const wrapper = mount(defineComponent({ setup() { usePolling(() => 'event-1', load); return () => null } }))
  await flushPromises()
  expect(load).toHaveBeenCalledTimes(1)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(true)
  document.dispatchEvent(new Event('visibilitychange'))
  await vi.advanceTimersByTimeAsync(60000)
  expect(load).toHaveBeenCalledTimes(1)
  vi.spyOn(document, 'hidden', 'get').mockReturnValue(false)
  document.dispatchEvent(new Event('visibilitychange'))
  await flushPromises()
  expect(load).toHaveBeenCalledTimes(2)
  window.dispatchEvent(new Event('givvi:mutation'))
  await flushPromises()
  expect(load).toHaveBeenCalledTimes(3)
  wrapper.unmount()
  await vi.advanceTimersByTimeAsync(60000)
  expect(load).toHaveBeenCalledTimes(3)
})

it('aborts obsolete requests and rejects stale results after a route change', async () => {
  const key = ref('first')
  const pending: { signal: AbortSignal; current: () => boolean; finish: () => void }[] = []
  const load = vi.fn((signal: AbortSignal, current: () => boolean) => new Promise<void>((finish) => {
    pending.push({ signal, current, finish })
  }))
  const wrapper = mount(defineComponent({ setup() { usePolling(() => key.value, load); return () => null } }))
  key.value = 'second'
  await flushPromises()
  expect(pending[0]!.signal.aborted).toBe(true)
  expect(pending[0]!.current()).toBe(false)
  expect(pending[1]!.current()).toBe(true)
  pending[0]!.finish()
  pending[1]!.finish()
  await flushPromises()
  wrapper.unmount()
})

it('backs off after failed reads and resets after recovery', async () => {
  const load = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValue(undefined)
  const onError = vi.fn()
  const wrapper = mount(defineComponent({
    setup() { usePolling(() => 'event-1', load, { onError }); return () => null },
  }))
  await flushPromises()
  expect(onError).toHaveBeenCalledOnce()
  await vi.advanceTimersByTimeAsync(15000)
  expect(load).toHaveBeenCalledTimes(1)
  await vi.advanceTimersByTimeAsync(15000)
  expect(load).toHaveBeenCalledTimes(2)
  await vi.advanceTimersByTimeAsync(15000)
  expect(load).toHaveBeenCalledTimes(3)
  wrapper.unmount()
})