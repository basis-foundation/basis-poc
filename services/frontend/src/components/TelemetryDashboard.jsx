/**
 * Basis Foundation — Live Telemetry Dashboard
 * Stage 4: accepts { telemetry, wsStatus } as props (state lifted to App.jsx
 * so ControlPanel can share the same WebSocket data without a second connection).
 */

// ── Constants ─────────────────────────────────────────────────────────────────
export const TOPIC_HVAC      = 'basis/hvac/main/telemetry'
export const TOPIC_CO2       = 'basis/sensors/co2/telemetry'
export const TOPIC_OCCUPANCY = 'basis/sensors/occupancy/telemetry'

// ── Colours ───────────────────────────────────────────────────────────────────
const C = {
  bg:         '#0f1117',
  surface:    '#1a202c',
  border:     '#2d3748',
  text:       '#e2e8f0',
  muted:      '#718096',
  green:      '#68d391',
  greenBg:    '#1c4532',
  yellow:     '#f6e05e',
  yellowBg:   '#744210',
  red:        '#fc8181',
  redBg:      '#742a2a',
  blue:       '#63b3ed',
  blueBg:     '#1a365d',
  orange:     '#f6ad55',
  orangeBg:   '#7b341e',
}

// ── Shared styles ─────────────────────────────────────────────────────────────
const card = {
  background:   C.surface,
  border:       `1px solid ${C.border}`,
  borderRadius: '8px',
  padding:      '1.25rem',
}

const label = {
  fontSize:      '0.7rem',
  fontWeight:    700,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color:         C.muted,
  marginBottom:  '1rem',
}

const bigNumber = {
  fontSize:   '2.2rem',
  fontWeight: 700,
  lineHeight: 1,
}

const metaRow = {
  display:    'flex',
  gap:        '0.5rem',
  marginTop:  '0.75rem',
  flexWrap:   'wrap',
}

// ── Status badge ──────────────────────────────────────────────────────────────
function Badge({ text, bg, color }) {
  return (
    <span style={{
      background: bg, color,
      padding: '2px 8px', borderRadius: '10px',
      fontSize: '0.7rem', fontWeight: 700,
    }}>
      {text}
    </span>
  )
}

// ── Skeleton placeholder ──────────────────────────────────────────────────────
function Skeleton({ height = '1rem', width = '60%' }) {
  return (
    <div style={{
      height, width, borderRadius: '4px',
      background: C.border,
      animation: 'pulse 1.5s ease-in-out infinite',
    }} />
  )
}

// ── HVAC Card ─────────────────────────────────────────────────────────────────
function HVACCard({ data }) {
  if (!data) {
    return (
      <div style={card}>
        <div style={label}>HVAC — Main Zone</div>
        <Skeleton height="2.2rem" width="50%" />
        <div style={{ marginTop: '0.5rem' }}><Skeleton width="40%" /></div>
        <div style={{ marginTop: '0.5rem' }}><Skeleton width="55%" /></div>
      </div>
    )
  }

  const { current_temperature: cur, target_temperature: tgt, hvac_mode, fan_speed } = data

  const tempColor =
    hvac_mode === 'cooling' ? C.blue :
    hvac_mode === 'heating' ? C.orange :
    C.green

  const modeBadge =
    hvac_mode === 'cooling' ? { bg: C.blueBg,   color: C.blue,   text: '❄ cooling' } :
    hvac_mode === 'heating' ? { bg: C.orangeBg,  color: C.orange, text: '🔥 heating' } :
    { bg: C.greenBg, color: C.green, text: '✓ idle' }

  return (
    <div style={card}>
      <div style={label}>HVAC — Main Zone</div>

      <div style={{ ...bigNumber, color: tempColor }}>
        {cur?.toFixed(1)} °C
      </div>
      <div style={{ fontSize: '0.8rem', color: C.muted, marginTop: '0.25rem' }}>
        setpoint: {tgt?.toFixed(1)} °C
      </div>

      {/* Temperature bar */}
      <div style={{
        marginTop: '0.75rem',
        height: '4px',
        background: C.border,
        borderRadius: '2px',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${Math.min(100, Math.max(0, ((cur - 15) / 20) * 100))}%`,
          background: tempColor,
          borderRadius: '2px',
          transition: 'width 1s ease',
        }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: C.muted, marginTop: '2px' }}>
        <span>15°C</span><span>35°C</span>
      </div>

      <div style={metaRow}>
        <Badge {...modeBadge} />
        <Badge text={`fan: ${fan_speed}`} bg={C.border} color={C.muted} />
      </div>
    </div>
  )
}

// ── CO2 Card ──────────────────────────────────────────────────────────────────
function CO2Card({ data }) {
  if (!data) {
    return (
      <div style={card}>
        <div style={label}>CO₂ — Air Quality</div>
        <Skeleton height="2.2rem" width="50%" />
        <div style={{ marginTop: '0.5rem' }}><Skeleton width="40%" /></div>
      </div>
    )
  }

  const { co2_level, status } = data

  const statusStyle =
    status === 'high'     ? { bg: C.redBg,    color: C.red,    text: '⚠ high' } :
    status === 'elevated' ? { bg: C.yellowBg, color: C.yellow, text: '△ elevated' } :
    { bg: C.greenBg, color: C.green, text: '✓ normal' }

  // Scale: 350 (floor) → 1500 (ceil)
  const pct = Math.min(100, Math.max(0, ((co2_level - 350) / 1150) * 100))
  const barColor = status === 'high' ? C.red : status === 'elevated' ? C.yellow : C.green

  return (
    <div style={card}>
      <div style={label}>CO₂ — Air Quality</div>

      <div style={{ ...bigNumber, color: barColor }}>
        {co2_level} <span style={{ fontSize: '1rem', fontWeight: 400, color: C.muted }}>ppm</span>
      </div>

      <div style={{
        marginTop: '0.75rem',
        height: '4px',
        background: C.border,
        borderRadius: '2px',
        overflow: 'hidden',
      }}>
        <div style={{
          height: '100%',
          width: `${pct}%`,
          background: barColor,
          borderRadius: '2px',
          transition: 'width 1s ease',
        }} />
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.65rem', color: C.muted, marginTop: '2px' }}>
        <span>350</span><span>1500 ppm</span>
      </div>

      <div style={metaRow}>
        <Badge {...statusStyle} />
      </div>
    </div>
  )
}

// ── Occupancy Card ────────────────────────────────────────────────────────────
function OccupancyCard({ data }) {
  if (!data) {
    return (
      <div style={card}>
        <div style={label}>Occupancy</div>
        <Skeleton height="2.2rem" width="60%" />
        <div style={{ marginTop: '0.5rem' }}><Skeleton width="40%" /></div>
      </div>
    )
  }

  const { occupancy_status, occupant_count } = data
  const occupied = occupancy_status === 'occupied'

  return (
    <div style={card}>
      <div style={label}>Occupancy</div>

      <div style={{ ...bigNumber, color: occupied ? C.green : C.muted }}>
        {occupied ? occupant_count : '—'}
        <span style={{ fontSize: '1rem', fontWeight: 400, color: C.muted }}>
          {occupied ? (occupant_count === 1 ? ' person' : ' people') : ''}
        </span>
      </div>

      <div style={metaRow}>
        <Badge
          text={occupied ? '● occupied' : '○ vacant'}
          bg={occupied ? C.greenBg : C.border}
          color={occupied ? C.green : C.muted}
        />
      </div>
    </div>
  )
}

// ── WS status pill ────────────────────────────────────────────────────────────
function WSStatusPill({ status }) {
  const cfg = {
    connected:    { color: C.green,  bg: C.greenBg,  dot: '●', text: 'Live' },
    connecting:   { color: C.muted,  bg: C.border,   dot: '○', text: 'Connecting…' },
    reconnecting: { color: C.yellow, bg: C.yellowBg, dot: '◌', text: 'Reconnecting…' },
    auth_error:   { color: C.red,    bg: '#3b1010',  dot: '✕', text: 'Auth Error' },
  }[status] ?? { color: C.muted, bg: C.border, dot: '○', text: status }

  return (
    <span style={{
      display: 'inline-flex', alignItems: 'center', gap: '4px',
      background: cfg.bg, color: cfg.color,
      padding: '2px 10px', borderRadius: '10px',
      fontSize: '0.72rem', fontWeight: 600,
    }}>
      {cfg.dot} {cfg.text}
    </span>
  )
}

// ── Dashboard ─────────────────────────────────────────────────────────────────
// telemetry and wsStatus are now passed as props from App.jsx, which owns the
// single useTelemetry() call so ControlPanel can share the same data.
export default function TelemetryDashboard({ telemetry, wsStatus }) {
  const hvac      = telemetry[TOPIC_HVAC]
  const co2       = telemetry[TOPIC_CO2]
  const occupancy = telemetry[TOPIC_OCCUPANCY]

  return (
    <section>
      {/* Header row */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem',
        marginBottom: '0.75rem',
      }}>
        <div style={{
          fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: C.muted,
        }}>
          Live Telemetry — Main Zone
        </div>
        <WSStatusPill status={wsStatus} />
      </div>

      {/* Sensor cards */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(3, 1fr)',
        gap: '1rem',
      }}>
        <HVACCard      data={hvac}      />
        <CO2Card       data={co2}       />
        <OccupancyCard data={occupancy} />
      </div>

      {/* Pulse animation */}
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 0.4; }
          50%       { opacity: 0.8; }
        }
      `}</style>
    </section>
  )
}
