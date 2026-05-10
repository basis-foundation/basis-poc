"""
Basis Foundation — FastAPI Backend
Stage 4: Identity-aware HVAC control commands added.
"""

import asyncio
import os
import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers.protected import router as protected_router
from routers.telemetry import router as telemetry_router
from routers.controls  import router as controls_router
from mqtt_client import mqtt_listener

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
        "**Stage 4**: Role-gated HVAC control commands via MQTT.\n\n"
        "Protected endpoints require a Keycloak Bearer token (click **Authorize**)."
    ),
    version="0.4.0",
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

# ── Lifecycle ─────────────────────────────────────────────────────────────────
_mqtt_task: asyncio.Task | None = None


@app.on_event("startup")
async def startup() -> None:
    global _mqtt_task
    log.info("Basis API v0.4.0 starting up (Stage 4)")
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
    return {"service": "basis-api", "version": "0.4.0", "stage": 4, "docs": "/docs"}


@app.get("/health", tags=["meta"])
def health():
    from ws_manager import broadcaster
    return {
        "status": "ok",
        "service": "basis-api",
        "version": "0.4.0",
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
        "stage": 4,
        "features": {
            "auth":      True,
            "telemetry": True,
            "controls":  True,
            "audit":     False,  # Stage 5
        },
    }
