/**
 * Centralized fetch boundary for all frontend API calls.
 *
 * Behaviour:
 * - Only same-origin /api/* requests are intercepted.
 * - Adds X-Requested-With and optional Bearer token headers.
 * - Retries once after RETRY_DELAY_MS on transient failures:
 *     • Network error (TypeError) — request never reached the server,
 *       safe to retry for any HTTP method.
 *     • 502 / 503 / 504 — gateway/proxy error, app was not running,
 *       request was not processed.
 *   Does NOT retry 4xx or 500 — those indicate the server processed
 *   the request and returned a real error.
 */

let installed = false

const SECURITY_MODE = (import.meta.env.VITE_SECURITY_MODE || 'off').toLowerCase()
const STATIC_TOKEN = (import.meta.env.VITE_API_TOKEN || '').trim()

const RETRY_DELAY_MS = 1000
const RETRYABLE_STATUSES = new Set([502, 503, 504])

function sleep(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

function getToken() {
  if (SECURITY_MODE !== 'token') return ''
  const stored = window.localStorage.getItem('ipxe_station_token') || ''
  return (stored || STATIC_TOKEN).trim()
}

function isSameOriginApiRequest(input) {
  let raw = ''
  if (typeof input === 'string') {
    raw = input
  } else if (input instanceof URL) {
    raw = input.href
  } else if (input && typeof input === 'object' && 'url' in input) {
    raw = input.url
  }

  if (!raw) return false
  if (raw.startsWith('/api/')) return true

  try {
    const url = new URL(raw, window.location.origin)
    return url.origin === window.location.origin && url.pathname.startsWith('/api/')
  } catch {
    return false
  }
}

export function installFetchClient() {
  if (installed) return
  installed = true

  const nativeFetch = window.fetch.bind(window)

  window.fetch = async (input, init = undefined) => {
    if (!isSameOriginApiRequest(input)) {
      return nativeFetch(input, init)
    }

    const baseHeaders = input instanceof Request ? input.headers : undefined
    const headers = new Headers(baseHeaders)

    if (init?.headers) {
      const extra = new Headers(init.headers)
      extra.forEach((value, key) => headers.set(key, value))
    }

    if (!headers.has('X-Requested-With')) {
      headers.set('X-Requested-With', 'ipxe-station-ui')
    }

    const token = getToken()
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }

    const mergedInit = { ...init, headers }

    try {
      const response = await nativeFetch(input, mergedInit)
      if (RETRYABLE_STATUSES.has(response.status)) {
        await sleep(RETRY_DELAY_MS)
        return nativeFetch(input, mergedInit)
      }
      return response
    } catch {
      // Network error: server unreachable or restarting.
      // Request never reached the app — safe to retry once.
      await sleep(RETRY_DELAY_MS)
      return nativeFetch(input, mergedInit)
    }
  }
}

