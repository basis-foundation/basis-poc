/**
 * BASIS — Architecture View
 * Explains the platform architecture with an SVG diagram, component cards,
 * and a numbered data-flow walkthrough.
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

// ── Architecture SVG diagram ──────────────────────────────────────────────────
function ArchDiagram() {
  // viewBox: 0 0 820 290
  // Row 1 (y=20-80): Keycloak centered
  // Row 2 (y=175-240): Frontend, FastAPI, MQTT Broker, Simulator
  const BOX = { rx: '7', fillOpacity: '1' }
  const LABEL = { textAnchor: 'middle', fontFamily: 'system-ui, sans-serif', dominantBaseline: 'middle' }
  const ARROW_COLOR = '#3a4a5f'
  const TELEMETRY_COLOR = '#f6ad55'
  const WS_COLOR = '#63b3ed'
  const AUTH_COLOR = '#7c5cbf'

  return (
    <svg
      viewBox="0 0 820 290"
      style={{ width: '100%', maxHeight: '290px' }}
      aria-label="BASIS platform architecture diagram"
    >
      <defs>
        {/* Standard grey arrowhead */}
        <marker id="ah" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M 0 0 L 7 3 L 0 6 Z" fill={ARROW_COLOR} />
        </marker>
        {/* Blue arrowhead (WebSocket) */}
        <marker id="ah-ws" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M 0 0 L 7 3 L 0 6 Z" fill={WS_COLOR} />
        </marker>
        {/* Orange arrowhead (telemetry) */}
        <marker id="ah-tel" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M 0 0 L 7 3 L 0 6 Z" fill={TELEMETRY_COLOR} />
        </marker>
        {/* Purple arrowhead (auth) */}
        <marker id="ah-auth" markerWidth="7" markerHeight="6" refX="6" refY="3" orient="auto">
          <path d="M 0 0 L 7 3 L 0 6 Z" fill={AUTH_COLOR} />
        </marker>
      </defs>

      {/* ── Keycloak (top-center) ─────────────────────────────────────── */}
      <rect x="305" y="20" width="190" height="68" {...BOX}
        fill="rgba(68,51,122,0.18)" stroke="#6b46c1" strokeWidth="1.5"
      />
      <text x="400" y="47" {...LABEL} fill="#b794f4" fontSize="13" fontWeight="700">Keycloak</text>
      <text x="400" y="64" {...LABEL} fill="#7c5cbf" fontSize="10">Identity Provider</text>
      <text x="400" y="79" {...LABEL} fill="#5a3f8f" fontSize="9">OIDC · RBAC · JWT · PKCE</text>

      {/* ── Frontend (far-left, row 2) ────────────────────────────────── */}
      <rect x="20" y="182" width="148" height="68" {...BOX}
        fill="rgba(26,54,93,0.25)" stroke="#2b6cb0" strokeWidth="1.5"
      />
      <text x="94" y="209" {...LABEL} fill="#63b3ed" fontSize="13" fontWeight="700">Frontend</text>
      <text x="94" y="225" {...LABEL} fill="#3a7ab5" fontSize="10">React + Vite</text>
      <text x="94" y="239" {...LABEL} fill="#2a5a8a" fontSize="9">:5173</text>

      {/* ── FastAPI (center-left, row 2) ──────────────────────────────── */}
      <rect x="235" y="182" width="148" height="68" {...BOX}
        fill="rgba(28,69,50,0.25)" stroke="#276749" strokeWidth="1.5"
      />
      <text x="309" y="209" {...LABEL} fill="#68d391" fontSize="13" fontWeight="700">FastAPI</text>
      <text x="309" y="225" {...LABEL} fill="#3a7a58" fontSize="10">Backend API</text>
      <text x="309" y="239" {...LABEL} fill="#2a5a40" fontSize="9">:8000</text>

      {/* ── MQTT Broker (center-right, row 2) ────────────────────────── */}
      <rect x="455" y="182" width="148" height="68" {...BOX}
        fill="rgba(123,52,30,0.2)" stroke="#c05621" strokeWidth="1.5"
      />
      <text x="529" y="209" {...LABEL} fill="#f6ad55" fontSize="13" fontWeight="700">Mosquitto</text>
      <text x="529" y="225" {...LABEL} fill="#a07040" fontSize="10">MQTT Broker</text>
      <text x="529" y="239" {...LABEL} fill="#7a5030" fontSize="9">:1883</text>

      {/* ── Simulator (far-right, row 2) ──────────────────────────────── */}
      <rect x="660" y="182" width="140" height="68" {...BOX}
        fill="rgba(116,66,16,0.2)" stroke="#b7791f" strokeWidth="1.5"
      />
      <text x="730" y="209" {...LABEL} fill="#f6e05e" fontSize="13" fontWeight="700">Simulator</text>
      <text x="730" y="225" {...LABEL} fill="#a09040" fontSize="10">OT Devices</text>
      <text x="730" y="239" {...LABEL} fill="#7a7030" fontSize="9">HVAC · CO₂ · Occupancy</text>

      {/* ── Arrow: Frontend → Keycloak (OIDC login, curved up-right) ──── */}
      <path
        d="M 94 182 Q 80 90 318 80"
        fill="none" stroke={AUTH_COLOR} strokeWidth="1.3"
        strokeDasharray="5,3"
        markerEnd="url(#ah-auth)"
      />
      <text x="138" y="117" fill="#6b46c1" fontSize="9" textAnchor="middle"
        transform="rotate(-62 138 117)">
        OIDC login
      </text>

      {/* ── Arrow: FastAPI → Keycloak (JWKS validation, curved up) ───── */}
      <path
        d="M 309 182 Q 310 110 390 88"
        fill="none" stroke={AUTH_COLOR} strokeWidth="1.3"
        strokeDasharray="5,3"
        markerEnd="url(#ah-auth)"
      />
      <text x="362" y="130" fill="#6b46c1" fontSize="9" textAnchor="middle">JWKS</text>

      {/* ── Arrow: Frontend → FastAPI (REST + JWT) ────────────────────── */}
      <line
        x1="168" y1="211" x2="235" y2="211"
        stroke={ARROW_COLOR} strokeWidth="1.5"
        markerEnd="url(#ah)"
      />
      <text x="201" y="206" fill={C.muted} fontSize="9" textAnchor="middle">REST + JWT</text>

      {/* ── Arrow: FastAPI → Frontend (WebSocket push) ─────────────────── */}
      <line
        x1="235" y1="228" x2="168" y2="228"
        stroke={WS_COLOR} strokeWidth="1.5"
        strokeDasharray="5,3"
        markerEnd="url(#ah-ws)"
      />
      <text x="201" y="243" fill={WS_COLOR} fontSize="9" textAnchor="middle">WebSocket</text>

      {/* ── Arrow: FastAPI → MQTT (publish commands) ──────────────────── */}
      <line
        x1="383" y1="211" x2="455" y2="211"
        stroke={ARROW_COLOR} strokeWidth="1.5"
        markerEnd="url(#ah)"
      />
      <text x="419" y="206" fill={C.muted} fontSize="9" textAnchor="middle">commands</text>

      {/* ── Arrow: MQTT → FastAPI (telemetry subscription) ──────────────── */}
      <line
        x1="455" y1="228" x2="383" y2="228"
        stroke={TELEMETRY_COLOR} strokeWidth="1.5"
        markerEnd="url(#ah-tel)"
      />
      <text x="419" y="243" fill={TELEMETRY_COLOR} fontSize="9" textAnchor="middle">telemetry</text>

      {/* ── Arrow: MQTT ↔ Simulator ────────────────────────────────────── */}
      <line
        x1="603" y1="211" x2="660" y2="211"
        stroke={ARROW_COLOR} strokeWidth="1.5"
        markerEnd="url(#ah)"
      />
      <line
        x1="660" y1="228" x2="603" y2="228"
        stroke={TELEMETRY_COLOR} strokeWidth="1.5"
        markerEnd="url(#ah-tel)"
      />

      {/* ── Legend ──────────────────────────────────────────────────────── */}
      <g transform="translate(20, 265)">
        <line x1="0" y1="6" x2="20" y2="6" stroke={AUTH_COLOR} strokeWidth="1.2" strokeDasharray="4,2" markerEnd="url(#ah-auth)" />
        <text x="24" y="9" fill="#6b46c1" fontSize="8.5">Auth / OIDC</text>
        <line x1="90" y1="6" x2="110" y2="6" stroke={ARROW_COLOR} strokeWidth="1.4" markerEnd="url(#ah)" />
        <text x="114" y="9" fill={C.muted} fontSize="8.5">Commands</text>
        <line x1="185" y1="6" x2="205" y2="6" stroke={TELEMETRY_COLOR} strokeWidth="1.4" markerEnd="url(#ah-tel)" />
        <text x="209" y="9" fill={TELEMETRY_COLOR} fontSize="8.5">Telemetry</text>
        <line x1="270" y1="6" x2="290" y2="6" stroke={WS_COLOR} strokeWidth="1.2" strokeDasharray="4,2" markerEnd="url(#ah-ws)" />
        <text x="294" y="9" fill={WS_COLOR} fontSize="8.5">WebSocket push</text>
      </g>
    </svg>
  )
}

// ── Component cards ───────────────────────────────────────────────────────────
const COMPONENTS = [
  {
    name: 'Keycloak',
    role: 'Identity Provider',
    port: '18080',
    color: C.purple,
    borderColor: '#6b46c1',
    bg: 'rgba(68,51,122,0.12)',
    description: 'Manages all user identities, roles, and authentication flows. Implements OpenID Connect with PKCE. Issues signed JWTs that carry role claims. FastAPI validates every token against Keycloak\'s JWKS endpoint.',
    tags: ['OIDC', 'JWT', 'RBAC', 'PKCE'],
  },
  {
    name: 'React Frontend',
    role: 'Operator Console',
    port: '5173',
    color: C.accent,
    borderColor: '#2b6cb0',
    bg: 'rgba(26,54,93,0.15)',
    description: 'The interface you\'re using right now. Authenticates via Keycloak redirect, then attaches a Bearer token to every API call. Receives live telemetry over an authenticated WebSocket. No token = no data.',
    tags: ['React', 'Vite', 'OIDC Client', 'WebSocket'],
  },
  {
    name: 'FastAPI',
    role: 'Backend API',
    port: '8000',
    color: C.green,
    borderColor: '#276749',
    bg: 'rgba(28,69,50,0.15)',
    description: 'The authorization enforcement point. Validates JWT signatures against Keycloak\'s JWKS, extracts realm roles, and applies RBAC policy before allowing any command. Bridges REST/WebSocket to MQTT.',
    tags: ['FastAPI', 'JWT Validation', 'RBAC Policy', 'WebSocket'],
  },
  {
    name: 'Mosquitto',
    role: 'MQTT Broker',
    port: '1883',
    color: C.orange,
    borderColor: '#c05621',
    bg: 'rgba(123,52,30,0.15)',
    description: 'The OT message bus. Carries telemetry from the simulator to the API, and forwards commands from the API to the simulator. Represents the transport layer you\'d find in a real building automation system.',
    tags: ['MQTT', 'Pub/Sub', 'OT Transport', 'Eclipse Mosquitto'],
  },
  {
    name: 'Simulator',
    role: 'OT Device Layer',
    port: 'internal',
    color: C.yellow,
    borderColor: '#b7791f',
    bg: 'rgba(116,66,16,0.12)',
    description: 'Simulates an HVAC unit, CO₂ sensor, and occupancy detector. Publishes telemetry on a configurable heartbeat, and receives command messages that adjust the HVAC setpoint — demonstrating a realistic control loop.',
    tags: ['HVAC', 'CO₂', 'Occupancy', 'Python'],
  },
]

function ComponentCard({ component: c }) {
  return (
    <div style={{
      background: c.bg,
      border: `1px solid ${c.borderColor}33`,
      borderLeft: `3px solid ${c.borderColor}`,
      borderRadius: '8px',
      padding: '1rem 1.1rem',
    }}>
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '0.5rem' }}>
        <div>
          <div style={{ fontSize: '0.88rem', fontWeight: 700, color: c.color }}>{c.name}</div>
          <div style={{ fontSize: '0.72rem', color: C.muted, marginTop: '1px' }}>{c.role}</div>
        </div>
        {c.port !== 'internal' && (
          <code style={{
            fontSize: '0.68rem',
            color: C.muted,
            background: 'rgba(0,0,0,0.3)',
            padding: '1px 6px',
            borderRadius: '4px',
            fontFamily: 'monospace',
          }}>
            :{c.port}
          </code>
        )}
      </div>
      <p style={{ fontSize: '0.77rem', color: '#a0aec0', lineHeight: 1.65, margin: '0 0 0.6rem 0' }}>
        {c.description}
      </p>
      <div style={{ display: 'flex', gap: '0.3rem', flexWrap: 'wrap' }}>
        {c.tags.map(tag => (
          <span key={tag} style={{
            fontSize: '0.62rem',
            color: c.color,
            background: `${c.borderColor}20`,
            border: `1px solid ${c.borderColor}30`,
            padding: '1px 6px',
            borderRadius: '4px',
            fontWeight: 600,
          }}>
            {tag}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Data flow steps ───────────────────────────────────────────────────────────
const DATA_FLOWS = [
  {
    num: 1,
    title: 'User opens the console',
    description: 'The browser loads the React app. No credentials exist yet, so Keycloak redirects the user to log in.',
    tag: 'Authentication',
    color: C.purple,
  },
  {
    num: 2,
    title: 'Keycloak issues a signed JWT',
    description: 'After successful login, Keycloak returns an access token containing the user\'s realm roles (viewer, operator, or admin) as signed claims.',
    tag: 'Token Issuance',
    color: C.purple,
  },
  {
    num: 3,
    title: 'Frontend opens an authenticated WebSocket',
    description: 'The token is appended to the WebSocket handshake URL. FastAPI validates it against Keycloak\'s JWKS before accepting the connection.',
    tag: 'Telemetry Auth',
    color: C.accent,
  },
  {
    num: 4,
    title: 'Simulator publishes telemetry via MQTT',
    description: 'Every 10 seconds, the simulator publishes sensor readings to the Mosquitto broker on topics like basis/hvac/main/telemetry.',
    tag: 'OT Data',
    color: C.orange,
  },
  {
    num: 5,
    title: 'FastAPI fans telemetry to WebSocket clients',
    description: 'The API subscribes to MQTT topics and broadcasts each message to all connected WebSocket clients with valid tokens.',
    tag: 'Fan-out',
    color: C.green,
  },
  {
    num: 6,
    title: 'Operator sends a setpoint command',
    description: 'POST /api/controls/hvac/main/setpoint with a Bearer token. FastAPI validates the JWT, checks that the role is operator or admin, then publishes the command to MQTT.',
    tag: 'Authorization',
    color: C.green,
  },
  {
    num: 7,
    title: 'Simulator receives the command',
    description: 'The simulator\'s MQTT subscription picks up the command and adjusts the internal setpoint. Subsequent telemetry ticks show current_temperature drifting toward the new target.',
    tag: 'Control Loop',
    color: C.yellow,
  },
]

function FlowStep({ step }) {
  return (
    <div style={{ display: 'flex', gap: '0.9rem', alignItems: 'flex-start' }}>
      <div style={{
        width: '24px', height: '24px',
        borderRadius: '50%',
        background: `${step.color}22`,
        border: `1.5px solid ${step.color}55`,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.7rem', fontWeight: 700,
        color: step.color,
        flexShrink: 0,
        marginTop: '1px',
      }}>
        {step.num}
      </div>
      <div style={{ flex: 1 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.2rem' }}>
          <span style={{ fontSize: '0.83rem', fontWeight: 600, color: C.text }}>{step.title}</span>
          <span style={{
            fontSize: '0.6rem', fontWeight: 700,
            color: step.color,
            background: `${step.color}15`,
            padding: '1px 6px', borderRadius: '4px',
          }}>
            {step.tag}
          </span>
        </div>
        <p style={{ fontSize: '0.77rem', color: C.muted, margin: 0, lineHeight: 1.6 }}>
          {step.description}
        </p>
      </div>
    </div>
  )
}

// ── Main view ─────────────────────────────────────────────────────────────────
export default function ArchitectureView() {
  return (
    <div>

      {/* ── Page header ─────────────────────────────────────────────── */}
      <div style={{ marginBottom: '2rem' }}>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, margin: '0 0 0.4rem', color: C.text }}>
          Platform Architecture
        </h2>
        <p style={{ fontSize: '0.83rem', color: C.muted, margin: 0, lineHeight: 1.65, maxWidth: '680px' }}>
          BASIS demonstrates how modern identity and authorization controls — typically found in IT systems —
          can be applied to operational technology (OT) environments. Five services collaborate to authenticate
          users, enforce RBAC policy, and deliver live telemetry from simulated building devices.
        </p>
      </div>

      {/* ── Architecture diagram ─────────────────────────────────────── */}
      <div style={{
        background: C.surface,
        border: `1px solid ${C.border}`,
        borderRadius: '10px',
        padding: '1.5rem',
        marginBottom: '1.75rem',
      }}>
        <div style={{
          fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.1em', color: C.muted, marginBottom: '1.25rem',
        }}>
          System Diagram
        </div>
        <ArchDiagram />
      </div>

      {/* ── Component cards ──────────────────────────────────────────── */}
      <div style={{ marginBottom: '1.75rem' }}>
        <div style={{
          fontSize: '0.65rem', fontWeight: 700, textTransform: 'uppercase',
          letterSpacing: '0.1em', color: C.muted, marginBottom: '0.9rem',
        }}>
          Platform Components
        </div>
        <div style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
          gap: '0.85rem',
        }}>
          {COMPONENTS.map(c => <ComponentCard key={c.name} component={c} />)}
        </div>
      </div>

      {/* ── Data flow walkthrough ─────────────────────────────────────── */}
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
          Demo Walkthrough — End-to-End Data Flow
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1.1rem' }}>
          {DATA_FLOWS.map((step, i) => (
            <div key={step.num}>
              <FlowStep step={step} />
              {i < DATA_FLOWS.length - 1 && (
                <div style={{
                  width: '1px',
                  height: '10px',
                  background: C.border,
                  marginLeft: '11px',
                  marginTop: '0.6rem',
                }} />
              )}
            </div>
          ))}
        </div>
      </div>

      {/* ── Design philosophy note ───────────────────────────────────── */}
      <div style={{
        marginTop: '1.25rem',
        padding: '1rem 1.25rem',
        background: 'rgba(26,39,68,0.5)',
        border: '1px solid #2a4a8a',
        borderRadius: '8px',
        fontSize: '0.78rem',
        color: '#90cdf4',
        lineHeight: 1.7,
      }}>
        <strong>Design intent:</strong> BASIS is intentionally local-first and air-gap compatible.
        Every component runs inside a single Docker Compose stack with no external network dependencies —
        a constraint that reflects the reality of OT environments. The architecture is educational and
        demonstrative; it is not a production-ready platform.
      </div>

    </div>
  )
}
