/**
 * Basis Foundation — Keycloak singleton
 *
 * A single Keycloak instance is shared across the whole app.
 * initKeycloak() is safe to call multiple times — it returns the same
 * promise, preventing double-initialization in React StrictMode.
 */
import Keycloak from 'keycloak-js'

const keycloak = new Keycloak({
  url: import.meta.env.VITE_KEYCLOAK_URL || 'http://localhost:18080',
  realm: import.meta.env.VITE_KEYCLOAK_REALM || 'basis',
  clientId: import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'basis-frontend',
})

// Module-level promise — ensures init() is called exactly once
// even when React StrictMode mounts components twice in development.
let _initPromise = null

export function initKeycloak() {
  if (_initPromise) return _initPromise

  _initPromise = keycloak
    .init({
      onLoad: 'login-required',   // redirect to Keycloak login if not authenticated
      pkceMethod: 'S256',          // PKCE — matches the realm client configuration
      checkLoginIframe: false,     // disable silent check iframe (causes issues in dev)
    })
    .catch((err) => {
      // Reset so a subsequent call can retry
      _initPromise = null
      throw err
    })

  return _initPromise
}

/**
 * Return the user's realm roles from the decoded token.
 * Available after initKeycloak() resolves.
 */
export function getRoles() {
  return keycloak.tokenParsed?.realm_access?.roles ?? []
}

/**
 * Check whether the current user holds a given realm role.
 */
export function hasRole(role) {
  return keycloak.hasRealmRole(role)
}

export default keycloak
