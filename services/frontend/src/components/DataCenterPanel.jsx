/**
 * BASIS — Data Center Telemetry Panel
 * Renders live telemetry from a simulated data center site (dc-boise-01).
 * Payload shape matches DataCenterSimulator in simulator.py:
 *   { event_type, site_id, timestamp, racks[], thermal{}, cooling{}, power{}, ups{}, environment{} }
 *
 * Displayed below the existing HVAC/CO2/Occupancy cards on the Dashboard.
 * Uses the same colour palette and card styles as TelemetryDashboard.jsx.
 */

const C = {
  bg:        '#0f1117',
  surface:   '#1a202c',
  surfaceHi: '#202635',
  border:    '#2d3748',
  text:      '#e2e8f0',
  muted:     '#718096',
  mutedHi:   '#a0aec0',
  accent:    '#63b3ed',
  green:     '#68d391',
  greenBg:   '#0d2318',
  yellow:    '#f6e05e',
  yellowBg:  '#2d2408',
  red:       '#fc8181',
  redBg:     '#2d1010',
  orange:    '#f6ad55',
  orangeBg:  '#2d1a08',
  blue:      '#63b3ed',
  blueBg:    '#0d1f3c',
  purple:    '#b794f4',
}

// ── Shared primitives ─────────────────────────────────────────────────────────

const card = {
  background:   C.surface,
  border:       `1px solid ${C.border}`,
  borderRadius: '8px',
  padding:      '1rem 1.1rem',
}

function Badge({ text, bg, color }) {
  return (
    <span style={{
      background: bg, color,
      padding: '1px 7px', borderRadius: '9px',
      fontSize: '0.68rem', fontWeight: 700,
      whiteSpace: 'nowrap',
    }}>
      {text}
    </span>
  )
}

function MiniBar({ value, max, color }) {
  const pct = Math.min(100, Math.max(0, (value / max) * 100))
  return (
    <div style={{ height: '4px', background: C.border, borderRadius: '2px', overflow: 'hidden', marginTop: '4px' }}>
      <div style={{
        height: '100%', width: `${pct}%`, background: color,
        borderRadius: '2px', transition: 'width 1s ease',
      }} />
    </div>
  )
}

function Skeleton({ height = '1rem', width = '60%' }) {
  return (
    <div style={{
      height, width, borderRadius: '4px',
      background: C.border,
      animation: 'dc-pulse 1.5s ease-in-out infinite',
    }} />
  )
}

// ── Status helpers ────────────────────────────────────────────────────────────

function statusColor(status) {
  switch (status) {
    case 'normal':   return { color: C.green,  bg: C.greenBg  }
    case 'warning':  return { color: C.yellow, bg: C.yellowBg }
    case 'critical':
    case 'overload': return { color: C.red,    bg: C.redBg    }
    case 'on_battery': return { color: C.orange, bg: C.orangeBg }
    default:         return { color: C.muted,  bg: C.border   }
  }
}

// ── Rack Temperature Card ─────────────────────────────────────────────────────
function RackTempCard({ racks }) {
  if (!racks?.length) return (
    <div style={card}>
      <div style={sectionLabel}>Rack Inlet Temps</div>
      <Skeleton height="1rem" width="80%" />
    </div>
  )

  return (
    <div style={card}>
      <div style={sectionLabel}>Rack Inlet Temps</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.55rem' }}>
        {racks.map(rack => {
          const sc = statusColor(rack.status)
          const pct = Math.min(100, Math.max(0, ((rack.inlet_temp_c - 18) / 16) * 100))
          const barColor = rack.status === 'critical' ? C.red : rack.status === 'warning' ? C.yellow : C.green
          return (
            <div key={rack.rack_id}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2px' }}>
                <span style={{ fontSize: '0.72rem', color: C.mutedHi, fontFamily: 'monospace' }}>
                  {rack.rack_id}
                </span>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <span style={{ fontSize: '0.82rem', fontWeight: 700, color: barColor }}>
                    {rack.inlet_temp_c?.toFixed(1)}°C
                  </span>
                  <Badge text={rack.status} bg={sc.bg} color={sc.color} />
                </div>
              </div>
              <MiniBar value={rack.inlet_temp_c - 18} max={16} color={barColor} />
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.63rem', color: C.muted, marginTop: '3px' }}>
        <span>18°C</span><span>34°C</span>
      </div>
    </div>
  )
}

// ── Thermal Aisle Card ────────────────────────────────────────────────────────
function ThermalCard({ thermal }) {
  if (!thermal) return (
    <div style={card}>
      <div style={sectionLabel}>Thermal — Aisles</div>
      <Skeleton height="2rem" width="50%" />
    </div>
  )

  const { cold_aisle_temp_c: cold, hot_aisle_temp_c: hot, delta_t_c: delta } = thermal
  const deltaOk = delta < 14
  const deltaColor = delta >= 16 ? C.red : delta >= 14 ? C.yellow : C.green

  return (
    <div style={card}>
      <div style={sectionLabel}>Thermal — Aisles</div>
      <div style={{ display: 'flex', gap: '0.75rem', justifyContent: 'space-between' }}>
        <div style={{ textAlign: 'center', flex: 1 }}>
          <div style={{ fontSize: '1.55rem', fontWeight: 700, color: C.blue, lineHeight: 1 }}>
            {cold?.toFixed(1)}°C
          </div>
          <div style={{ fontSize: '0.65rem', color: C.muted, marginTop: '3px' }}>❄ cold aisle</div>
        </div>
        <div style={{ textAlign: 'center', flex: 1, borderLeft: `1px solid ${C.border}`, borderRight: `1px solid ${C.border}` }}>
          <div style={{ fontSize: '1.55rem', fontWeight: 700, color: deltaColor, lineHeight: 1 }}>
            ΔT {delta?.toFixed(1)}K
          </div>
          <div style={{ fontSize: '0.65rem', color: C.muted, marginTop: '3px' }}>
            {deltaOk ? '✓ within range' : '⚠ high delta'}
          </div>
        </div>
        <div style={{ textAlign: 'center', flex: 1 }}>
          <div style={{ fontSize: '1.55rem', fontWeight: 700, color: C.orange, lineHeight: 1 }}>
            {hot?.toFixed(1)}°C
          </div>
          <div style={{ fontSize: '0.65rem', color: C.muted, marginTop: '3px' }}>🔥 hot aisle</div>
        </div>
      </div>
    </div>
  )
}

// ── CRAC Cooling Card ─────────────────────────────────────────────────────────
function CoolingCard({ cooling }) {
  if (!cooling) return (
    <div style={card}>
      <div style={sectionLabel}>CRAC Cooling Unit</div>
      <Skeleton height="1.5rem" width="60%" />
    </div>
  )

  const { unit_id, mode, fan_speed_percent, supply_air_temp_c, return_air_temp_c } = cooling
  const modeStyle = {
    cooling:     { color: C.blue,  bg: C.blueBg,  text: '❄ cooling'     },
    standby:     { color: C.muted, bg: C.border,  text: '○ standby'     },
    maintenance: { color: C.yellow, bg: C.yellowBg, text: '⚙ maintenance' },
  }[mode] ?? { color: C.muted, bg: C.border, text: mode }

  const fanColor = fan_speed_percent > 85 ? C.yellow : C.green

  return (
    <div style={card}>
      <div style={sectionLabel}>CRAC Cooling Unit</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.6rem' }}>
        <span style={{ fontSize: '0.75rem', fontFamily: 'monospace', color: C.mutedHi }}>{unit_id}</span>
        <Badge text={modeStyle.text} bg={modeStyle.bg} color={modeStyle.color} />
      </div>
      <div style={{ display: 'flex', gap: '0.75rem' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.63rem', color: C.muted, marginBottom: '2px' }}>Fan speed</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: fanColor }}>
            {fan_speed_percent?.toFixed(0)}%
          </div>
          <MiniBar value={fan_speed_percent} max={100} color={fanColor} />
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.63rem', color: C.muted, marginBottom: '2px' }}>Supply air</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: C.blue }}>
            {supply_air_temp_c?.toFixed(1)}°C
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.63rem', color: C.muted, marginBottom: '2px' }}>Return air</div>
          <div style={{ fontSize: '1.1rem', fontWeight: 700, color: C.orange }}>
            {return_air_temp_c?.toFixed(1)}°C
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Power / PDU Card ──────────────────────────────────────────────────────────
function PowerCard({ power }) {
  if (!power) return (
    <div style={card}>
      <div style={sectionLabel}>Power — PDU</div>
      <Skeleton height="2rem" width="50%" />
    </div>
  )

  const { pdu_id, load_percent, kw, status } = power
  const sc = statusColor(status)
  const barColor = status === 'overload' ? C.red : status === 'warning' ? C.yellow : C.green

  return (
    <div style={card}>
      <div style={sectionLabel}>Power — PDU</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '0.4rem' }}>
        <div>
          <span style={{ fontSize: '1.8rem', fontWeight: 700, color: barColor, lineHeight: 1 }}>
            {load_percent?.toFixed(0)}%
          </span>
          <span style={{ fontSize: '0.8rem', color: C.muted, marginLeft: '0.4rem' }}>
            {kw?.toFixed(1)} kW
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
          <span style={{ fontSize: '0.7rem', fontFamily: 'monospace', color: C.mutedHi }}>{pdu_id}</span>
          <Badge text={status} bg={sc.bg} color={sc.color} />
        </div>
      </div>
      <MiniBar value={load_percent} max={100} color={barColor} />
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.63rem', color: C.muted, marginTop: '2px' }}>
        <span>0%</span><span style={{ color: C.yellow }}>70%</span><span style={{ color: C.red }}>90%</span><span>100%</span>
      </div>
    </div>
  )
}

// ── UPS Card ──────────────────────────────────────────────────────────────────
function UPSCard({ ups }) {
  if (!ups) return (
    <div style={card}>
      <div style={sectionLabel}>UPS</div>
      <Skeleton height="2rem" width="50%" />
    </div>
  )

  const { ups_id, battery_percent, runtime_minutes, utility_power, status } = ups
  const sc = statusColor(status)
  const battColor =
    battery_percent < 20 ? C.red :
    battery_percent < 50 ? C.yellow :
    C.green
  const utilStyle =
    utility_power === 'normal'
      ? { color: C.green, bg: C.greenBg, text: '✓ utility normal' }
      : { color: C.red,   bg: C.redBg,   text: '⚡ utility failed' }

  return (
    <div style={card}>
      <div style={sectionLabel}>UPS</div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-end', marginBottom: '0.4rem' }}>
        <div>
          <span style={{ fontSize: '1.8rem', fontWeight: 700, color: battColor, lineHeight: 1 }}>
            {battery_percent?.toFixed(0)}%
          </span>
          <span style={{ fontSize: '0.8rem', color: C.muted, marginLeft: '0.4rem' }}>
            {runtime_minutes}m runtime
          </span>
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: '3px' }}>
          <span style={{ fontSize: '0.7rem', fontFamily: 'monospace', color: C.mutedHi }}>{ups_id}</span>
          <Badge text={status} bg={sc.bg} color={sc.color} />
        </div>
      </div>
      <MiniBar value={battery_percent} max={100} color={battColor} />
      <div style={{ marginTop: '0.4rem' }}>
        <Badge text={utilStyle.text} bg={utilStyle.bg} color={utilStyle.color} />
      </div>
    </div>
  )
}

// ── Environment Card ──────────────────────────────────────────────────────────
function EnvironmentCard({ environment }) {
  if (!environment) return (
    <div style={card}>
      <div style={sectionLabel}>Environment</div>
      <Skeleton height="1.5rem" width="70%" />
    </div>
  )

  const { humidity_percent, leak_detected, smoke_detected } = environment
  const humidityColor =
    humidity_percent > 60 ? C.yellow :
    humidity_percent < 35 ? C.yellow :
    C.green
  const safetyOk = !leak_detected && !smoke_detected

  return (
    <div style={card}>
      <div style={sectionLabel}>Environment</div>
      <div style={{ display: 'flex', gap: '0.75rem', alignItems: 'flex-start' }}>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.63rem', color: C.muted, marginBottom: '2px' }}>Humidity</div>
          <div style={{ fontSize: '1.55rem', fontWeight: 700, color: humidityColor, lineHeight: 1 }}>
            {humidity_percent?.toFixed(0)}%
          </div>
          <MiniBar value={humidity_percent} max={100} color={humidityColor} />
          <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.6rem', color: C.muted, marginTop: '1px' }}>
            <span>30%</span><span>50%</span><span>70%</span>
          </div>
        </div>
        <div style={{ flex: 1 }}>
          <div style={{ fontSize: '0.63rem', color: C.muted, marginBottom: '0.4rem' }}>Safety sensors</div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span style={{ color: leak_detected ? C.red : C.green, fontSize: '0.65rem' }}>
                {leak_detected ? '⚠' : '✓'}
              </span>
              <span style={{ fontSize: '0.73rem', color: leak_detected ? C.red : C.mutedHi }}>
                {leak_detected ? 'Leak detected' : 'No leak'}
              </span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
              <span style={{ color: smoke_detected ? C.red : C.green, fontSize: '0.65rem' }}>
                {smoke_detected ? '⚠' : '✓'}
              </span>
              <span style={{ fontSize: '0.73rem', color: smoke_detected ? C.red : C.mutedHi }}>
                {smoke_detected ? 'Smoke detected' : 'No smoke'}
              </span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Section label shared style ────────────────────────────────────────────────
const sectionLabel = {
  fontSize:      '0.65rem',
  fontWeight:    700,
  textTransform: 'uppercase',
  letterSpacing: '0.08em',
  color:         C.muted,
  marginBottom:  '0.65rem',
}

// ── Empty / loading state ─────────────────────────────────────────────────────
function LoadingState() {
  return (
    <div style={{
      padding: '2rem',
      textAlign: 'center',
      background: C.surface,
      border: `1px solid ${C.border}`,
      borderRadius: '8px',
    }}>
      <div style={{ fontSize: '0.8rem', color: C.muted, marginBottom: '0.35rem' }}>
        Awaiting data center telemetry…
      </div>
      <div style={{ fontSize: '0.72rem', color: C.muted, opacity: 0.7 }}>
        First event arrives within ~9 s of simulator startup
      </div>
    </div>
  )
}

// ── Main export ───────────────────────────────────────────────────────────────
export default function DataCenterPanel({ data }) {
  return (
    <section style={{ marginTop: '1.75rem' }}>

      {/* Section header */}
      <div style={{
        display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '0.75rem',
      }}>
        <div style={{
          fontSize: '0.7rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.08em', color: C.muted,
        }}>
          Data Center Telemetry — {data?.site_id ?? 'dc-boise-01'}
        </div>
        {data && (
          <span style={{
            fontSize: '0.65rem', fontWeight: 600,
            color: C.green, background: C.greenBg,
            padding: '1px 8px', borderRadius: '9px',
          }}>
            ● live
          </span>
        )}
      </div>

      {/* Educational callout */}
      <div style={{
        padding: '0.75rem 1rem',
        background: 'rgba(26,39,68,0.45)',
        border: '1px solid #2a4a8a',
        borderRadius: '7px',
        fontSize: '0.75rem',
        color: '#90cdf4',
        lineHeight: 1.65,
        marginBottom: '1rem',
      }}>
        <strong>Why this matters for BASIS:</strong> AI-era data centers are critical
        infrastructure — any unauthorized setpoint change, power override, or cooling
        command can cascade into downtime or hardware damage. BASIS enforces identity-verified,
        role-gated authorization on every control action before it reaches the physical layer,
        and records each decision in the audit log. The same{' '}
        <code style={{ background: '#0f1a2d', padding: '0 3px', borderRadius: '3px', fontFamily: 'monospace' }}>
          require_action()
        </code>{' '}
        pattern that gates the HVAC setpoint would gate a PDU reboot or CRAC mode change.
      </div>

      {!data ? (
        <LoadingState />
      ) : (
        <>
          {/* Row 1: Rack temps + Thermal */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: '1fr 1fr',
            gap: '1rem',
            marginBottom: '1rem',
          }}>
            <RackTempCard   racks={data.racks}         />
            <ThermalCard    thermal={data.thermal}     />
          </div>

          {/* Row 2: Cooling + Power + UPS + Environment */}
          <div style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(4, 1fr)',
            gap: '1rem',
          }}>
            <CoolingCard     cooling={data.cooling}         />
            <PowerCard       power={data.power}             />
            <UPSCard         ups={data.ups}                 />
            <EnvironmentCard environment={data.environment} />
          </div>
        </>
      )}

      <style>{`
        @keyframes dc-pulse {
          0%, 100% { opacity: 0.4; }
          50%       { opacity: 0.8; }
        }
      `}</style>
    </section>
  )
}
