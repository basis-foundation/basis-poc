/**
 * Basis Foundation — API client
 *
 * Thin fetch wrapper that:
 *   1. Refreshes the Keycloak access token if it expires within 30 seconds
 *   2. Attaches Authorization: Bearer <token> to every request
 *   3. Forces logout on 401 (token was rejected by the API)
 */
import keycloak from '../auth/keycloak'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

/**
 * Make an authenticated API call.
 *
 * @param {string} path   - e.g. '/api/viewer'
 * @param {object} opts   - standard fetch options (method, body, headers, …)
 * @returns {Promise<{ ok: boolean, status: number, data: any }>}
 */
export async function apiFetch(path, opts = {}) {
  // Ensure the token is fresh (refresh if it expires in < 30 s)
  try {
    await keycloak.updateToken(30)
  } catch {
    // Token could not be refreshed — session has ended
    keycloak.logout()
    return { ok: false, status: 0, data: null }
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${keycloak.token}`,
      ...opts.headers,
    },
  })

  if (response.status === 401) {
    // The API rejected our token — log out and start fresh
    keycloak.logout()
    return { ok: false, status: 401, data: null }
  }

  let data = null
  try {
    data = await response.json()
  } catch {
    // Non-JSON response (e.g. 204 No Content) — leave data as null
  }

  return { ok: response.ok, status: response.status, data }
}
