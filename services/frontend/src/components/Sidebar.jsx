/**
 * BASIS — Sidebar Navigation
 * Left-rail navigation for the Operator Console.
 * Shows platform branding, view navigation, live service status, and user identity.
 */

const C = {
  bg:       '#080c14',
  surface:  '#0f1520',
  border:   '#1a2235',
  text:     '#e2e8f0',
  muted:    '#4a5568',
  mutedHi:  '#718096',
  accent:   '#63b3ed',
  green:    '#68d391',
  red:      '#fc8181',
  yellow:   '#f6e05e',
  orange:   '#f6ad55',
  purple:   '#b794f4',
}

const ROLE_CFG = {
  admin:    { bg: 'rgba(68,51,122,0.5)',  color: '#b794f4' },
  operator: { bg: 'rgba(116,66,16,0.5)', color: '#f6ad55' },
  viewer:   { bg: 'rgba(28,69,50,0.5)',  color: '#68d391' },
}

const NAV_GROUPS = [
  {
    label: 'Monitor',
    items: [
      { id: 'dashboard', icon: '◈', label: 'Dashboard', liveIndicator: true },
    ],
  },
  {
    label: 'Security',
    items: [
      { id: 'access-control', icon: '⊛', label: 'Access Control' },
      { id: 'audit',          icon: '◑', label: 'Audit Trail', adminBadge: true },
    ],
  },
  {
    label: 'Platform',
    items: [
      { id: 'architecture', icon: '◎', label: 'Architecture' },
      { id: 'identity',     icon: '◇', label: 'Identity'     },
    ],
  },
]

function wsStatusLabel(status) {
  switch (status) {
    case 'connected':    return { dot: '●', text: 'LIVE',    color: C.green  }
    case 'connecting':   return { dot: '○', text: '…',       color: C.muted  }
    case 'reconnecting': return { dot: '◌', text: 'RECONNECT', color: C.yellow }
    case 'auth_error':   return { dot: '✕', text: 'AUTH ERR', color: C.red   }
    default:             return { dot: '○', text: status,    color: C.muted  }
  }
}

export default function Sidebar({ activeView, onNavigate, wsStatus, username, roles, onLogout }) {
  const wsLabel = wsStatusLabel(wsStatus)

  // Service status derived from what we know:
  //   keycloak  — we're authenticated, so it's up
  //   api       — we've made REST calls, so it's up
  //   mqtt      — inferred from websocket telemetry connection
  //   simulator — inferred from telemetry data flowing
  const services = [
    { label: 'Keycloak', port: ':18080', up: true   },
    { label: 'FastAPI',  port: ':8000',  up: true   },
    { label: 'MQTT',     port: ':1883',  up: wsStatus === 'connected' || wsStatus === 'reconnecting' },
    { label: 'Simulator', port: '',     up: wsStatus === 'connected' },
  ]

  return (
    <aside style={{
      width: '220px',
      minHeight: '100vh',
      background: C.bg,
      borderRight: `1px solid ${C.border}`,
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      position: 'sticky',
      top: 0,
      height: '100vh',
    }}>

      {/* ── Brand ─────────────────────────────────────────────────────── */}
      <div style={{
        padding: '1.4rem 1.25rem 1.1rem',
        borderBottom: `1px solid ${C.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.2rem' }}>
          <div style={{
            width: '30px', height: '30px',
            background: 'linear-gradient(135deg, #1e3a6e 0%, #4a2d7c 100%)',
            borderRadius: '7px',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.9rem',
            boxShadow: '0 0 12px rgba(99,179,237,0.15)',
            flexShrink: 0,
          }}>
            ⬡
          </div>
          <span style={{
            fontSize: '1rem',
            fontWeight: 800,
            color: C.text,
            letterSpacing: '0.08em',
            fontFamily: 'system-ui, sans-serif',
          }}>
            BASIS
          </span>
        </div>
        <div style={{
          fontSize: '0.67rem',
          color: C.muted,
          paddingLeft: '2.8rem',
          letterSpacing: '0.04em',
        }}>
          OT Identity Platform
        </div>
      </div>

      {/* ── Navigation ────────────────────────────────────────────────── */}
      <nav style={{ flex: 1, overflowY: 'auto', padding: '0.5rem 0' }}>
        {NAV_GROUPS.map(group => (
          <div key={group.label} style={{ marginBottom: '0.1rem' }}>
            <div style={{
              padding: '0.6rem 1.25rem 0.2rem',
              fontSize: '0.6rem',
              fontWeight: 700,
              textTransform: 'uppercase',
              letterSpacing: '0.12em',
              color: C.muted,
            }}>
              {group.label}
            </div>

            {group.items.map(item => {
              const active = activeView === item.id
              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.55rem',
                    width: '100%',
                    padding: '0.5rem 1.25rem',
                    background: active ? 'rgba(99,179,237,0.07)' : 'transparent',
                    border: 'none',
                    borderLeft: `2px solid ${active ? C.accent : 'transparent'}`,
                    cursor: 'pointer',
                    color: active ? C.accent : C.mutedHi,
                    fontSize: '0.82rem',
                    textAlign: 'left',
                    lineHeight: 1,
                    transition: 'color 0.1s, background 0.1s, border-color 0.1s',
                  }}
                  onMouseEnter={e => { if (!active) e.currentTarget.style.color = C.text }}
                  onMouseLeave={e => { if (!active) e.currentTarget.style.color = C.mutedHi }}
                >
                  <span style={{ fontSize: '0.72rem', opacity: active ? 1 : 0.55, flexShrink: 0 }}>
                    {item.icon}
                  </span>
                  <span style={{ flex: 1 }}>{item.label}</span>
                  {item.liveIndicator && (
                    <span style={{
                      fontSize: '0.58rem',
                      fontWeight: 700,
                      color: wsLabel.color,
                      opacity: 0.9,
                    }}>
                      {wsLabel.dot} {wsLabel.text}
                    </span>
                  )}
                  {item.adminBadge && (
                    <span style={{
                      fontSize: '0.55rem',
                      fontWeight: 700,
                      color: C.purple,
                      opacity: 0.85,
                      letterSpacing: '0.03em',
                    }}>
                      admin
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        ))}

        {/* ── Services ─────────────────────────────────────────────── */}
        <div style={{ marginTop: '0.75rem', borderTop: `1px solid ${C.border}`, paddingTop: '0.6rem' }}>
          <div style={{
            padding: '0.3rem 1.25rem 0.2rem',
            fontSize: '0.6rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.12em',
            color: C.muted,
          }}>
            Services
          </div>

          {services.map(svc => (
            <div key={svc.label} style={{
              display: 'flex',
              alignItems: 'center',
              padding: '0.22rem 1.25rem',
              fontSize: '0.75rem',
            }}>
              <span style={{
                color: svc.up ? C.green : C.muted,
                fontSize: '0.45rem',
                marginRight: '0.55rem',
                flexShrink: 0,
              }}>
                ●
              </span>
              <span style={{ color: C.mutedHi, flex: 1 }}>{svc.label}</span>
              {svc.port && (
                <span style={{
                  color: C.muted,
                  fontSize: '0.65rem',
                  fontFamily: 'monospace',
                }}>
                  {svc.port}
                </span>
              )}
            </div>
          ))}
        </div>
      </nav>

      {/* ── User ──────────────────────────────────────────────────────── */}
      <div style={{
        padding: '0.85rem 1.25rem',
        borderTop: `1px solid ${C.border}`,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.55rem', marginBottom: '0.5rem' }}>
          <div style={{
            width: '26px', height: '26px',
            background: 'linear-gradient(135deg, #1e3a5f 0%, #2d1b69 100%)',
            borderRadius: '50%',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: '0.7rem',
            color: '#90cdf4',
            fontWeight: 700,
            flexShrink: 0,
          }}>
            {username ? username.charAt(0).toUpperCase() : '?'}
          </div>
          <span style={{
            fontSize: '0.8rem',
            color: C.text,
            fontWeight: 500,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
            whiteSpace: 'nowrap',
          }}>
            {username}
          </span>
        </div>

        <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap', marginBottom: '0.65rem' }}>
          {roles.length > 0
            ? roles.map(r => {
                const cfg = ROLE_CFG[r] ?? { bg: 'rgba(45,55,72,0.6)', color: C.mutedHi }
                return (
                  <span key={r} style={{
                    background: cfg.bg,
                    color: cfg.color,
                    padding: '1px 7px',
                    borderRadius: '10px',
                    fontSize: '0.63rem',
                    fontWeight: 700,
                    border: `1px solid ${cfg.color}22`,
                  }}>
                    {r}
                  </span>
                )
              })
            : <span style={{ fontSize: '0.7rem', color: C.muted }}>no roles</span>
          }
        </div>

        <button
          onClick={onLogout}
          style={{
            width: '100%',
            padding: '0.38rem',
            background: 'transparent',
            border: `1px solid ${C.border}`,
            borderRadius: '5px',
            color: C.muted,
            cursor: 'pointer',
            fontSize: '0.73rem',
            transition: 'border-color 0.1s, color 0.1s',
          }}
          onMouseEnter={e => {
            e.currentTarget.style.borderColor = '#fc8181'
            e.currentTarget.style.color = '#fc8181'
          }}
          onMouseLeave={e => {
            e.currentTarget.style.borderColor = C.border
            e.currentTarget.style.color = C.muted
          }}
        >
          Log out
        </button>
      </div>

    </aside>
  )
}
