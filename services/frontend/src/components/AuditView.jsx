/**
 * BASIS — Audit Trail View
 * Admin-only view of the platform audit log.
 * Calls GET /api/audit with Bearer token via apiFetch().
 * Non-admin users see an educational access-denied panel.
 */

import { useState, useEffect, useCallback } from 'react'
import { apiFetch } from '../api/client'

const C = {
  bg:       '#0f1117',
  surface:  '#1a202c',
  surfaceHi:'#202635',
  border:   '#2d3748',
  borderHi: '#3d4f6e',
  text:     '#e2e8f0',
  muted:    '#718096',
  mutedHi:  '#a0aec0',
  accent:   '#63b3ed',
  green:    '#68d391',
  greenBg:  '#0d2318',
  red:      '#fc8181',
  redBg:    '#2d1010',
  yellow:   '#f6e05e',
  yellowBg: '#2d2408',
  orange:   '#f6ad55',
  purple:   '#b794f4',
}

const OUTCOME_COLORS = {
  allowed: { color: C.green,  bg: 'rgba(28,69,50,0.45)',   border: '#276749' },
  denied:  { color: C.red,    bg: 'rgba(45,16,16,0.55)',   border: '#9b2c2c' },
  error:   { color: C.yellow, bg: 'rgba(45,36,8,0.55)',    border: '#975a16' },
}

const ACTION_LABELS = {
  'write:hvac:setpoint':    'HVAC Setpoint',
  'write:modbus:setpoint':  'Modbus Setpoint',
  'subscribe:telemetry':    'Subscribe Telemetry',
  'disconnect:telemetry':   'Disconnect Telemetry',
  'read:audit:log':         'Read Audit Log',
  'read:resources':         'Read Resources',
  'read:api:viewer':        'Viewer API',
  'read:api:operator':      'Operator API',
  'read:api:admin':         'Admin API',
}

function formatTimestamp(iso) {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) +
      ' ' + d.toLocaleDateString([], { month: 'short', day: 'numeric' })
  } catch { return iso }
}

function OutcomePill({ outcome }) {
  const cfg = OUTCOME_COLORS[outcome] ?? { color: C.muted, bg: C.surface, border: C.border }
  return (
    <span style={{
      fontSize: '0.63rem',
      fontWeight: 700,
      textTransform: 'uppercase',
      letterSpacing: '0.06em',
      color: cfg.color,
      background: cfg.bg,
      border: `1px solid ${cfg.border}`,
      padding: '1px 7px',
      borderRadius: '9px',
      whiteSpace: 'nowrap',
    }}>
      {outcome ?? '—'}
    </span>
  )
}

function AuditEventRow({ event, index }) {
  const [expanded, setExpanded] = useState(false)
  const isEven = index % 2 === 0
  const actionLabel = ACTION_LABELS[event.action] ?? event.action

  return (
    <>
      <tr
        onClick={() => setExpanded(e => !e)}
        style={{
          background: isEven ? 'transparent' : 'rgba(255,255,255,0.018)',
          cursor: 'pointer',
          transition: 'background 0.1s',
        }}
        onMouseEnter={e => { e.currentTarget.style.background = 'rgba(99,179,237,0.05)' }}
        onMouseLeave={e => { e.currentTarget.style.background = isEven ? 'transparent' : 'rgba(255,255,255,0.018)' }}
      >
        {/* Timestamp */}
        <td style={{ padding: '0.5rem 0.75rem', fontSize: '0.71rem', color: C.muted, whiteSpace: 'nowrap', fontFamily: 'monospace' }}>
          {formatTimestamp(event.timestamp)}
        </td>

        {/* Subject */}
        <td style={{ padding: '0.5rem 0.75rem', fontSize: '0.75rem', color: C.text, fontWeight: 500 }}>
          {event.subject_name ?? event.subject_id ?? '—'}
          {event.subject_roles?.length > 0 && (
            <span style={{ marginLeft: '0.4rem', fontSize: '0.62rem', color: C.muted }}>
              ({event.subject_roles.join(', ')})
            </span>
          )}
        </td>

        {/* Action */}
        <td style={{ padding: '0.5rem 0.75rem', fontSize: '0.73rem', color: C.accent, fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
          {actionLabel}
        </td>

        {/* Resource */}
        <td style={{ padding: '0.5rem 0.75rem', fontSize: '0.72rem', color: C.mutedHi }}>
          {event.resource_id ?? '—'}
        </td>

        {/* Outcome */}
        <td style={{ padding: '0.5rem 0.75rem' }}>
          <OutcomePill outcome={event.outcome} />
        </td>

        {/* Expand indicator */}
        <td style={{ padding: '0.5rem 0.5rem', textAlign: 'right' }}>
          <span style={{ fontSize: '0.6rem', color: C.muted, opacity: 0.6 }}>
            {expanded ? '▲' : '▼'}
          </span>
        </td>
      </tr>

      {expanded && (
        <tr style={{ background: 'rgba(26,32,48,0.8)' }}>
          <td colSpan={6} style={{ padding: '0.75rem 1rem 0.85rem', borderBottom: `1px solid ${C.border}` }}>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))',
              gap: '0.5rem 1.25rem',
              fontSize: '0.72rem',
            }}>
              {[
                ['Event ID',    event.event_id],
                ['Action',      event.action],
                ['Endpoint',    event.endpoint],
                ['Resource type', event.resource_type],
                ['Subject type', event.subject_type],
                ['Reason',      event.reason],
              ].map(([label, val]) => val ? (
                <div key={label}>
                  <span style={{ color: C.muted }}>{label}: </span>
                  <span style={{ color: C.mutedHi, fontFamily: 'monospace' }}>{val}</span>
                </div>
              ) : null)}
            </div>
            {event.detail && Object.keys(event.detail).length > 0 && (
              <div style={{
                marginTop: '0.6rem',
                padding: '0.45rem 0.65rem',
                background: C.surface,
                border: `1px solid ${C.border}`,
                borderRadius: '5px',
                fontSize: '0.7rem',
                color: C.mutedHi,
                fontFamily: 'monospace',
              }}>
                {JSON.stringify(event.detail, null, 2)}
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

// ── Access-denied panel for non-admin users ────────────────────────────────────
function AccessDeniedPanel({ roles }) {
  const roleNames = roles.join(', ') || 'none'
  return (
    <div style={{ maxWidth: '620px' }}>

      {/* Lock icon + header */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        gap: '1rem',
        padding: '1.5rem',
        background: 'rgba(45,16,16,0.4)',
        border: `1px solid #9b2c2c`,
        borderRadius: '10px',
        marginBottom: '1.5rem',
      }}>
        <div style={{
          width: '42px', height: '42px',
          background: 'rgba(252,129,129,0.1)',
          border: '1px solid #9b2c2c',
          borderRadius: '8px',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          fontSize: '1.25rem',
          flexShrink: 0,
        }}>
          ⊘
        </div>
        <div>
          <div style={{ fontSize: '0.95rem', fontWeight: 700, color: C.red, marginBottom: '0.2rem' }}>
            Access Denied
          </div>
          <div style={{ fontSize: '0.78rem', color: C.muted, lineHeight: 1.55 }}>
            Your current role{roles.length > 1 ? 's' : ''} (<strong style={{ color: C.mutedHi }}>{roleNames}</strong>) do not include the{' '}
            <code style={{ background: '#2d1010', padding: '1px 5px', borderRadius: '3px', fontFamily: 'monospace', color: C.red }}>
              admin
            </code>{' '}
            realm role required to access the audit log.
          </div>
        </div>
      </div>

      {/* Educational explanation */}
      <div style={{
        padding: '1.1rem 1.25rem',
        background: 'rgba(26,39,68,0.5)',
        border: '1px solid #2a4a8a',
        borderRadius: '8px',
        fontSize: '0.79rem',
        color: '#90cdf4',
        lineHeight: 1.75,
        marginBottom: '1.25rem',
      }}>
        <div style={{ fontWeight: 700, marginBottom: '0.5rem', fontSize: '0.83rem' }}>
          Why is the audit log admin-only?
        </div>
        <p style={{ margin: '0 0 0.5rem' }}>
          The audit log records every authorization decision the platform makes — who tried to do what,
          on which resource, and whether it was allowed or denied. This data is sensitive: it reveals
          user behavior patterns, active sessions, and potential attack attempts.
        </p>
        <p style={{ margin: 0 }}>
          The FastAPI backend enforces this with the{' '}
          <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
            read:audit:log
          </code>{' '}
          action check. Even if a viewer or operator sends a request to{' '}
          <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>
            GET /api/audit
          </code>{' '}
          with a valid Bearer token, the API returns{' '}
          <strong>HTTP 403 Forbidden</strong> — the role check fires before any data is read.
        </p>
      </div>

      {/* Try it callout */}
      <div style={{
        padding: '0.85rem 1.1rem',
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '8px',
        fontSize: '0.77rem',
        color: C.muted,
        lineHeight: 1.65,
      }}>
        <span style={{ color: C.mutedHi, fontWeight: 600 }}>To see the audit log: </span>
        log out and sign in as{' '}
        <code style={{ background: '#0f1520', padding: '1px 5px', borderRadius: '3px', fontFamily: 'monospace', color: C.accent }}>
          carol
        </code>{' '}
        (password: <code style={{ background: '#0f1520', padding: '1px 5px', borderRadius: '3px', fontFamily: 'monospace', color: C.accent }}>demo123</code>),
        who holds the <strong style={{ color: C.purple }}>admin</strong> role.
        Every action taken while logged in as alice or bob will appear as an entry in the log.
      </div>
    </div>
  )
}

// ── Filter bar ────────────────────────────────────────────────────────────────
function FilterBar({ outcomeFilter, setOutcomeFilter, limitFilter, setLimitFilter, onRefresh, loading }) {
  const selectStyle = {
    background: C.surface,
    border: `1px solid ${C.border}`,
    borderRadius: '5px',
    color: C.text,
    fontSize: '0.75rem',
    padding: '0.3rem 0.5rem',
    cursor: 'pointer',
  }

  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      gap: '0.75rem',
      flexWrap: 'wrap',
      marginBottom: '1rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <span style={{ fontSize: '0.7rem', color: C.muted }}>Outcome:</span>
        <select
          value={outcomeFilter}
          onChange={e => setOutcomeFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="">All</option>
          <option value="allowed">Allowed</option>
          <option value="denied">Denied</option>
          <option value="error">Error</option>
        </select>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
        <span style={{ fontSize: '0.7rem', color: C.muted }}>Limit:</span>
        <select
          value={limitFilter}
          onChange={e => setLimitFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="25">25</option>
          <option value="50">50</option>
          <option value="100">100</option>
          <option value="200">200</option>
        </select>
      </div>

      <button
        onClick={onRefresh}
        disabled={loading}
        style={{
          background: 'transparent',
          border: `1px solid ${C.border}`,
          borderRadius: '5px',
          color: loading ? C.muted : C.accent,
          fontSize: '0.75rem',
          padding: '0.3rem 0.75rem',
          cursor: loading ? 'not-allowed' : 'pointer',
          display: 'flex',
          alignItems: 'center',
          gap: '0.35rem',
          transition: 'border-color 0.1s, color 0.1s',
        }}
        onMouseEnter={e => { if (!loading) { e.currentTarget.style.borderColor = C.accent } }}
        onMouseLeave={e => { e.currentTarget.style.borderColor = C.border }}
      >
        <span style={{ fontSize: '0.7rem', display: 'inline-block', animation: loading ? 'spin 1s linear infinite' : 'none' }}>
          ↻
        </span>
        Refresh
      </button>

      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
    </div>
  )
}

// ── Admin audit table ─────────────────────────────────────────────────────────
function AdminAuditPanel() {
  const [events, setEvents]             = useState([])
  const [count, setCount]               = useState(null)
  const [loading, setLoading]           = useState(false)
  const [error, setError]               = useState(null)
  const [outcomeFilter, setOutcomeFilter] = useState('')
  const [limitFilter, setLimitFilter]   = useState('50')

  const fetchAudit = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams({ limit: limitFilter })
      if (outcomeFilter) params.set('outcome', outcomeFilter)
      const result = await apiFetch(`/api/audit?${params}`)
      if (!result.ok) {
        setError(`API returned ${result.status}`)
      } else {
        setEvents(result.data?.events ?? [])
        setCount(result.data?.count ?? 0)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [outcomeFilter, limitFilter])

  useEffect(() => { fetchAudit() }, [fetchAudit])

  return (
    <div>
      {/* Summary bar */}
      <div style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '0.75rem',
        flexWrap: 'wrap',
        gap: '0.5rem',
      }}>
        <FilterBar
          outcomeFilter={outcomeFilter}
          setOutcomeFilter={setOutcomeFilter}
          limitFilter={limitFilter}
          setLimitFilter={setLimitFilter}
          onRefresh={fetchAudit}
          loading={loading}
        />
        {count !== null && (
          <span style={{ fontSize: '0.72rem', color: C.muted }}>
            {loading ? 'Loading…' : `${events.length} event${events.length !== 1 ? 's' : ''}`}
          </span>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div style={{
          padding: '0.75rem 1rem',
          background: C.redBg,
          border: `1px solid #9b2c2c`,
          borderRadius: '7px',
          fontSize: '0.77rem',
          color: C.red,
          marginBottom: '1rem',
        }}>
          Failed to load audit events: {error}
        </div>
      )}

      {/* Empty state */}
      {!loading && !error && events.length === 0 && (
        <div style={{
          padding: '2rem',
          textAlign: 'center',
          color: C.muted,
          fontSize: '0.8rem',
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: '8px',
        }}>
          No audit events found{outcomeFilter ? ` with outcome "${outcomeFilter}"` : ''}.
          Try triggering some actions on the Dashboard.
        </div>
      )}

      {/* Table */}
      {events.length > 0 && (
        <div style={{
          background: C.surface,
          border: `1px solid ${C.border}`,
          borderRadius: '8px',
          overflow: 'hidden',
        }}>
          <table style={{
            width: '100%',
            borderCollapse: 'collapse',
            fontSize: '0.77rem',
          }}>
            <thead>
              <tr style={{ borderBottom: `1px solid ${C.border}`, background: 'rgba(255,255,255,0.025)' }}>
                {['Timestamp', 'Subject', 'Action', 'Resource', 'Outcome', ''].map(h => (
                  <th key={h} style={{
                    padding: '0.5rem 0.75rem',
                    textAlign: 'left',
                    fontSize: '0.64rem',
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.08em',
                    color: C.muted,
                    whiteSpace: 'nowrap',
                  }}>
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {events.map((ev, i) => (
                <AuditEventRow key={ev.event_id ?? i} event={ev} index={i} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Policy note */}
      <div style={{
        marginTop: '1.5rem',
        padding: '0.9rem 1.1rem',
        background: 'rgba(26,39,68,0.45)',
        border: '1px solid #2a4a8a',
        borderRadius: '7px',
        fontSize: '0.76rem',
        color: '#90cdf4',
        lineHeight: 1.7,
      }}>
        <strong>Persistence:</strong> Events are written to SQLite via{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>DualAuditStore</code>.
        The{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>StdoutAuditStore</code>{' '}
        logs to the container console and the{' '}
        <code style={{ background: '#0f1a2d', padding: '0 4px', borderRadius: '3px', fontFamily: 'monospace' }}>SqliteAuditStore</code>{' '}
        persists to disk. Every protected route emits an event on both success and failure, giving a complete authorization history.
        Click any row to expand the full event detail.
      </div>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function AuditView({ roles }) {
  const isAdmin = roles.includes('admin')

  return (
    <div>

      {/* Page header */}
      <div style={{ marginBottom: '1.75rem' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.4rem' }}>
          <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: 0, color: C.text }}>
            Audit Trail
          </h2>
          <span style={{
            fontSize: '0.63rem',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.06em',
            color: C.purple,
            background: 'rgba(68,51,122,0.45)',
            border: '1px solid rgba(183,148,244,0.3)',
            padding: '1px 8px',
            borderRadius: '9px',
          }}>
            admin only
          </span>
        </div>
        <p style={{ fontSize: '0.83rem', color: C.muted, margin: 0, lineHeight: 1.65, maxWidth: '680px' }}>
          Every authorization decision — allowed or denied — is recorded in the platform audit log.
          Requires the <code style={{ fontFamily: 'monospace', color: C.accent, background: 'rgba(99,179,237,0.08)', padding: '1px 4px', borderRadius: '3px' }}>read:audit:log</code> action,
          which is granted exclusively to the <strong style={{ color: C.purple }}>admin</strong> role.
        </p>
      </div>

      {isAdmin ? <AdminAuditPanel /> : <AccessDeniedPanel roles={roles} />}

    </div>
  )
}
