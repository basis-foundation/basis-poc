/**
 * BASIS — Identity View
 * Shows the authenticated user's identity, decoded JWT token claims,
 * OIDC configuration, and an explanation of the authentication flow.
 */

const C = {
  bg:      '#0f1117',
  surface: '#1a202c',
  border:  '#2d3748',
  text:    '#e2e8f0',
  muted:   '#718096',
  accent:  '#63b3ed',
  green:   '#68d391',
  red:     '#fc8181',
  yellow:  '#f6e05e',
  orange:  '#f6ad55',
  purple:  '#b794f4',
}

const ROLE_CFG = {
  admin:    { bg: 'rgba(68,51,122,0.5)',  color: '#b794f4' },
  operator: { bg: 'rgba(116,66,16,0.5)', color: '#f6ad55' },
  viewer:   { bg: 'rgba(28,69,50,0.5)',  color: '#68d391' },
}

// ── JWT claim rows ────────────────────────────────────────────────────────────
const CLAIM_META = {
  sub:                { label: 'Subject',         desc: 'Unique user identifier (UUID)' },
  preferred_username: { label: 'Username',        desc: 'Login name in Keycloak' },
  email:              { label: 'Email',           desc: 'User email address' },
  name:               { label: 'Display name',    desc: 'Full display name' },
  iss:                { label: 'Issuer',          desc: 'Keycloak realm URL that issued this token' },
  aud:                { label: 'Audience',        desc: 'Intended recipient(s) of this token' },
  exp:                { label: 'Expires',         desc: 'Token expiry (Unix timestamp)' },
  iat:                { label: 'Issued at',       desc: 'Token issuance time' },
  nbf:                { label: 'Not before',      desc: 'Token valid from this time' },
  jti:                { label: 'JWT ID',          desc: 'Unique token identifier' },
  azp:                { label: 'Authorized party', desc: 'Client that requested this token' },
  realm_access:       { label: 'Realm roles',     desc: 'Roles assigned in this Keycloak realm' },
  resource_access:    { label: 'Resource access', desc: 'Per-client role assignments' },
  scope:              { label: 'Scope',           desc: 'OAuth2 scopes granted' },
  session_state:      { label: 'Session',         desc: 'Keycloak SSO session identifier' },
  typ:                { label: 'Type',            desc: 'Token type (Bearer)' },
  acr:                { label: 'Auth context',    desc: 'Authentication context class reference' },
  sid:                { label: 'Session ID',      desc: 'Session identifier' },
  email_verified:     { label: 'Email verified',  desc: 'Whether the email address is confirmed' },
}

// Prioritized claim order for display
const CLAIM_ORDER = [
  'preferred_username', 'email', 'name',
  'sub',
  'realm_access',
  'iss', 'aud', 'azp', 'scope',
  'exp', 'iat', 'nbf',
  'jti', 'session_state', 'sid', 'acr',
  'email_verified', 'typ',
]

function formatClaimValue(key, value) {
  if (key === 'exp' || key === 'iat' || key === 'nbf') {
    try {
      const d = new Date(value * 1000)
      return `${value} (${d.toLocaleString()})`
    } catch {
      return String(value)
    }
  }
  if (typeof value === 'object') {
    return JSON.stringify(value, null, 0)
  }
  return String(value)
}

// ── Token claim table ─────────────────────────────────────────────────────────
function TokenClaimsTable({ tokenParsed }) {
  if (!tokenParsed) return null

  const orderedKeys = [
    ...CLAIM_ORDER.filter(k => k in tokenParsed),
    ...Object.keys(tokenParsed).filter(k => !CLAIM_ORDER.includes(k)).sort(),
  ]

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: '8px',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '0.75rem 1.1rem',
        borderBottom: `1px solid ${C.border}`,
        fontSize: '0.65rem',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        color: C.muted,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}>
        <span>Decoded JWT Claims</span>
        <span style={{ color: C.green, fontSize: '0.62rem', fontWeight: 600 }}>● valid</span>
      </div>
      <div style={{ overflowX: 'auto' }}>
        {orderedKeys.map((key, i) => {
          const meta = CLAIM_META[key]
          const rawValue = tokenParsed[key]
          const displayValue = formatClaimValue(key, rawValue)
          const isRoles = key === 'realm_access'
          const isLong = displayValue.length > 60

          return (
            <div key={key} style={{
              display: 'grid',
              gridTemplateColumns: '150px 1fr',
              borderBottom: i < orderedKeys.length - 1 ? `1px solid ${C.border}` : 'none',
              fontSize: '0.77rem',
            }}>
              {/* Key cell */}
              <div style={{
                padding: '0.5rem 1.1rem',
                borderRight: `1px solid ${C.border}`,
                background: 'rgba(0,0,0,0.15)',
              }}>
                <div style={{ color: C.accent, fontFamily: 'monospace', fontSize: '0.73rem' }}>{key}</div>
                {meta && (
                  <div style={{ color: C.muted, fontSize: '0.65rem', marginTop: '1px' }}>{meta.label}</div>
                )}
              </div>

              {/* Value cell */}
              <div style={{ padding: '0.5rem 1.1rem' }}>
                {isRoles && rawValue?.roles ? (
                  <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
                    {rawValue.roles.map(r => {
                      const cfg = ROLE_CFG[r] ?? { bg: C.border, color: C.muted }
                      return (
                        <span key={r} style={{
                          background: cfg.bg, color: cfg.color,
                          padding: '1px 7px', borderRadius: '8px',
                          fontSize: '0.68rem', fontWeight: 700,
                        }}>
                          {r}
                        </span>
                      )
                    })}
                    {rawValue.roles.filter(r => !['admin', 'operator', 'viewer'].includes(r)).length > 0 && (
                      <span style={{ color: C.muted, fontSize: '0.68rem', alignSelf: 'center' }}>
                        (+system roles hidden)
                      </span>
                    )}
                  </div>
                ) : (
                  <code style={{
                    fontFamily: 'monospace',
                    fontSize: '0.73rem',
                    color: C.text,
                    wordBreak: isLong ? 'break-all' : 'normal',
                    whiteSpace: isLong ? 'pre-wrap' : 'normal',
                    display: 'block',
                  }}>
                    {displayValue}
                  </code>
                )}
                {meta?.desc && (
                  <div style={{ color: C.muted, fontSize: '0.65rem', marginTop: '2px' }}>
                    {meta.desc}
                  </div>
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

// ── Identity summary card ─────────────────────────────────────────────────────
function IdentitySummaryCard({ username, email, roles, meResult }) {
  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: '8px',
      padding: '1.25rem',
    }}>
      <div style={{
        fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.1em', color: C.muted, marginBottom: '1rem',
      }}>
        Authenticated Identity
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', marginBottom: '1.25rem' }}>
        <div style={{
          width: '48px', height: '48px',
          background: 'linear-gradient(135deg, #1e3a5f 0%, #2d1b69 100%)',
          borderRadius: '50%',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.2rem', color: '#90cdf4', fontWeight: 700,
          flexShrink: 0,
        }}>
          {username ? username.charAt(0).toUpperCase() : '?'}
        </div>
        <div>
          <div style={{ fontSize: '1rem', fontWeight: 700, color: C.text }}>{username}</div>
          {email && <div style={{ fontSize: '0.78rem', color: C.muted, marginTop: '1px' }}>{email}</div>}
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '110px 1fr', gap: '0.5rem 0', fontSize: '0.8rem', alignItems: 'center' }}>
        <span style={{ color: C.muted }}>Username</span>
        <span style={{ fontWeight: 600 }}>{username || '—'}</span>

        <span style={{ color: C.muted }}>Email</span>
        <span>{email || '—'}</span>

        <span style={{ color: C.muted }}>Roles</span>
        <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
          {roles.length > 0
            ? roles.map(r => {
                const cfg = ROLE_CFG[r] ?? { bg: C.border, color: C.muted }
                return (
                  <span key={r} style={{
                    background: cfg.bg, color: cfg.color,
                    padding: '1px 8px', borderRadius: '10px',
                    fontSize: '0.68rem', fontWeight: 700,
                  }}>
                    {r}
                  </span>
                )
              })
            : <span style={{ color: C.muted }}>none</span>
          }
        </div>

        <span style={{ color: C.muted }}>API /me</span>
        <span style={{
          fontSize: '0.72rem',
          color: meResult?.ok ? C.green : meResult === null ? C.muted : C.red,
        }}>
          {meResult === null ? 'Loading…' : meResult.ok ? '200 OK — identity confirmed' : `${meResult.status} Error`}
        </span>
      </div>
    </div>
  )
}

// ── OIDC flow explanation ─────────────────────────────────────────────────────
const OIDC_STEPS = [
  {
    step: 'A',
    title: 'App initializes Keycloak JS adapter',
    description: 'On load, the frontend calls keycloak.init() with onLoad: "login-required". If no valid session exists, the browser is redirected to Keycloak\'s login page.',
    color: C.purple,
  },
  {
    step: 'B',
    title: 'User authenticates with Keycloak',
    description: 'Keycloak validates credentials and checks realm configuration. The demo realm has pre-seeded users (alice/operator, bob/viewer, carol/admin) for convenience.',
    color: C.purple,
  },
  {
    step: 'C',
    title: 'Authorization code + PKCE exchange',
    description: 'Keycloak redirects back with an authorization code. The adapter exchanges this for an access token using the PKCE code verifier — mitigating code interception attacks.',
    color: C.accent,
  },
  {
    step: 'D',
    title: 'JWT stored in memory, not localStorage',
    description: 'The access token is held in the Keycloak adapter\'s memory. It is never written to localStorage or cookies — reducing XSS exposure. Every API call fetches it fresh from the adapter.',
    color: C.accent,
  },
  {
    step: 'E',
    title: 'FastAPI validates tokens via JWKS',
    description: 'Each backend request includes Authorization: Bearer <token>. FastAPI fetches Keycloak\'s JWKS endpoint, verifies the RS256 signature, checks expiry, and extracts role claims.',
    color: C.green,
  },
  {
    step: 'F',
    title: 'Token refresh heartbeat',
    description: 'The frontend runs a 30-second interval that calls keycloak.updateToken(60). If the token expires within 60 seconds, Keycloak issues a fresh one using the refresh token — seamlessly.',
    color: C.green,
  },
]

function OidcFlowStep({ step }) {
  return (
    <div style={{ display: 'flex', gap: '0.85rem', alignItems: 'flex-start' }}>
      <div style={{
        width: '22px', height: '22px',
        borderRadius: '50%',
        background: `${step.color}20`,
        border: `1.5px solid ${step.color}50`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.65rem', fontWeight: 700,
        color: step.color,
        flexShrink: 0,
        marginTop: '2px',
      }}>
        {step.step}
      </div>
      <div>
        <div style={{ fontSize: '0.82rem', fontWeight: 600, color: C.text, marginBottom: '0.15rem' }}>
          {step.title}
        </div>
        <p style={{ fontSize: '0.75rem', color: C.muted, margin: 0, lineHeight: 1.6 }}>
          {step.description}
        </p>
      </div>
    </div>
  )
}

// ── Keycloak config card ──────────────────────────────────────────────────────
function KeycloakConfigCard({ tokenParsed }) {
  const issuer = tokenParsed?.iss ?? '—'
  const realm = issuer.includes('/realms/') ? issuer.split('/realms/')[1] : '—'
  const keycloakBase = issuer.includes('/realms/') ? issuer.split('/realms/')[0] : '—'

  const configs = [
    { key: 'Realm',          value: realm },
    { key: 'Issuer',         value: issuer, mono: true, truncate: true },
    { key: 'Grant type',     value: 'authorization_code + PKCE' },
    { key: 'Token signing',  value: 'RS256 (asymmetric)' },
    { key: 'JWKS endpoint',  value: `${keycloakBase}/realms/${realm}/protocol/openid-connect/certs`, mono: true, truncate: true },
    { key: 'Login endpoint', value: `${keycloakBase}/realms/${realm}/protocol/openid-connect/auth`, mono: true, truncate: true },
    { key: 'Client ID',      value: tokenParsed?.azp ?? '—', mono: true },
  ]

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: '8px',
      overflow: 'hidden',
    }}>
      <div style={{
        padding: '0.75rem 1.1rem',
        borderBottom: `1px solid ${C.border}`,
        fontSize: '0.65rem',
        fontWeight: 700,
        textTransform: 'uppercase',
        letterSpacing: '0.1em',
        color: C.muted,
      }}>
        Keycloak Configuration
      </div>
      {configs.map((row, i) => (
        <div key={row.key} style={{
          display: 'grid',
          gridTemplateColumns: '150px 1fr',
          borderBottom: i < configs.length - 1 ? `1px solid ${C.border}` : 'none',
          fontSize: '0.78rem',
        }}>
          <div style={{
            padding: '0.45rem 1.1rem',
            borderRight: `1px solid ${C.border}`,
            color: C.muted,
            background: 'rgba(0,0,0,0.1)',
          }}>
            {row.key}
          </div>
          <div style={{ padding: '0.45rem 1.1rem', overflow: 'hidden' }}>
            <span style={{
              fontFamily: row.mono ? 'monospace' : 'inherit',
              fontSize: row.mono ? '0.72rem' : '0.78rem',
              color: C.text,
              display: 'block',
              overflow: row.truncate ? 'hidden' : 'visible',
              textOverflow: row.truncate ? 'ellipsis' : 'clip',
              whiteSpace: row.truncate ? 'nowrap' : 'normal',
            }}>
              {row.value}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────
export default function IdentityView({ username, email, roles, meResult, keycloak }) {
  const tokenParsed = keycloak?.tokenParsed ?? null

  return (
    <div>

      {/* ── Page header ────────────────────────────────────────────── */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.4rem', color: C.text }}>
          Identity
        </h2>
        <p style={{ fontSize: '0.83rem', color: C.muted, margin: 0, lineHeight: 1.65, maxWidth: '680px' }}>
          Your authenticated session is backed by a signed JWT issued by Keycloak.
          Every API call and WebSocket connection presents this token for validation.
          Below you can inspect the decoded token claims, see how the OIDC flow works,
          and explore the Keycloak configuration.
        </p>
      </div>

      {/* ── Identity summary + KC config ────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1.5fr',
        gap: '1rem',
        marginBottom: '1.75rem',
      }}>
        <IdentitySummaryCard
          username={username}
          email={email}
          roles={roles}
          meResult={meResult}
        />
        <KeycloakConfigCard tokenParsed={tokenParsed} />
      </div>

      {/* ── JWT claims table ─────────────────────────────────────────── */}
      <div style={{ marginBottom: '1.75rem' }}>
        <TokenClaimsTable tokenParsed={tokenParsed} />
      </div>

      {/* ── OIDC flow ────────────────────────────────────────────────── */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '10px',
        padding: '1.5rem',
      }}>
        <div style={{
          fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.1em', color: C.muted, marginBottom: '1.25rem',
        }}>
          OIDC Authentication Flow
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {OIDC_STEPS.map((s, i) => (
            <div key={s.step}>
              <OidcFlowStep step={s} />
              {i < OIDC_STEPS.length - 1 && (
                <div style={{
                  width: '1px', height: '8px',
                  background: C.border,
                  marginLeft: '10px', marginTop: '0.5rem',
                }} />
              )}
            </div>
          ))}
        </div>
      </div>

    </div>
  )
}
