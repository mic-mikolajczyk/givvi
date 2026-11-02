import { onScopeDispose, watch } from 'vue'

const POLL_INTERVAL_MS = 15000
const MAX_BACKOFF_MS = 120000

export function usePolling(
  key: () => string,
  load: (signal: AbortSignal, isCurrent: () => boolean) => Promise<void>,
  options: { paused?: () => boolean; onError?: (error: unknown) => void; interval?: number } = {},
) {
  let controller: AbortController | undefined
  let timer: ReturnType<typeof setTimeout> | undefined
  let generation = 0
  let failures = 0
  let disposed = false
  const interval = options.interval ?? POLL_INTERVAL_MS

  function cancel() {
    generation += 1
    controller?.abort()
    clearTimeout(timer)
  }

  async function refresh() {
    cancel()
    if (disposed || document.hidden || !key()) return
    if (options.paused?.()) {
      timer = setTimeout(() => { void refresh() }, interval)
      return
    }
    controller = new AbortController()
    const signal = controller.signal
    const expected = generation
    const isCurrent = () => !disposed && !signal.aborted && generation === expected
    try {
      await load(signal, isCurrent)
      if (isCurrent()) failures = 0
    } catch (error) {
      if (isCurrent()) {
        failures += 1
        options.onError?.(error)
      }
    } finally {
      if (isCurrent()) timer = setTimeout(() => { void refresh() }, Math.min(MAX_BACKOFF_MS, interval * 2 ** failures))
    }
  }

  function resume() { void refresh() }
  document.addEventListener('visibilitychange', resume)
  window.addEventListener('givvi:mutation-start', cancel)
  window.addEventListener('givvi:mutation', resume)
  watch(key, resume, { immediate: true })
  onScopeDispose(() => {
    disposed = true
    cancel()
    document.removeEventListener('visibilitychange', resume)
    window.removeEventListener('givvi:mutation-start', cancel)
    window.removeEventListener('givvi:mutation', resume)
  })
  return { refresh, cancel }
}