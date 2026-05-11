/**
 * Basis Foundation — Frontend
 * Stage 4: Role-gated HVAC control commands + live telemetry feedback.
 */

import { useState, useEffect, useRef } from 'react'
import keycloak, { initKeycloak, getRoles, hasRole } from './auth/keycloak'
import { apiFetch } from './api/client'
import { useTelemetry } from './ws/telemetry'
import TelemetryDashboard, { TOPIC_HVAC } from './components/TelemetryDashboard'
import ControlPanel from './components/ControlPanel'

// ── WebSocket URL ─────────────────────────────────────────────────────────────
const WS_URL =
  (import.meta.env.VITE_API_URL || 'http://localhost:8000')
    .replace(/^http/, 'ws') + '/ws/telemetry'

// ── Design tokens ─────────────────────────────────────────────────────────────
const C = {
  bg:       '#0f1117',
  surface:  '#1a202c',
  border:   '#2d3748',
  text:     '#e2e8f0',
  muted:    '#718096',
  accent:   '#63b3ed',
  green:    '#68d391',
  greenBg:  '#1c4532',
  red:      '#fc8181',
  yellow:   '#f6e05e',
  yellowBg: '#744210',
  purple:   '#b794f4',
  purpleBg: '#44337a',
}

const ROLE_COLORS = {
  admin:    { bg: C.purpleBg, text: C.purple },
  operator: { bg: C.yellowBg, text: C.yellow },
  viewer:   { bg: C.greenBg,  text: C.green  },
}

// ── Small components ──────────────────────────────────────────────────────────
function RoleBadge({ role }) {
  const { bg, text } = ROLE_COLORS[role] ?? { bg: C.border, text: C.muted }
  return (
    <span style={{
      background: bg, color: text,
      padding: '1px 8px', borderRadius: '10px',
      fontSize: '0.7rem', fontWeight: 700,
    }}>
      {role}
    </span>
  )
}

function EndpointCard({ path, label, requiredRoles, result }) {
  const allowed = requiredRoles.some(r => hasRole(r))
  const statusColor = result === null ? C.muted : result.ok ? C.green : C.red
  const statusText  = result === null ? 'not tested'
    : result.ok ? '200 OK'
    : `${result.status} ${result.status === 403 ? 'Forbidden' : 'Error'}`

  return (
    <div style={{
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderLeft: `3px solid ${result === null ? C.border : result.ok ? C.green : C.red}`,
      borderRadius: '8px', padding: '1rem',
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.4rem' }}>
        <code style={{ fontSize: '0.78rem', color: C.accent }}>{path}</code>
        <span style={{ fontSize: '0.72rem', color: statusColor, fontWeight: 600 }}>{statusText}</span>
      </div>
      <div style={{ fontSize: '0.73rem', color: C.muted, marginBottom: '0.5rem' }}>{label}</div>
      <div style={{ display: 'flex', gap: '0.3rem' }}>
        {requiredRoles.map(r => <RoleBadge key={r} role={r} />)}
      </div>
      {result && !result.ok && result.data?.detail && (
        <div style={{ marginTop: '0.5rem', fontSize: '0.72rem', color: C.red }}>
          {result.data.detail}
        </div>
      )}
      {!allowed && (
        <div style={{ marginTop: '0.4rem', fontSize: '0.7rem', color: C.muted, fontStyle: 'italic' }}>
          Your role will receive 403 from this endpoint.
        </div>
      )}
    </div>
  )
}

function CenteredMessage({ title, sub, color = C.muted }) {
  return (
    <div style={{
      minHeight: '100vh', background: C.bg,
      display: 'flex', flexDirection: 'column',
      alignItems: 'center', justifyContent: 'center', gap: '0.5rem',
      fontFamily: 'system-ui, sans-serif', color: C.text,
    }}>
      <div style={{ fontSize: '1.1rem', fontWeight: 600, color }}>{title}</div>
      {sub && <div style={{ fontSize: '0.85rem', color: C.muted }}>{sub}</div>}
    </div>
  )
}

// ── App ───────────────────────────────────────────────────────────────────────
export default function App() {
  const [authState, setAuthState]         = useState('loading')
  const [meResult, setMeResult]           = useState(null)
  const [endpointResults, setEndpointResults] = useState({
    viewer: null, operator: null, admin: null,
  })
  const didInit = useRef(false)

  // Single WebSocket connection — shared between TelemetryDashboard and ControlPanel
  const { telemetry, wsStatus } = useTelemetry(WS_URL)

  // ── Keycloak init ─────────────────────────────────────────────────────────
  useEffect(() => {
    if (didInit.current) return
    didInit.current = true
    initKeycloak()
      .then(authenticated => setAuthState(authenticated ? 'authenticated' : 'error'))
      .catch(err => { console.error('Keycloak init failed:', err); setAuthState('error') })
  }, [])

  // ── Auto-test protected endpoints on login ────────────────────────────────
  useEffect(() => {
    if (authState !== 'authenticated') return
    const run = async () => {
      const me = await apiFetch('/api/me')
      setMeResult(me)
      const [v, o, a] = await Promise.all([
        apiFetch('/api/viewer'),
        apiFetch('/api/operator'),
        apiFetch('/api/admin'),
      ])
      setEndpointResults({ viewer: v, operator: o, admin: a })
    }
    run()
  }, [authState])

  // ── Token refresh heartbeat ───────────────────────────────────────────────
  useEffect(() => {
    if (authState !== 'authenticated') return
    const id = setInterval(() => {
      keycloak.updateToken(60).catch(() => keycloak.logout())
    }, 30_000)
    return () => clearInterval(id)
  }, [authState])

  // ── Loading / error screens ───────────────────────────────────────────────
  if (authState === 'loading') {
    return <CenteredMessage title="Initializing authentication…" sub="Connecting to Keycloak" />
  }
  if (authState === 'error') {
    return (
      <CenteredMessage
        title="Authentication failed"
        sub="Could not connect to Keycloak. Check that it is running at the configured URL."
        color={C.red}
      />
    )
  }

  // ── Authenticated layout ──────────────────────────────────────────────────
  const username = keycloak.tokenParsed?.preferred_username ?? '—'
  const email    = keycloak.tokenParsed?.email ?? ''
  const roles    = getRoles().filter(r => ['viewer', 'operator', 'admin'].includes(r))
  const hvacData = telemetry[TOPIC_HVAC] ?? null

  const ENDPOINTS = [
    { key: 'viewer',   path: '/api/viewer',   label: 'Read-only telemetry access',          requiredRoles: ['viewer', 'operator', 'admin'] },
    { key: 'operator', path: '/api/operator', label: 'HVAC control (setpoint commands)',     requiredRoles: ['operator', 'admin'] },
    { key: 'admin',    path: '/api/admin',    label: 'Audit logs and system config (Stage 5)', requiredRoles: ['admin'] },
  ]

  return (
    <div style={{
      minHeight: '100vh', background: C.bg, color: C.text,
      fontFamily: 'system-ui, -apple-system, sans-serif', fontSize: '14px', lineHeight: 1.6,
    }}>

      {/* ── Top bar ─────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', alignItems: 'center', padding: '0.75rem 2rem',
        background: C.surface, borderBottom: `1px solid ${C.border}`, gap: '1rem',
      }}>
        <h1 style={{ fontSize: '1rem', fontWeight: 700, color: C.text, margin: 0 }}>
          Basis Foundation
        </h1>
        <span style={{ fontSize: '0.75rem', color: C.muted }}>Stage 5 — Audit Logging</span>
        <div style={{ flex: 1 }} />
        <div style={{
          display: 'flex', alignItems: 'center', gap: '0.5rem',
          background: C.bg, border: `1px solid ${C.border}`,
          borderRadius: '20px', padding: '0.25rem 0.75rem',
          fontSize: '0.8rem', color: C.muted,
        }}>
          <span style={{ color: C.green }}>●</span>
          <span>{username}</span>
          {roles.map(r => <RoleBadge key={r} role={r} />)}
        </div>
        <button
          onClick={() => keycloak.logout()}
          style={{
            padding: '0.3rem 0.9rem', background: 'transparent',
            border: `1px solid ${C.border}`, borderRadius: '6px',
            color: C.muted, cursor: 'pointer', fontSize: '0.8rem',
          }}
        >
          Log out
        </button>
      </div>

      {/* ── Main content ─────────────────────────────────────────────────── */}
      <div style={{ maxWidth: '1000px', margin: '0 auto', padding: '2rem' }}>

        {/* ── Live telemetry ─────────────────────────────────────────────── */}
        <TelemetryDashboard telemetry={telemetry} wsStatus={wsStatus} />

        {/* ── HVAC control panel ─────────────────────────────────────────── */}
        <div style={{ marginTop: '1rem' }}>
          <ControlPanel hvacData={hvacData} />
        </div>

        {/* ── Divider ────────────────────────────────────────────────────── */}
        <hr style={{ border: 'none', borderTop: `1px solid ${C.border}`, margin: '2rem 0' }} />

        {/* ── Identity + token claims ─────────────────────────────────────── */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem', marginBottom: '1.5rem',
        }}>
          <div style={{
            background: C.surface, border: `1px solid ${C.border}`,
            borderRadius: '8px', padding: '1.25rem',
          }}>
            <div style={{
              fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
              letterSpacing: '0.08em', color: C.muted, marginBottom: '1rem',
            }}>
              Authenticated Identity
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '100px 1fr', gap: '0.25rem 0', fontSize: '0.85rem' }}>
              <span style={{ color: C.muted }}>Username</span>
              <span style={{ fontWeight: 600 }}>{username}</span>
              <span style={{ color: C.muted }}>Email</span>
              <span>{email || '—'}</span>
              <span style={{ color: C.muted }}>Roles</span>
              <div style={{ display: 'flex', gap: '0.4rem', flexWrap: 'wrap' }}>
                {roles.length > 0
                  ? roles.map(r => <RoleBadge key={r} role={r} />)
                  : <span style={{ color: C.muted }}>none</span>}
              </div>
            </div>
          </div>

          {meResult?.ok && (
            <div style={{
              background: C.surface, border: `1px solid ${C.border}`,
              borderRadius: '8px', padding: '1.25rem', overflow: 'hidden',
            }}>
              <div style={{
                fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
                letterSpacing: '0.08em', color: C.muted, marginBottom: '1rem',
              }}>
                Token Claims — /api/me
              </div>
              <pre style={{
                fontSize: '0.72rem', color: C.muted, margin: 0,
                overflowX: 'auto', whiteSpace: 'pre-wrap',
              }}>
                {JSON.stringify(meResult.data, null, 2)}
              </pre>
            </div>
          )}
        </div>

        {/* ── Role-protected endpoint tests ───────────────────────────────── */}
        <div style={{
          fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: C.muted, marginBottom: '0.75rem',
        }}>
          Role-Protected Endpoints
        </div>
        <div style={{
          display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)',
          gap: '1rem', marginBottom: '1.5rem',
        }}>
          {ENDPOINTS.map(ep => (
            <EndpointCard key={ep.key} {...ep} result={endpointResults[ep.key]} />
          ))}
        </div>

        {/* ── How it works ───────────────────────────────────────────────── */}
        <div style={{
          padding: '1rem 1.25rem',
          background: '#1a2744', border: '1px solid #2a4a8a',
          borderRadius: '8px', fontSize: '0.82rem', color: '#90cdf4', lineHeight: 1.7,
        }}>
          <strong>Command flow:</strong> When an operator or admin submits a setpoint,
          the frontend sends <code>POST /api/controls/hvac/main/setpoint</code> with a
          Bearer token. FastAPI validates the JWT, checks the role, validates the temperature
          range (10–35 °C), then publishes to <code>basis/hvac/main/command</code> via MQTT.
          The simulator receives the command, validates it again, updates its internal setpoint,
          and the next telemetry ticks show <code>current_temperature</code> drifting toward
          the new target. Viewers see this card locked — the API would return 403 regardless.
          Stage 5 will add an audit log recording every command and who issued it.
        </div>

      </div>
    </div>
  )
}
