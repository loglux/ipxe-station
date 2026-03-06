/**
 * Centralized fetch boundary for all frontend API calls.
 *
 * Current behavior is intentionally non-breaking:
 * - Existing fetch call sites keep working unchanged.
 * - Only same-origin /api/* requests are intercepted.
 * - Optional token mode can be enabled later via env/localStorage.
 */

let installed = false

const SECURITY_MODE = (import.meta.env.VITE_SECURITY_MODE || 'off').toLowerCase()
const STATIC_TOKEN = (import.meta.env.VITE_API_TOKEN || '').trim()

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

    return nativeFetch(input, { ...init, headers })
  }
}

