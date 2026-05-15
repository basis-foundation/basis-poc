/**
 * Basis Foundation — API client
 *
 * Thin fetch wrapper that:
 *   1. Refreshes the Keycloak access token if it expires within 30 seconds
 *   2. Attaches Authorization: Bearer <token> to every request
 *   3. Forces logout on 401 (token was rejected by the API)
 */
import keycloak from '../auth/keycloak'

// Always use the page's own origin so REST calls go through Vite's /api proxy,
// just as WebSocket connections go through Vite's /ws proxy. This keeps all
// traffic on a single authenticated port (5173) — essential in Codespaces where
// each forwarded port has its own tunnel auth cookie and direct cross-port fetches
// produce "TypeError: Failed to fetch" (no cookie for the target port domain).
//
// VITE_API_URL is intentionally NOT used here for the same reason App.jsx uses
// window.location.origin for WS_BASE_URL instead of VITE_API_URL.
const API_BASE = window.location.origin

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

  let response
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...opts,
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${keycloak.token}`,
        ...opts.headers,
      },
    })
  } catch (networkErr) {
    // Network failure (CORS, unreachable host, etc.) — surface as a structured error
    // rather than letting the promise reject and silently hang callers.
    console.error(`apiFetch network error [${path}]:`, networkErr)
    return { ok: false, status: 0, data: null, networkError: String(networkErr) }
  }

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
