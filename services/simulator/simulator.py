"""
Basis Foundation — OT Device Simulator
Stage 6: Authenticated MQTT connections (MQTT_USERNAME / MQTT_PASSWORD).

Topics published:
  basis/hvac/main/telemetry         every 3 seconds
  basis/sensors/co2/telemetry       every 6 seconds  (every 2nd HVAC tick)
  basis/sensors/occupancy/telemetry every 12 seconds (every 4th HVAC tick)

Topics subscribed:
  basis/hvac/+/command              setpoint commands from the API

Command payload expected:
  {
    "target_temperature": 23.0,   # float, 10–35 °C
    "requested_by": "bob",        # informational
    "zone": "main",               # matched against simulator zone
    "timestamp": "..."
  }

Command validation (simulator side):
  - JSON parse failure      → logged, dropped
  - Non-float temperature   → logged, dropped
  - Out of range (< 10 or > 35) → logged, dropped
  - Mismatched zone         → ignored silently
"""

import json
import logging
import os
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import paho.mqtt.client as mqtt

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("basis.simulator")

# ── Configuration ─────────────────────────────────────────────────────────────
BROKER_HOST          = os.getenv("MQTT_BROKER_HOST", "mosquitto")
BROKER_PORT          = int(os.getenv("MQTT_BROKER_PORT", "1883"))
MQTT_USERNAME        = os.getenv("MQTT_USERNAME", "")
MQTT_PASSWORD        = os.getenv("MQTT_PASSWORD", "")
TICK_INTERVAL        = 3    # seconds per HVAC tick
CO2_TICK_EVERY       = 2    # publish CO2 every N ticks
OCCUPANCY_TICK_EVERY = 4    # publish occupancy every N ticks

TOPIC_HVAC       = "basis/hvac/main/telemetry"
TOPIC_CO2        = "basis/sensors/co2/telemetry"
TOPIC_OCCUPANCY  = "basis/sensors/occupancy/telemetry"
TOPIC_STATUS     = "basis/simulator/status"
TOPIC_CMD_HVAC   = "basis/hvac/+/command"   # wildcard — matches any zone

TEMP_MIN = 10.0   # must match API bounds
TEMP_MAX = 35.0

# ── Setpoint persistence ──────────────────────────────────────────────────────
# Written whenever the setpoint changes; read on startup so a container restart
# doesn't silently reset the target back to the default (21.0 °C).
# Path is inside the mounted source volume so it survives `docker compose restart`.
SETPOINT_FILE = Path(__file__).parent / ".setpoint_state.json"


def _load_persisted_setpoint(zone: str, default: float) -> float:
    """Return the last persisted setpoint for this zone, or *default*."""
    try:
        data = json.loads(SETPOINT_FILE.read_text())
        val  = float(data.get(zone, default))
        if TEMP_MIN <= val <= TEMP_MAX:
            log.info("Loaded persisted setpoint for zone '%s': %.1f °C", zone, val)
            return val
    except Exception:
        pass  # missing file or corrupt data — use the default
    return default


def _persist_setpoint(zone: str, value: float) -> None:
    """Write the current setpoint to disk (best-effort; never raises)."""
    try:
        existing: dict = {}
        if SETPOINT_FILE.exists():
            try:
                existing = json.loads(SETPOINT_FILE.read_text())
            except Exception:
                pass
        existing[zone] = value
        SETPOINT_FILE.write_text(json.dumps(existing))
    except Exception as exc:
        log.warning("Could not persist setpoint: %s", exc)


# ── Simulator classes ─────────────────────────────────────────────────────────

class HVACSimulator:
    """
    Single-zone HVAC simulator.
    target_temp can be updated at any time from the command callback.
    Python's GIL makes float assignment atomic — safe for cross-thread access.

    Setpoint is persisted to SETPOINT_FILE on every change and loaded at
    construction, so container restarts don't silently reset the target.
    """
    def __init__(self, zone: str = "main"):
        self.zone            = zone
        self.current_temp    = round(random.uniform(20.5, 23.5), 1)
        self.target_temp     = _load_persisted_setpoint(zone, default=21.0)
        self.CORRECTION_RATE = 0.12   # faster drift — more visible in demos
        self.NOISE_SIGMA     = 0.10   # reduced noise for cleaner convergence

    def tick(self) -> dict:
        error = self.target_temp - self.current_temp
        delta = error * self.CORRECTION_RATE + random.gauss(0, self.NOISE_SIGMA)
        self.current_temp = round(max(15.0, min(32.0, self.current_temp + delta)), 1)

        diff = self.current_temp - self.target_temp
        hvac_mode = "cooling" if diff > 0.3 else "heating" if diff < -0.3 else "idle"
        abs_diff  = abs(diff)
        fan_speed = "high" if abs_diff > 2.0 else "medium" if abs_diff > 0.5 else "low"

        return {
            "zone":                self.zone,
            "current_temperature": self.current_temp,
            "target_temperature":  self.target_temp,
            "hvac_mode":           hvac_mode,
            "fan_speed":           fan_speed,
            "unit":                "celsius",
            "timestamp":           _now(),
        }


class CO2Simulator:
    AMBIENT     = 400.0
    MIN_PPM     = 350.0
    MAX_PPM     = 1500.0
    NOISE_SIGMA = 8.0

    def __init__(self):
        self.level = random.uniform(430.0, 550.0)

    def tick(self, occupied: bool) -> dict:
        target = 550.0 if occupied else self.AMBIENT
        delta  = (target - self.level) * 0.05 + random.gauss(0, self.NOISE_SIGMA)
        self.level = round(max(self.MIN_PPM, min(self.MAX_PPM, self.level + delta)), 0)
        status = "normal" if self.level < 800 else "elevated" if self.level < 1000 else "high"
        return {"co2_level": int(self.level), "unit": "ppm", "status": status, "timestamp": _now()}


class OccupancySimulator:
    STAY_OCCUPIED = 0.90
    STAY_VACANT   = 0.85
    MAX_OCCUPANTS = 8

    def __init__(self):
        self.occupied       = random.random() > 0.4
        self.occupant_count = random.randint(1, 4) if self.occupied else 0

    def tick(self) -> dict:
        if self.occupied:
            if random.random() > self.STAY_OCCUPIED:
                self.occupied       = False
                self.occupant_count = 0
            else:
                delta = random.choice([-1, 0, 0, 0, 1])
                self.occupant_count = max(1, min(self.MAX_OCCUPANTS,
                                                  self.occupant_count + delta))
        else:
            if random.random() > self.STAY_VACANT:
                self.occupied       = True
                self.occupant_count = random.randint(1, 3)

        return {
            "occupancy_status": "occupied" if self.occupied else "vacant",
            "occupant_count":   self.occupant_count,
            "timestamp":        _now(),
        }


# ── Command handling ──────────────────────────────────────────────────────────

def _handle_hvac_command(state: dict, topic: str, command: dict) -> None:
    """
    Apply a validated setpoint command to the HVACSimulator.
    Runs in paho's network thread — only writes a float (GIL-safe).
    """
    hvac = state.get("hvac")
    if hvac is None:
        log.error("HVACSimulator not in state dict — cannot apply command")
        return

    # Extract zone from topic: basis/hvac/<zone>/command
    parts = topic.split("/")
    if len(parts) < 3:
        log.warning("Unexpected command topic format: %s", topic)
        return
    zone = parts[2]
    if zone != hvac.zone:
        log.debug("Command for zone '%s' ignored — this simulator is zone '%s'", zone, hvac.zone)
        return

    # Validate temperature
    raw_temp = command.get("target_temperature")
    if raw_temp is None:
        log.warning("Command missing 'target_temperature': %s", command)
        return

    try:
        new_temp = float(raw_temp)
    except (TypeError, ValueError):
        log.warning("Invalid 'target_temperature' value: %r", raw_temp)
        return

    if not (TEMP_MIN <= new_temp <= TEMP_MAX):
        log.warning(
            "Temperature %.1f°C out of range [%.1f, %.1f] — command dropped",
            new_temp, TEMP_MIN, TEMP_MAX,
        )
        return

    old_temp         = hvac.target_temp
    hvac.target_temp = new_temp
    _persist_setpoint(zone, new_temp)   # survive container restarts
    requested_by = command.get("requested_by", "unknown")
    log.info(
        "✓ Setpoint updated: %.1f → %.1f °C  (zone=%s, requested_by=%s)",
        old_temp, new_temp, zone, requested_by,
    )


# ── MQTT helpers ──────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _publish(client: mqtt.Client, topic: str, payload: dict, qos: int = 0) -> None:
    result = client.publish(topic, json.dumps(payload), qos=qos)
    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        log.warning("Publish failed on %s (rc=%d)", topic, result.rc)


_RC_MESSAGES = {
    1: "incorrect protocol version",
    2: "invalid client identifier",
    3: "broker unavailable",
    4: "bad username or password — check MQTT_USERNAME and MQTT_PASSWORD env vars",
    5: "not authorized — client not permitted by broker ACL",
}


def on_connect(client: mqtt.Client, userdata: dict, flags, rc: int) -> None:
    if rc == 0:
        auth_desc = f"user={MQTT_USERNAME}" if MQTT_USERNAME else "anonymous"
        log.info(
            "Connected to MQTT broker at %s:%d  auth=%s",
            BROKER_HOST, BROKER_PORT, auth_desc,
        )
        client.publish(TOPIC_STATUS, "online", qos=1, retain=True)
        # Subscribe to command topics — must happen in on_connect so it
        # re-subscribes automatically after any broker reconnect.
        client.subscribe(TOPIC_CMD_HVAC, qos=1)
        log.info("Subscribed to command topic: %s", TOPIC_CMD_HVAC)
    else:
        reason = _RC_MESSAGES.get(rc, f"unknown error code {rc}")
        log.error("MQTT connection refused (rc=%d): %s", rc, reason)


def on_disconnect(client: mqtt.Client, userdata, rc: int) -> None:
    if rc != 0:
        log.warning("MQTT disconnected unexpectedly (rc=%d) — paho will reconnect", rc)


def on_message(client: mqtt.Client, userdata: dict, msg: mqtt.MQTTMessage) -> None:
    """Receives command messages in paho's background thread."""
    topic = msg.topic
    try:
        command = json.loads(msg.payload.decode("utf-8"))
    except Exception as exc:
        log.warning("Unparseable command on %s: %s", topic, exc)
        return

    log.info("Command received on %s: %s", topic, command)

    if "command" in topic:
        _handle_hvac_command(userdata, topic, command)


def connect_with_retry(client: mqtt.Client) -> None:
    while True:
        try:
            client.connect(BROKER_HOST, BROKER_PORT, keepalive=60)
            return
        except Exception as exc:
            log.warning("Broker not ready (%s) — retrying in 5s", exc)
            time.sleep(5)


# ── Main loop ─────────────────────────────────────────────────────────────────

def main() -> None:
    log.info(
        "Basis OT Simulator starting — broker=%s:%d  tick=%ds",
        BROKER_HOST, BROKER_PORT, TICK_INTERVAL,
    )

    hvac      = HVACSimulator(zone="main")
    co2       = CO2Simulator()
    occupancy = OccupancySimulator()

    # userdata dict is shared with MQTT callbacks — allows on_message to
    # update simulator state without globals.
    state = {"hvac": hvac, "co2": co2, "occupancy": occupancy}

    client = mqtt.Client(client_id="basis-simulator-01", userdata=state)
    client.on_connect    = on_connect
    client.on_disconnect = on_disconnect
    client.on_message    = on_message
    client.will_set(TOPIC_STATUS, "offline", qos=1, retain=True)

    # Stage 6: authenticate to broker if credentials are provided
    if MQTT_USERNAME:
        client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        log.info("MQTT simulator identity: username=%s  broker=%s:%d",
                 MQTT_USERNAME, BROKER_HOST, BROKER_PORT)
    else:
        log.warning(
            "MQTT simulator running WITHOUT credentials (anonymous). "
            "Set MQTT_USERNAME and MQTT_PASSWORD to enable authenticated connections."
        )

    connect_with_retry(client)
    client.loop_start()

    log.info(
        "Simulator running — HVAC every %ds, CO2 every %ds, "
        "Occupancy every %ds, listening for commands on %s",
        TICK_INTERVAL,
        TICK_INTERVAL * CO2_TICK_EVERY,
        TICK_INTERVAL * OCCUPANCY_TICK_EVERY,
        TOPIC_CMD_HVAC,
    )

    tick = 0
    while True:
        tick += 1

        if tick % OCCUPANCY_TICK_EVERY == 0:
            occ_data = occupancy.tick()
            _publish(client, TOPIC_OCCUPANCY, occ_data)
            log.info(
                "Occupancy  status=%-8s  count=%d",
                occ_data["occupancy_status"], occ_data["occupant_count"],
            )

        if tick % CO2_TICK_EVERY == 0:
            co2_data = co2.tick(occupied=occupancy.occupied)
            _publish(client, TOPIC_CO2, co2_data)
            log.info(
                "CO2        level=%4d ppm  status=%s",
                co2_data["co2_level"], co2_data["status"],
            )

        hvac_data = hvac.tick()
        _publish(client, TOPIC_HVAC, hvac_data)
        log.info(
            "HVAC       current=%.1f°C  target=%.1f°C  mode=%-8s  fan=%s",
            hvac_data["current_temperature"],
            hvac_data["target_temperature"],
            hvac_data["hvac_mode"],
            hvac_data["fan_speed"],
        )

        time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    main()
