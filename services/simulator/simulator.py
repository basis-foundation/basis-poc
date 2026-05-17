"""
Basis Foundation — OT Device Simulator
Stage 6: Authenticated MQTT connections (MQTT_USERNAME / MQTT_PASSWORD).

Topics published:
  basis/hvac/main/telemetry                every 3 seconds
  basis/sensors/co2/telemetry              every 6 seconds  (every 2nd HVAC tick)
  basis/sensors/occupancy/telemetry        every 12 seconds (every 4th HVAC tick)
  basis/datacenter/dc-boise-01/telemetry   every 9 seconds  (every 3rd HVAC tick)

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
DC_TICK_EVERY        = 3    # publish data-center telemetry every N ticks (~9s)

TOPIC_HVAC        = "basis/hvac/main/telemetry"
TOPIC_CO2         = "basis/sensors/co2/telemetry"
TOPIC_OCCUPANCY   = "basis/sensors/occupancy/telemetry"
TOPIC_DATACENTER  = "basis/datacenter/dc-boise-01/telemetry"
TOPIC_STATUS      = "basis/simulator/status"
TOPIC_CMD_HVAC    = "basis/hvac/+/command"   # wildcard — matches any zone

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


class DataCenterSimulator:
    """
    Simulates a single data center site (dc-boise-01) with:
      - 3 server racks (rack-a12, rack-b08, rack-c04)  — inlet temperatures
      - Thermal aisle monitoring                        — cold/hot aisle temps
      - CRAC cooling unit                               — fan speed, supply/return air
      - PDU power distribution unit                     — load %, kW
      - UPS                                             — battery %, runtime, utility status
      - Environmental sensors                           — humidity, leak, smoke

    All values drift slowly with Gaussian noise to keep the dashboard alive.
    Status thresholds are realistic for a small AI/edge inference data center.
    """

    # ── Rack inlet temperature thresholds (ASHRAE A2 envelope) ────────────────
    RACK_WARN_C     = 27.0    # inlet temps above this → warning
    RACK_CRIT_C     = 30.0    # inlet temps above this → critical

    # ── PDU load thresholds ────────────────────────────────────────────────────
    PDU_WARN_PCT    = 70.0    # load above this → warning
    PDU_OVERLOAD_PCT = 90.0   # load above this → overload

    # ── Rack capacity (approx kW per rack at full load) ───────────────────────
    RACK_KW_EACH    = 8.0     # 3 racks × 8 kW ≈ 24 kW base + overhead

    def __init__(self, site_id: str = "dc-boise-01"):
        self.site_id = site_id

        # Rack inlet temperatures — start within normal range
        self._rack_inlet = {
            "rack-a12": random.uniform(23.0, 26.0),
            "rack-b08": random.uniform(22.5, 25.5),
            "rack-c04": random.uniform(23.5, 26.5),
        }

        # Thermal — cold aisle cools the rack fronts; hot aisle exhausts rear heat
        self._cold_aisle_temp = random.uniform(19.0, 22.0)
        self._hot_aisle_temp  = random.uniform(30.0, 34.0)

        # CRAC (computer room air conditioning) unit
        self._fan_speed_pct   = random.uniform(55.0, 70.0)
        self._supply_air_temp = random.uniform(16.0, 19.0)
        self._return_air_temp = random.uniform(27.0, 31.0)

        # PDU — target ~65 % load for a normally loaded demo environment
        self._pdu_load_pct    = random.uniform(55.0, 70.0)
        self._pdu_kw          = self._pdu_load_pct / 100.0 * (self.RACK_KW_EACH * 3 * 1.3)

        # UPS — assume utility is nominal; battery at 100 %
        self._battery_pct     = random.uniform(97.0, 100.0)
        self._runtime_min     = random.uniform(44.0, 52.0)
        self._utility_ok      = True

        # Environment
        self._humidity_pct    = random.uniform(40.0, 50.0)
        self._leak_detected   = False
        self._smoke_detected  = False

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _drift(self, value: float, sigma: float, lo: float, hi: float) -> float:
        """Apply small Gaussian drift, clamped to [lo, hi]."""
        return round(max(lo, min(hi, value + random.gauss(0, sigma))), 1)

    def _rack_status(self, temp: float) -> str:
        if temp >= self.RACK_CRIT_C:
            return "critical"
        if temp >= self.RACK_WARN_C:
            return "warning"
        return "normal"

    def _pdu_status(self, load_pct: float) -> str:
        if load_pct >= self.PDU_OVERLOAD_PCT:
            return "overload"
        if load_pct >= self.PDU_WARN_PCT:
            return "warning"
        return "normal"

    # ── Tick ──────────────────────────────────────────────────────────────────

    def tick(self) -> dict:
        # Drift rack inlet temperatures
        for rack_id in self._rack_inlet:
            self._rack_inlet[rack_id] = self._drift(
                self._rack_inlet[rack_id], sigma=0.15, lo=20.0, hi=32.0
            )

        # Drift thermal aisle temps — hot aisle roughly tracks rack inlet heat
        avg_inlet = sum(self._rack_inlet.values()) / len(self._rack_inlet)
        self._cold_aisle_temp = self._drift(self._cold_aisle_temp, 0.10, 17.0, 24.0)
        self._hot_aisle_temp  = self._drift(
            max(avg_inlet + 6.0, self._hot_aisle_temp), 0.15, 28.0, 40.0
        )
        delta_t = round(self._hot_aisle_temp - self._cold_aisle_temp, 1)

        # Drift CRAC — fan speed rises when hot aisle is hot
        fan_target = 50.0 + (self._hot_aisle_temp - 30.0) * 3.0
        self._fan_speed_pct   = self._drift(
            (self._fan_speed_pct + fan_target) / 2, 0.5, 30.0, 98.0
        )
        self._supply_air_temp = self._drift(self._supply_air_temp, 0.08, 14.0, 21.0)
        self._return_air_temp = self._drift(self._return_air_temp, 0.10, 25.0, 35.0)
        crac_mode = (
            "cooling"     if self._fan_speed_pct > 35.0 else
            "standby"     if self._fan_speed_pct > 10.0 else
            "maintenance"
        )

        # Drift PDU load — slight variance around 65 %
        self._pdu_load_pct = self._drift(self._pdu_load_pct, 0.4, 40.0, 92.0)
        self._pdu_kw = round(self._pdu_load_pct / 100.0 * (self.RACK_KW_EACH * 3 * 1.3), 1)

        # UPS — stays fully charged when utility is OK
        if self._utility_ok:
            self._battery_pct = min(100.0, self._battery_pct + 0.05)
            self._runtime_min = self._drift(self._runtime_min, 0.2, 40.0, 60.0)
        else:
            self._battery_pct = max(0.0, self._battery_pct - 0.5)
            self._runtime_min = max(0.0, self._runtime_min - 1.0)

        ups_status = (
            "critical"   if self._battery_pct < 20 else
            "on_battery" if not self._utility_ok   else
            "normal"
        )

        # Environment — humidity drifts gently
        self._humidity_pct = self._drift(self._humidity_pct, 0.3, 30.0, 65.0)

        return {
            "event_type": "datacenter.telemetry",
            "site_id":    self.site_id,
            "timestamp":  _now(),
            "racks": [
                {
                    "rack_id":       rack_id,
                    "inlet_temp_c":  temp,
                    "status":        self._rack_status(temp),
                }
                for rack_id, temp in self._rack_inlet.items()
            ],
            "thermal": {
                "cold_aisle_temp_c": self._cold_aisle_temp,
                "hot_aisle_temp_c":  self._hot_aisle_temp,
                "delta_t_c":         delta_t,
            },
            "cooling": {
                "unit_id":            "crac-1",
                "mode":               crac_mode,
                "fan_speed_percent":  round(self._fan_speed_pct, 1),
                "supply_air_temp_c":  self._supply_air_temp,
                "return_air_temp_c":  self._return_air_temp,
            },
            "power": {
                "pdu_id":       "pdu-a",
                "load_percent": round(self._pdu_load_pct, 1),
                "kw":           self._pdu_kw,
                "status":       self._pdu_status(self._pdu_load_pct),
            },
            "ups": {
                "ups_id":          "ups-1",
                "battery_percent": round(self._battery_pct, 1),
                "runtime_minutes": round(self._runtime_min, 0),
                "utility_power":   "normal" if self._utility_ok else "failed",
                "status":          ups_status,
            },
            "environment": {
                "humidity_percent": round(self._humidity_pct, 1),
                "leak_detected":    self._leak_detected,
                "smoke_detected":   self._smoke_detected,
            },
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

    hvac       = HVACSimulator(zone="main")
    co2        = CO2Simulator()
    occupancy  = OccupancySimulator()
    datacenter = DataCenterSimulator(site_id="dc-boise-01")

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
        "Occupancy every %ds, DataCenter every %ds, listening for commands on %s",
        TICK_INTERVAL,
        TICK_INTERVAL * CO2_TICK_EVERY,
        TICK_INTERVAL * OCCUPANCY_TICK_EVERY,
        TICK_INTERVAL * DC_TICK_EVERY,
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

        if tick % DC_TICK_EVERY == 0:
            dc_data = datacenter.tick()
            _publish(client, TOPIC_DATACENTER, dc_data)
            racks = dc_data["racks"]
            log.info(
                "DataCenter racks=[%s]  cold=%.1f°C  hot=%.1f°C  "
                "pdu=%.0f%%  ups=%s",
                ", ".join(f"{r['rack_id']}:{r['inlet_temp_c']:.1f}°C" for r in racks),
                dc_data["thermal"]["cold_aisle_temp_c"],
                dc_data["thermal"]["hot_aisle_temp_c"],
                dc_data["power"]["load_percent"],
                dc_data["ups"]["status"],
            )

        time.sleep(TICK_INTERVAL)


if __name__ == "__main__":
    main()
