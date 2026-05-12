"""
Basis Foundation — FastAPI Backend
Stage 6: MQTT security — adapters/ package introduced.
         mqtt_client.py → adapters/mqtt/subscriber.py
         mqtt_publisher.py → adapters/mqtt/publisher.py
         MQTT connections now use per-service credentials (MQTT_USERNAME/MQTT_PASSWORD).
         Mosquitto anonymous access disabled.
Stage 7: Identity-aware policy architecture.
         domain/subject.py  — Subject model + SubjectType enum (HUMAN, DEVICE, SERVICE, GATEWAY, AGENT)
         policy/engine.py   — PolicyEngine: chain-of-responsibility authorization evaluation
         policy/rbac.py     — RoleBasedPolicy: centralizes the role→action mapping
         policy/actions.py  — Named action constants (write:hvac:setpoint, read:audit:log, ...)
         auth.py            — require_action() replaces require_role() in all routers;
                              subject_from_jwt() translates JWT → Subject at the auth boundary.
         All routers now receive typed Subject objects instead of raw JWT dicts.
         External API behavior is identical. Internal authorization path is formalized.
Stage 8: Resource model introduction.
         domain/resource.py — Resource model, ResourceType enum (HVAC/SENSOR/ZONE/DEVICE/GATEWAY),
                              ResourceIdentifier helper, static registry, resolve_resource(),
                              list_resources()
         routers/resources.py — GET /api/resources, GET /api/resources/{id}
         controls.py        — zone validation now registry-driven; AuditEvents carry
                              resource_type as a first-class field alongside resource_id.
         domain/events.py   — resource_type field added to AuditEvent.
         audit/store.py     — rtype= emitted in log lines when resource_type is set.
"""

import asyncio
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.protected  import router as protected_router
from routers.telemetry  import router as telemetry_router
from routers.controls   import router as controls_router
from routers.audit      import router as audit_router
from routers.resources  import router as resources_router
from adapters.mqtt.subscriber import mqtt_listener

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)
log = logging.getLogger("basis.api")

# ── Configuration ─────────────────────────────────────────────────────────────
KEYCLOAK_URL          = os.getenv("KEYCLOAK_URL",          "http://keycloak:8080")
KEYCLOAK_EXTERNAL_URL = os.getenv("KEYCLOAK_EXTERNAL_URL", "http://localhost:18080")
KEYCLOAK_REALM        = os.getenv("KEYCLOAK_REALM",        "basis")
MQTT_BROKER_HOST      = os.getenv("MQTT_BROKER_HOST",      "mosquitto")
MQTT_BROKER_PORT      = int(os.getenv("MQTT_BROKER_PORT",  "1883"))
FRONTEND_URL          = os.getenv("FRONTEND_URL",          "http://localhost:5173")

# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(
    title="Basis Foundation API",
    description=(
        "Identity-aware access control for building automation and OT systems.\n\n"
        "**Stage 8**: Resource model. OT resources (HVAC, sensors, zones) are "
        "normalized typed objects. Zone validation is registry-driven. "
        "Audit events carry `resource_type` as a first-class field. "
        "`GET /api/resources` exposes the OT topology to API consumers.\n\n"
        "Protected endpoints require a Keycloak Bearer token (click **Authorize**)."
    ),
    version="0.8.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL, "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
app.include_router(protected_router)
app.include_router(telemetry_router)
app.include_router(controls_router)
app.include_router(audit_router)
app.include_router(resources_router)

# ── Lifecycle ─────────────────────────────────────────────────────────────────
_mqtt_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup() -> None:
    global _mqtt_task
    log.info("Basis API v0.8.0 starting up (Stage 8 — resource model introduction)")
    log.info("Keycloak internal:  %s/realms/%s", KEYCLOAK_URL, KEYCLOAK_REALM)
    log.info("Keycloak external:  %s/realms/%s", KEYCLOAK_EXTERNAL_URL, KEYCLOAK_REALM)
    log.info("MQTT broker:        %s:%d", MQTT_BROKER_HOST, MQTT_BROKER_PORT)
    log.info("Frontend origin:    %s", FRONTEND_URL)
    _mqtt_task = asyncio.create_task(mqtt_listener(), name="mqtt-listener")
    log.info("MQTT listener task started")


@app.on_event("shutdown")
async def shutdown() -> None:
    global _mqtt_task
    if _mqtt_task and not _mqtt_task.done():
        _mqtt_task.cancel()
        try:
            await _mqtt_task
        except asyncio.CancelledError:
            pass
    log.info("Basis API shut down cleanly")


# ── Public Routes ─────────────────────────────────────────────────────────────
@app.get("/", tags=["meta"])
def root():
    return {"service": "basis-api", "version": "0.8.0", "stage": 8, "docs": "/docs"}


@app.get("/health", tags=["meta"])
def health():
    from ws_manager import broadcaster
    return {
        "status": "ok",
        "service": "basis-api",
        "version": "0.8.0",
        "websocket_clients": broadcaster.client_count,
    }


@app.get("/config", tags=["meta"])
def config():
    return {
        "keycloak_url":          KEYCLOAK_URL,
        "keycloak_external_url": KEYCLOAK_EXTERNAL_URL,
        "keycloak_realm":        KEYCLOAK_REALM,
        "mqtt_broker_host":      MQTT_BROKER_HOST,
        "mqtt_broker_port":      MQTT_BROKER_PORT,
        "stage": 8,
        "features": {
            "auth":             True,
            "telemetry":        True,
            "controls":         True,
            "audit_log":        True,
            "audit_api":        False,  # returns 501 until Stage 5b
            "mqtt_auth":        True,   # broker requires credentials
            "policy_engine":    True,   # PolicyEngine + RoleBasedPolicy active
            "subject_model":    True,   # JWT → Subject resolution at auth boundary
            "resource_model":   True,   # Typed Resource objects; registry-driven validation
            "resource_api":     True,   # GET /api/resources exposes OT topology
        },
    }
