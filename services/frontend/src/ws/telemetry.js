/**
 * Basis Foundation — Authenticated Telemetry WebSocket hook
 * Stage 9: Token-aware connection with expiry handling.
 *
 * useTelemetry(wsBaseUrl, getToken, refreshToken)
 *   Returns { telemetry, wsStatus }
 *
 * Parameters
 * ──────────
 *   wsBaseUrl     Base WebSocket URL without trailing slash or path.
 *                 e.g. "ws://localhost:8000"
 *                 The hook appends "/ws/telemetry?token=<JWT>" before connecting.
 *
 *   getToken      () => string | null
 *                 Returns the current Keycloak access token, or null if unavailable.
 *                 Called fresh on every connect attempt so reconnects always use
 *                 the most recently refreshed token.
 *
 *   refreshToken  () => Promise<void>
 *                 Called when the server closes with code 4001 (token expired).
 *                 Should update the token so the next getToken() call returns a
 *                 fresh value. After the promise resolves, the hook reconnects
 *                 immediately (no backoff — 4001 is an expected, handled condition).
 *
 * wsStatus values
 * ───────────────
 *   'connecting'   — WebSocket opening, no message yet
 *   'connected'    — Session established, receiving data
 *   'reconnecting' — Temporary disconnect, will retry with backoff
 *   'auth_error'   — Server returned close code 4000 (auth/authz failure)
 *                    Reconnect is stopped. The UI should surface this to the user.
 *
 * Close code behavior
 * ───────────────────
 *   4001 (token expired)      — call refreshToken(), reconnect immediately (no delay)
 *   4000 (auth/authz failure) — set wsStatus='auth_error', stop reconnecting
 *   anything else             — exponential backoff reconnect (1s → 2s → … → 30s)
 *
 * Wire format (unchanged from Stage 3)
 * ─────────────────────────────────────
 *   {"type": "snapshot", "data": {topic: payload, ...}}
 *   {"type": "update",   "topic": "...", "data": {...}}
 */

import { useState, useEffect, useRef } from 'react'

const MIN_RETRY_MS = 1_000
const MAX_RETRY_MS = 30_000

export function useTelemetry(wsBaseUrl, getToken, refreshToken) {
  const [telemetry, setTelemetry] = useState({})
  const [wsStatus, setWsStatus]   = useState('connecting')

  const retryDelay = useRef(MIN_RETRY_MS)
  const retryTimer = useRef(null)
  const ws         = useRef(null)
  const mounted    = useRef(true)

  useEffect(() => {
    mounted.current = true

    async function connect() {
      if (!mounted.current) return

      // Fetch the current token fresh on every connect attempt.
      // This ensures reconnects after a 4001 use the refreshed token.
      const token = getToken()
      if (!token) {
        // No token yet — wait for Keycloak to initialize, then retry
        setWsStatus('connecting')
        retryTimer.current = setTimeout(() => connect(), MIN_RETRY_MS)
        return
      }

      setWsStatus('connecting')

      const url    = `${wsBaseUrl}/ws/telemetry?token=${encodeURIComponent(token)}`
      const socket = new WebSocket(url)
      ws.current   = socket

      socket.onopen = () => {
        if (!mounted.current) return
        setWsStatus('connected')
        retryDelay.current = MIN_RETRY_MS  // reset backoff on successful open
      }

      socket.onmessage = (event) => {
        if (!mounted.current) return
        let msg
        try {
          msg = JSON.parse(event.data)
        } catch {
          return
        }

        if (msg.type === 'snapshot') {
          // Replace entire telemetry state with the server's latest known values
          setTelemetry(msg.data ?? {})
        } else if (msg.type === 'update') {
          // Merge a single topic update into existing state
          setTelemetry(prev => ({ ...prev, [msg.topic]: msg.data }))
        }
      }

      socket.onerror = () => {
        // onerror is always followed by onclose — handle everything in onclose
      }

      socket.onclose = async (event) => {
        if (!mounted.current) return

        const code = event.code

        if (code === 4000) {
          // Authentication or authorization failure.
          // The server rejected the token (invalid, expired at connect time, or
          // the subject does not hold subscribe:telemetry). Do not reconnect —
          // surfacing this to the user is the right behavior.
          setWsStatus('auth_error')
          return
        }

        if (code === 4001) {
          // Token expired mid-session (server-initiated close).
          // Refresh the token then reconnect immediately — no backoff delay.
          // This is an expected, normal condition: the token lifecycle is finite.
          try {
            await refreshToken()
          } catch (err) {
            console.warn('[telemetry] Token refresh failed after 4001:', err)
            // If refresh fails, fall through to normal reconnect with backoff
          }
          if (mounted.current) {
            retryDelay.current = MIN_RETRY_MS  // fresh start, no penalty
            connect()
          }
          return
        }

        // Any other close code — reconnect with exponential backoff
        setWsStatus('reconnecting')
        retryTimer.current = setTimeout(() => {
          retryDelay.current = Math.min(retryDelay.current * 2, MAX_RETRY_MS)
          connect()
        }, retryDelay.current)
      }
    }

    connect()

    return () => {
      mounted.current = false
      clearTimeout(retryTimer.current)
      ws.current?.close()
    }
    // wsBaseUrl is the only stable dep — getToken and refreshToken are function refs
    // that should be stable (keycloak singleton methods or useCallback-wrapped).
  }, [wsBaseUrl])  // eslint-disable-line react-hooks/exhaustive-deps

  return { telemetry, wsStatus }
}
