/**
 * BASIS — Operator Console
 * Authenticated frontend for the BASIS OT Identity Platform.
 *
 * Authentication + telemetry logic is preserved exactly from Stage 9.
 * The layout has been restructured into a sidebar-navigation shell
 * with four views: Dashboard, Architecture, Access Control, Identity.
 */

import { useState, useEffect, useRef } from 'react'
import keycloak, { initKeycloak, getRoles } from './auth/keycloak'
import { apiFetch } from './api/client'
import { useTelemetry } from './ws/telemetry'
import TelemetryDashboard, { TOPIC_HVAC } from './components/TelemetryDashboard'
import ControlPanel from './components/ControlPanel'
import Sidebar from './components/Sidebar'
import ArchitectureView from './components/ArchitectureView'
import AccessControlView from './components/AccessControlView'
import IdentityView from './components/IdentityView'
import AuditView from './components/AuditView'

// ── WebSocket URL ──────────────────────────────────────────────────────────────
// Always use the page's own origin so traffic routes through Vite's /ws proxy.
// This is critical in GitHub Codespaces where each forwarded port has its own
// tunnel authentication cookie — direct cross-port WebSocket connections fail.
const WS_BASE_URL = window.location.origin.replace(/^http/, 'ws')

// ── Palette ────────────────────────────────────────────────────────────────────
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
  purple:  '#b794f4',
}

// ── Loading / error screens ───────────────────────────────────────────────────
function LoadingScreen({ attempt, maxAttempts }) {
  const isRetrying = attempt > 1
  return (
    <div style={{
      minHeight: '100vh',
      background: C.bg,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '1.25rem',
      fontFamily: 'system-ui, sans-serif',
      color: C.text,
    }}>
      {/* Logo */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.65rem', marginBottom: '0.25rem',
      }}>
        <div style={{
          width: '34px', height: '34px',
          background: 'linear-gradient(135deg, #1e3a6e 0%, #4a2d7c 100%)',
          borderRadius: '8px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1rem',
          boxShadow: '0 0 16px rgba(99,179,237,0.15)',
        }}>⬡</div>
        <span style={{ fontSize: '1.1rem', fontWeight: 800, letterSpacing: '0.08em' }}>BASIS</span>
      </div>

      <div style={{
        width: '36px', height: '36px',
        border: `2px solid ${C.border}`,
        borderTop: `2px solid ${C.accent}`,
        borderRadius: '50%',
        animation: 'spin 1s linear infinite',
      }} />

      <div style={{ textAlign: 'center' }}>
        <div style={{ fontSize: '0.9rem', fontWeight: 600 }}>
          {isRetrying ? 'Services are starting, please wait…' : 'Connecting to Keycloak…'}
        </div>
        <div style={{ fontSize: '0.78rem', color: C.muted, marginTop: '0.3rem' }}>
          {isRetrying
            ? `Attempt ${attempt} of ${maxAttempts} — containers may still be initializing`
            : 'Establishing authenticated session'}
        </div>
      </div>

      {isRetrying && (
        <div style={{
          padding: '0.5rem 1rem',
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: '6px',
          fontSize: '0.73rem',
          color: C.muted,
        }}>
          Keycloak typically takes 20–30 s on first boot
        </div>
      )}

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

function AuthErrorScreen() {
  return (
    <div style={{
      minHeight: '100vh',
      background: C.bg,
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      gap: '0.75rem',
      fontFamily: 'system-ui, sans-serif',
      color: C.text,
      padding: '2rem',
    }}>
      <div style={{ fontSize: '2.5rem', marginBottom: '0.25rem' }}>⚠</div>
      <div style={{ fontSize: '1.1rem', fontWeight: 700, color: C.red }}>
        Authentication Failed
      </div>
      <div style={{
        fontSize: '0.82rem', color: C.muted,
        maxWidth: '440px', textAlign: 'center', lineHeight: 1.65,
      }}>
        Could not connect to Keycloak after several attempts. Make sure all
        services are running and the Keycloak URL is reachable from your browser.
      </div>
      <div style={{
        marginTop: '0.75rem',
        padding: '0.6rem 1rem',
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '6px',
        fontSize: '0.78rem',
        color: C.muted,
        fontFamily: 'monospace',
      }}>
        docker compose up --build
      </div>
      <button
        onClick={() => window.location.reload()}
        style={{
          marginTop: '0.25rem',
          padding: '0.45rem 1.25rem',
          background: 'transparent',
          border: `1px solid ${C.border}`,
          borderRadius: '6px',
          color: C.accent,
          fontSize: '0.78rem',
          cursor: 'pointer',
        }}
      >
        Retry
      </button>
    </div>
  )
}

// ── Dashboard view (inline — lives in App to access shared state cleanly) ─────
function DashboardView({ telemetry, wsStatus, hvacData }) {
  return (
    <div>
      <PageHeader
        title="Operator Dashboard"
        subtitle="Live telemetry from simulated OT devices in the demo environment. Data flows: MQTT Broker → FastAPI → WebSocket → this console."
      />

      <TelemetryDashboard telemetry={telemetry} wsStatus={wsStatus} />

      <div style={{ marginTop: '1.25rem' }}>
        <ControlPanel hvacData={hvacData} />
      </div>

      {/* Command flow annotation */}
      <div style={{
        marginTop: '1.5rem',
        padding: '1rem 1.25rem',
        background: 'rgba(26,39,68,0.5)',
        border: '1px solid #2a4a8a',
        borderRadius: '8px',
        fontSize: '0.79rem',
        color: '#90cdf4',
        lineHeight: 1.75,
      }}>
        <strong>Command flow:</strong> When an operator or admin submits a setpoint, the frontend POSTs to{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
          /api/controls/hvac/main/setpoint
        </code>{' '}
        with a Bearer token. FastAPI validates the JWT, checks the role, validates the temperature
        range (10–35 °C), then publishes to the MQTT broker. The simulator receives the command,
        updates its internal setpoint, and subsequent telemetry ticks show{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
          current_temperature
        </code>{' '}
        drifting toward the new target. Viewers see the control panel locked — the API returns 403 regardless.
      </div>
    </div>
  )
}

// ── Shared page heading ───────────────────────────────────────────────────────
function PageHeader({ title, subtitle }) {
  return (
    <div style={{ marginBottom: '1.75rem' }}>
      <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.4rem', color: C.text }}>
        {title}
      </h2>
      {subtitle && (
        <p style={{ fontSize: '0.83rem', color: C.muted, margin: 0, lineHeight: 1.65, maxWidth: '700px' }}>
          {subtitle}
        </p>
      )}
    </div>
  )
}

// ── App ────────────────────────────────────────────────────────────────────────
export default function App() {
  const [authState, setAuthState]     = useState('loading')
  const [activeView, setActiveView]   = useState('dashboard')
  const [meResult, setMeResult]       = useState(null)
  const [endpointResults, setEndpointResults] = useState({
    viewer: null, operator: null, admin: null,
  })
  const [retryAttempt, setRetryAttempt] = useState(1)
  const MAX_RETRIES = 8
  const RETRY_DELAY_MS = 5000
  const didInit = useRef(false)

  // Token accessors passed to the telemetry hook so each connect uses a fresh JWT.
  const getToken     = () => keycloak.token ?? null
  const refreshToken = () => keycloak.updateToken(5)

  // Single shared WebSocket connection — both TelemetryDashboard and ControlPanel
  // read from the same telemetry state object rather than opening separate sockets.
  const { telemetry, wsStatus } = useTelemetry(WS_BASE_URL, getToken, refreshToken)

  // ── Keycloak init with startup retry ─────────────────────────────────────
  // Codespaces: docker-proxy binds the port before Keycloak is ready, so the
  // browser may open before services finish initialising. We retry up to
  // MAX_RETRIES times with RETRY_DELAY_MS between attempts rather than
  // immediately showing an error screen.
  useEffect(() => {
    if (didInit.current) return
    didInit.current = true

    let attempt = 1

    const tryInit = () => {
      setRetryAttempt(attempt)
      initKeycloak()
        .then(authenticated => {
          setAuthState(authenticated ? 'authenticated' : 'error')
        })
        .catch(err => {
          console.warn(`Keycloak init attempt ${attempt} failed:`, err)
          if (attempt < MAX_RETRIES) {
            attempt++
            setTimeout(tryInit, RETRY_DELAY_MS)
          } else {
            console.error('Keycloak init failed after max retries')
            setAuthState('error')
          }
        })
    }

    tryInit()
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

  // ── Token refresh heartbeat (every 30s) ───────────────────────────────────
  useEffect(() => {
    if (authState !== 'authenticated') return
    const id = setInterval(() => {
      keycloak.updateToken(60).catch(() => keycloak.logout())
    }, 30_000)
    return () => clearInterval(id)
  }, [authState])

  // ── Loading / error states ────────────────────────────────────────────────
  if (authState === 'loading') return <LoadingScreen attempt={retryAttempt} maxAttempts={MAX_RETRIES} />
  if (authState === 'error')   return <AuthErrorScreen />

  // ── Authenticated layout ──────────────────────────────────────────────────
  const username = keycloak.tokenParsed?.preferred_username ?? '—'
  const email    = keycloak.tokenParsed?.email ?? ''
  const roles    = getRoles().filter(r => ['viewer', 'operator', 'admin'].includes(r))
  const hvacData = telemetry[TOPIC_HVAC] ?? null

  return (
    <div style={{
      display: 'flex',
      minHeight: '100vh',
      background: C.bg,
      fontFamily: 'system-ui, -apple-system, sans-serif',
      fontSize: '14px',
      lineHeight: 1.6,
      color: C.text,
    }}>

      {/* ── Sidebar ───────────────────────────────────────────────────── */}
      <Sidebar
        activeView={activeView}
        onNavigate={setActiveView}
        wsStatus={wsStatus}
        username={username}
        roles={roles}
        onLogout={() => keycloak.logout()}
      />

      {/* ── Main content ──────────────────────────────────────────────── */}
      <main style={{
        flex: 1,
        minWidth: 0,
        overflowY: 'auto',
        padding: '2rem 2.5rem',
      }}>

        {activeView === 'dashboard' && (
          <DashboardView
            telemetry={telemetry}
            wsStatus={wsStatus}
            hvacData={hvacData}
          />
        )}

        {activeView === 'architecture' && (
          <ArchitectureView />
        )}

        {activeView === 'access-control' && (
          <AccessControlView
            endpointResults={endpointResults}
            roles={roles}
          />
        )}

        {activeView === 'identity' && (
          <IdentityView
            username={username}
            email={email}
            roles={roles}
            meResult={meResult}
            keycloak={keycloak}
          />
        )}

        {activeView === 'audit' && (
          <AuditView roles={roles} />
        )}

      </main>
    </div>
  )
}
