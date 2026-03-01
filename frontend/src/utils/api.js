/**
 * Centralised fetch wrapper.
 *
 * - Always sends / expects JSON
 * - Throws an Error with a human-readable message on non-2xx responses
 */

async function apiFetch(path, options = {}) {
  const res = await fetch(path, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options.headers,
    },
  })

  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || body.message || detail
    } catch {
      // keep default detail
    }
    throw new Error(detail)
  }

  return res.json()
}

export const api = {
  get:    (path)        => apiFetch(path),
  post:   (path, body)  => apiFetch(path, { method: 'POST',   body: JSON.stringify(body) }),
  delete: (path)        => apiFetch(path, { method: 'DELETE' }),
}

export default api
