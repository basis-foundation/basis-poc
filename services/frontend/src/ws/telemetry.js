/**
 * Basis Foundation — Telemetry WebSocket hook
 *
 * useTelemetry(wsUrl)
 *   Returns { telemetry, wsStatus }
 *
 * wsStatus: 'connecting' | 'connected' | 'reconnecting'
 *
 * telemetry: flat object keyed by MQTT topic, e.g.
 *   {
 *     "basis/hvac/main/telemetry":       { current_temperature, target_temperature, ... },
 *     "basis/sensors/co2/telemetry":     { co2_level, status, ... },
 *     "basis/sensors/occupancy/telemetry": { occupancy_status, occupant_count, ... },
 *   }
 *
 * Reconnect strategy: exponential backoff, 1 s → 2 s → 4 s → … → 30 s cap.
 * On reconnect, the server immediately re-sends a full snapshot, so the UI
 * never shows stale data after a reconnect.
 */

import { useState, useEffect, useRef } from 'react'

const MIN_RETRY_MS  = 1_000
const MAX_RETRY_MS  = 30_000

export function useTelemetry(wsUrl) {
  const [telemetry, setTelemetry] = useState({})
  const [wsStatus, setWsStatus]   = useState('connecting')

  // useRef so the cleanup function always has the current values
  const retryDelay = useRef(MIN_RETRY_MS)
  const retryTimer = useRef(null)
  const ws         = useRef(null)
  const mounted    = useRef(true)

  useEffect(() => {
    mounted.current = true

    function connect() {
      if (!mounted.current) return
      setWsStatus('connecting')

      const socket = new WebSocket(wsUrl)
      ws.current = socket

      socket.onopen = () => {
        if (!mounted.current) return
        setWsStatus('connected')
        retryDelay.current = MIN_RETRY_MS  // reset backoff on success
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
          // Replace entire state with the server's latest known values
          setTelemetry(msg.data ?? {})
        } else if (msg.type === 'update') {
          // Merge a single topic update
          setTelemetry(prev => ({ ...prev, [msg.topic]: msg.data }))
        }
      }

      socket.onerror = () => {
        // onerror is always followed by onclose — handle there
      }

      socket.onclose = () => {
        if (!mounted.current) return
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
  }, [wsUrl])

  return { telemetry, wsStatus }
}
