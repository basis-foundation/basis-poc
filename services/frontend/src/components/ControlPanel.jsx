/**
 * Basis Foundation — HVAC Control Panel
 * Stage 4: Operator/admin-only setpoint control with live feedback.
 *
 * Authorization logic (mirrors the API):
 *   viewer   → locked panel, clear explanation
 *   operator → full control
 *   admin    → full control
 *
 * Command flow:
 *   User adjusts slider → clicks "Apply" → POST /api/controls/hvac/main/setpoint
 *   → API validates JWT + role → publishes MQTT command
 *   → Simulator drifts current_temperature toward new target
 *   → Telemetry cards update automatically via WebSocket
 */

import { useState } from 'react'
import { hasRole } from '../auth/keycloak'
import { apiFetch } from '../api/client'

// ── Constants ─────────────────────────────────────────────────────────────────
const TEMP_MIN  = 10
const TEMP_MAX  = 35
const TEMP_STEP = 0.5

// ── Colours (match app palette) ───────────────────────────────────────────────
const C = {
  surface:  '#1a202c',
  border:   '#2d3748',
  text:     '#e2e8f0',
  muted:    '#718096',
  accent:   '#63b3ed',
  green:    '#68d391',
  greenBg:  '#1c4532',
  red:      '#fc8181',
  redBg:    '#742a2a',
  yellow:   '#f6e05e',
  yellowBg: '#744210',
  blue:     '#63b3ed',
  blueBg:   '#1a365d',
}

// ── Status feedback config ────────────────────────────────────────────────────
// `text` may be a string or a function(result) → string for dynamic messages.
const STATUS_CFG = {
  idle:     { color: C.muted,   text: '' },
  sending:  { color: C.accent,  text: 'Sending command…' },
  sent:     { color: C.green,   text: (r) => `✓ Command sent — ${r?.data?.mqtt_topic ?? 'MQTT'} will deliver setpoint to simulator.` },
  error:    { color: C.red,     text: (r) => r?.networkError
    ? `✗ Network error — could not reach API. (${r.networkError})`
    : `✗ Command failed (HTTP ${r?.status ?? '?'}). Check API logs.` },
  rejected: { color: C.red,     text: '✗ Access denied (403). This user does not have operator or admin role.' },
}

// ── Locked view (viewer role) ─────────────────────────────────────────────────
function LockedPanel({ currentSetpoint }) {
  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: '8px', padding: '1.25rem',
    }}>
      <SectionLabel />
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem',
        padding: '0.75rem 1rem',
        background: '#1a2744', border: `1px solid #2a4a8a`,
        borderRadius: '6px',
        fontSize: '0.85rem', color: '#90cdf4',
      }}>
        <span style={{ fontSize: '1.1rem' }}>🔒</span>
        <span>
          Control access requires the <strong>operator</strong> or <strong>admin</strong> role.
          Current setpoint: <strong>{currentSetpoint != null ? `${currentSetpoint.toFixed(1)} °C` : '—'}</strong>
        </span>
      </div>
    </div>
  )
}

function SectionLabel() {
  return (
    <div style={{
      fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
      letterSpacing: '0.08em', color: C.muted, marginBottom: '1rem',
    }}>
      HVAC Control — Main Zone
    </div>
  )
}

// ── Temperature display ───────────────────────────────────────────────────────
function TempDisplay({ value, label, muted = false }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{
        fontSize: '1.6rem', fontWeight: 700, lineHeight: 1,
        color: muted ? C.muted : C.text,
      }}>
        {value != null ? value.toFixed(1) : '—'}
        <span style={{ fontSize: '0.9rem', fontWeight: 400 }}> °C</span>
      </div>
      <div style={{ fontSize: '0.7rem', color: C.muted, marginTop: '2px' }}>{label}</div>
    </div>
  )
}

// ── Control panel ─────────────────────────────────────────────────────────────
export default function ControlPanel({ hvacData }) {
  const canControl = hasRole('operator') || hasRole('admin')

  const currentSetpoint = hvacData?.target_temperature ?? null
  const currentTemp     = hvacData?.current_temperature ?? null

  // Initialise the slider at the live setpoint, or a sensible default
  const [target, setTarget] = useState(() =>
    currentSetpoint != null ? currentSetpoint : 21.0
  )
  const [cmdStatus, setCmdStatus] = useState('idle')
  const [lastResult, setLastResult] = useState(null)

  if (!canControl) {
    return <LockedPanel currentSetpoint={currentSetpoint} />
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setCmdStatus('sending')
    setLastResult(null)

    const result = await apiFetch('/api/controls/hvac/main/setpoint', {
      method: 'POST',
      body: JSON.stringify({ target_temperature: target }),
    })

    setLastResult(result)
    if (result.ok) {
      setCmdStatus('sent')
    } else if (result.status === 403) {
      setCmdStatus('rejected')
    } else {
      setCmdStatus('error')
    }

    // Auto-clear status after 6 seconds (extra time to read error details)
    setTimeout(() => setCmdStatus('idle'), 6000)
  }

  const isSending   = cmdStatus === 'sending'
  const statusCfg   = STATUS_CFG[cmdStatus]
  const statusText  = typeof statusCfg.text === 'function'
    ? statusCfg.text(lastResult)
    : statusCfg.text

  // Colour the slider track based on temperature intent
  const sliderColor =
    target < 19 ? C.blue :    // cooling
    target > 23 ? C.red  :    // warm
    C.green                   // comfortable

  return (
    <div style={{
      background: C.surface, border: `1px solid ${C.border}`,
      borderRadius: '8px', padding: '1.25rem',
    }}>
      <SectionLabel />

      <form onSubmit={handleSubmit}>

        {/* Current vs target display row */}
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr auto 1fr',
          alignItems: 'center', gap: '1rem', marginBottom: '1.25rem',
        }}>
          <TempDisplay value={currentTemp}     label="Current" muted />
          <span style={{ color: C.border, fontSize: '1.2rem' }}>→</span>
          <TempDisplay value={target}          label="New setpoint" />
        </div>

        {/* Slider */}
        <div style={{ marginBottom: '0.75rem' }}>
          <input
            type="range"
            min={TEMP_MIN}
            max={TEMP_MAX}
            step={TEMP_STEP}
            value={target}
            disabled={isSending}
            onChange={e => setTarget(parseFloat(e.target.value))}
            style={{
              width: '100%', accentColor: sliderColor,
              cursor: isSending ? 'not-allowed' : 'pointer',
            }}
          />
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            fontSize: '0.65rem', color: C.muted,
          }}>
            <span>{TEMP_MIN} °C</span>
            <span>{TEMP_MAX} °C</span>
          </div>
        </div>

        {/* Fine-tune number input + submit */}
        <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'center' }}>
          <input
            type="number"
            min={TEMP_MIN}
            max={TEMP_MAX}
            step={TEMP_STEP}
            value={target}
            disabled={isSending}
            onChange={e => {
              const v = parseFloat(e.target.value)
              if (!isNaN(v) && v >= TEMP_MIN && v <= TEMP_MAX) setTarget(v)
            }}
            style={{
              width: '80px', padding: '0.35rem 0.5rem',
              background: '#0f1117', border: `1px solid ${C.border}`,
              borderRadius: '6px', color: C.text, fontSize: '0.9rem',
              textAlign: 'center',
            }}
          />
          <span style={{ fontSize: '0.8rem', color: C.muted }}>°C</span>

          <button
            type="submit"
            disabled={isSending}
            style={{
              marginLeft: 'auto',
              padding: '0.4rem 1.25rem',
              background: isSending ? C.border : sliderColor,
              border: 'none', borderRadius: '6px',
              color: '#0f1117', fontWeight: 700, fontSize: '0.85rem',
              cursor: isSending ? 'not-allowed' : 'pointer',
              transition: 'background 0.2s',
            }}
          >
            {isSending ? 'Sending…' : 'Apply Setpoint'}
          </button>
        </div>

        {/* Status feedback */}
        {cmdStatus !== 'idle' && (
          <div style={{
            marginTop: '0.75rem', fontSize: '0.8rem',
            color: statusCfg.color, lineHeight: 1.5,
          }}>
            {statusText}
          </div>
        )}

      </form>
    </div>
  )
}
