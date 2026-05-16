/**
 * BASIS — Access Control View
 * Demonstrates RBAC policy enforcement: role matrix, live endpoint test results,
 * and clear explanation of what each role can and cannot do.
 */

const C = {
  bg:      '#0f1117',
  surface: '#1a202c',
  border:  '#2d3748',
  text:    '#e2e8f0',
  muted:   '#718096',
  accent:  '#63b3ed',
  green:   '#68d391',
  greenBg: '#0d2318',
  red:     '#fc8181',
  redBg:   '#2d1010',
  yellow:  '#f6e05e',
  orange:  '#f6ad55',
  purple:  '#b794f4',
}

const ROLES = [
  {
    name: 'viewer',
    color: C.green,
    bg: 'rgba(28,69,50,0.3)',
    borderColor: '#276749',
    icon: '○',
    description: 'Read-only access. Can observe live telemetry and query resource state.',
    abilities: [
      { label: 'View live telemetry',          allowed: true  },
      { label: 'Subscribe to WebSocket feed',  allowed: true  },
      { label: 'Query /api/viewer endpoint',   allowed: true  },
      { label: 'Send HVAC control commands',   allowed: false },
      { label: 'Access /api/operator endpoint', allowed: false },
      { label: 'Access /api/admin endpoint',   allowed: false },
    ],
  },
  {
    name: 'operator',
    color: C.orange,
    bg: 'rgba(116,66,16,0.3)',
    borderColor: '#c05621',
    icon: '◐',
    description: 'Operational control. Can observe telemetry and send HVAC setpoint commands.',
    abilities: [
      { label: 'View live telemetry',          allowed: true  },
      { label: 'Subscribe to WebSocket feed',  allowed: true  },
      { label: 'Query /api/viewer endpoint',   allowed: true  },
      { label: 'Send HVAC control commands',   allowed: true  },
      { label: 'Access /api/operator endpoint', allowed: true  },
      { label: 'Access /api/admin endpoint',   allowed: false },
    ],
  },
  {
    name: 'admin',
    color: C.purple,
    bg: 'rgba(68,51,122,0.3)',
    borderColor: '#6b46c1',
    icon: '●',
    description: 'Full platform access. All operational capabilities plus system configuration and audit log access.',
    abilities: [
      { label: 'View live telemetry',          allowed: true  },
      { label: 'Subscribe to WebSocket feed',  allowed: true  },
      { label: 'Query /api/viewer endpoint',   allowed: true  },
      { label: 'Send HVAC control commands',   allowed: true  },
      { label: 'Access /api/operator endpoint', allowed: true  },
      { label: 'Access /api/admin endpoint',   allowed: true  },
    ],
  },
]

const ENDPOINTS = [
  {
    key: 'viewer',
    path: '/api/viewer',
    method: 'GET',
    description: 'Read-only probe — returns the caller\'s identity and confirms telemetry access',
    requiredRoles: ['viewer', 'operator', 'admin'],
    roleColor: C.green,
  },
  {
    key: 'operator',
    path: '/api/operator',
    method: 'GET',
    description: 'Operator-level probe — confirms HVAC command-send permission',
    requiredRoles: ['operator', 'admin'],
    roleColor: C.orange,
  },
  {
    key: 'admin',
    path: '/api/admin',
    method: 'GET',
    description: 'Admin-level probe — confirms full system access including audit logs',
    requiredRoles: ['admin'],
    roleColor: C.purple,
  },
]

// ── Role card ─────────────────────────────────────────────────────────────────
function RoleCard({ role }) {
  return (
    <div style={{
      background: role.bg,
      border: `1px solid ${role.borderColor}50`,
      borderTop: `2px solid ${role.borderColor}`,
      borderRadius: '8px',
      padding: '1.1rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem' }}>
        <span style={{ color: role.color, fontSize: '0.7rem' }}>{role.icon}</span>
        <span style={{ fontSize: '0.88rem', fontWeight: 700, color: role.color, textTransform: 'uppercase', letterSpacing: '0.06em' }}>
          {role.name}
        </span>
      </div>
      <p style={{ fontSize: '0.75rem', color: C.muted, margin: '0 0 0.75rem', lineHeight: 1.6 }}>
        {role.description}
      </p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
        {role.abilities.map(ab => (
          <div key={ab.label} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.74rem' }}>
            <span style={{ color: ab.allowed ? C.green : C.muted, fontSize: '0.65rem', flexShrink: 0 }}>
              {ab.allowed ? '✓' : '✗'}
            </span>
            <span style={{ color: ab.allowed ? '#c6f6d5' : C.muted }}>
              {ab.label}
            </span>
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Endpoint test card ────────────────────────────────────────────────────────
function EndpointTestCard({ endpoint, result, userRoles }) {
  const hasAccess = endpoint.requiredRoles.some(r => userRoles.includes(r))

  const status =
    result === null    ? 'pending' :
    result.ok          ? 'allowed' :
    result.status === 403 ? 'denied'  : 'error'

  const statusCfg = {
    pending: { color: C.muted,   label: 'Testing…',     dot: '○' },
    allowed: { color: C.green,   label: '200 OK',        dot: '✓' },
    denied:  { color: C.red,     label: '403 Forbidden', dot: '✗' },
    error:   { color: C.yellow,  label: `${result?.status ?? '?'} Error`, dot: '⚠' },
  }[status]

  const borderColor =
    status === 'allowed' ? C.green :
    status === 'denied'  ? C.red :
    C.border

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderLeft: `3px solid ${borderColor}`,
      borderRadius: '8px',
      padding: '1rem 1.1rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{
            fontSize: '0.65rem',
            fontWeight: 700,
            color: '#718096',
            background: '#2d3748',
            padding: '1px 5px',
            borderRadius: '3px',
            fontFamily: 'monospace',
          }}>
            {endpoint.method}
          </span>
          <code style={{ fontSize: '0.8rem', color: C.accent, fontFamily: 'monospace' }}>
            {endpoint.path}
          </code>
        </div>
        <span style={{
          fontSize: '0.72rem',
          fontWeight: 700,
          color: statusCfg.color,
          display: 'flex',
          alignItems: 'center',
          gap: '0.25rem',
        }}>
          <span>{statusCfg.dot}</span>
          <span>{statusCfg.label}</span>
        </span>
      </div>

      <p style={{ fontSize: '0.74rem', color: C.muted, margin: '0 0 0.6rem', lineHeight: 1.5 }}>
        {endpoint.description}
      </p>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
        <span style={{ fontSize: '0.68rem', color: C.muted }}>Required:</span>
        {endpoint.requiredRoles.map(r => {
          const roleCfg = {
            admin:    { bg: 'rgba(68,51,122,0.4)',  color: C.purple },
            operator: { bg: 'rgba(116,66,16,0.4)', color: C.orange },
            viewer:   { bg: 'rgba(28,69,50,0.4)',  color: C.green  },
          }[r] ?? { bg: C.border, color: C.muted }
          return (
            <span key={r} style={{
              fontSize: '0.65rem', fontWeight: 700,
              color: roleCfg.color, background: roleCfg.bg,
              padding: '1px 6px', borderRadius: '8px',
            }}>
              {r}
            </span>
          )
        })}
      </div>

      {!hasAccess && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: C.muted, fontStyle: 'italic' }}>
          Your current role will receive 403 from this endpoint.
        </div>
      )}

      {result?.data?.detail && (
        <div style={{
          marginTop: '0.5rem', fontSize: '0.72rem',
          color: C.red, fontFamily: 'monospace',
          background: C.redBg, padding: '0.3rem 0.5rem', borderRadius: '4px',
        }}>
          {result.data.detail}
        </div>
      )}
    </div>
  )
}

// ── Policy explanation ────────────────────────────────────────────────────────
function PolicyExplainer() {
  return (
    <div style={{
      background: 'rgba(26,39,68,0.5)',
      border: '1px solid #2a4a8a',
      borderRadius: '8px',
      padding: '1rem 1.25rem',
      fontSize: '0.79rem',
      color: '#90cdf4',
      lineHeight: 1.75,
    }}>
      <div style={{ fontWeight: 700, marginBottom: '0.4rem', fontSize: '0.82rem' }}>
        How authorization enforcement works
      </div>
      <p style={{ margin: '0 0 0.5rem' }}>
        Every request to the FastAPI backend carries a{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
          Authorization: Bearer &lt;token&gt;
        </code>{' '}
        header. FastAPI validates the JWT signature against Keycloak's JWKS endpoint, decodes the{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
          realm_access.roles
        </code>{' '}
        claim, and applies the RBAC policy before the route handler executes.
      </p>
      <p style={{ margin: 0 }}>
        A{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
          require_role()
        </code>{' '}
        FastAPI dependency gates every protected route — no role, no access, regardless of what
        the client says. The WebSocket endpoint also validates the token at connection time,
        closing with code <strong>4001</strong> on expiry.
      </p>
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────
export default function AccessControlView({ endpointResults, roles }) {
  return (
    <div>

      {/* ── Page header ────────────────────────────────────────────────── */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.4rem', color: C.text }}>
          Access Control
        </h2>
        <p style={{ fontSize: '0.83rem', color: C.muted, margin: 0, lineHeight: 1.65, maxWidth: '680px' }}>
          BASIS enforces Role-Based Access Control (RBAC) at the API layer using JWT claims issued by Keycloak.
          The three roles below define what each user type can observe and control. This page runs live
          authorization probes against the API to show real enforcement in action.
        </p>
      </div>

      {/* ── Current user notice ─────────────────────────────────────── */}
      {roles.length > 0 && (
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.75rem',
          padding: '0.75rem 1rem',
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: '8px',
          marginBottom: '1.75rem',
          fontSize: '0.8rem',
          color: C.muted,
        }}>
          <span style={{ color: C.green, fontSize: '0.65rem' }}>●</span>
          <span>You are authenticated with role{roles.length > 1 ? 's' : ''}:</span>
          {roles.map(r => {
            const cfg = {
              admin:    { bg: 'rgba(68,51,122,0.5)',  color: C.purple },
              operator: { bg: 'rgba(116,66,16,0.5)', color: C.orange },
              viewer:   { bg: 'rgba(28,69,50,0.5)',  color: C.green  },
            }[r] ?? { bg: C.border, color: C.muted }
            return (
              <span key={r} style={{
                background: cfg.bg, color: cfg.color,
                padding: '1px 8px', borderRadius: '10px',
                fontSize: '0.68rem', fontWeight: 700,
              }}>
                {r}
              </span>
            )
          })}
          <span style={{ color: C.muted }}>— scroll down to see live enforcement results.</span>
        </div>
      )}

      {/* ── Role cards ──────────────────────────────────────────────── */}
      <div style={{
        fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.1em', color: C.muted, marginBottom: '0.85rem',
      }}>
        Role Definitions
      </div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '1rem',
        marginBottom: '2rem',
      }}>
        {ROLES.map(role => <RoleCard key={role.name} role={role} />)}
      </div>

      {/* ── Live endpoint tests ─────────────────────────────────────── */}
      <div style={{
        fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
        letterSpacing: '0.1em', color: C.muted, marginBottom: '0.85rem',
      }}>
        Live Authorization Tests
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.85rem', marginBottom: '1.5rem' }}>
        {ENDPOINTS.map(ep => (
          <EndpointTestCard
            key={ep.key}
            endpoint={ep}
            result={endpointResults[ep.key]}
            userRoles={roles}
          />
        ))}
      </div>

      {/* ── Policy explainer ────────────────────────────────────────── */}
      <PolicyExplainer />

    </div>
  )
}
