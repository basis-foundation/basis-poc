"""
BASIS — Subject Domain Model
Stage 7: Formalizes the identity of any entity that can perform actions in BASIS.

Why Subject exists
──────────────────
Prior stages passed raw JWT payload dicts through the entire stack:
  user.get("sub"), user.get("preferred_username"), get_roles(user), ...

That works for a single human actor authenticated via Keycloak, but it has no
room to grow. A BACnet gateway reporting telemetry, a service account running
automated tests, or a device with its own certificate — none of these fit in a
dict shaped around Keycloak JWT claims.

Subject gives the identity concept a name, a type, and a stable shape that the
policy layer can reason about regardless of where the identity came from.

SubjectType
───────────
The enum documents the intended identity space for an OT control plane:

  HUMAN   — a person authenticated via Keycloak OIDC.
              Current operational path. All JWT-authenticated callers are HUMAN.

  DEVICE  — a physical OT device (HVAC controller, sensor, PLC) that presents
              its own credential (device certificate, pre-shared key).
              Future: authenticated at the MQTT or gateway layer.

  SERVICE — an internal BASIS service process (e.g., simulator as an identified
              service identity rather than a shared MQTT username).
              Future: authenticated via a service-account JWT or mTLS.

  GATEWAY — a protocol translation layer (BACnet/IP → MQTT, Modbus TCP → REST).
              Future: authenticated as its own actor with scoped permissions.

  AGENT   — an autonomous software agent acting on behalf of a user or system.
              Future: agent JWTs with delegated subject claims.

Only HUMAN subjects are wired to the operational authentication path in Stage 7.
The other types exist to document the design space and ensure the model can
accommodate them without a breaking change when they are introduced.

subject_from_jwt()
──────────────────
This is the single translation point from raw JWT claims to typed domain objects.
All downstream code (policy engine, audit, routers) works with Subject — never
with raw payload dicts. This constraint makes it straightforward to test the
policy layer in isolation: inject a Subject with known fields instead of
constructing a realistic JWT payload.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SubjectType(str, Enum):
    """
    Classification of who or what is performing an action in BASIS.

    Using str as the enum base makes SubjectType JSON-serializable and
    compatible with Pydantic field validation without a custom encoder.
    This also means SubjectType values print as plain strings in logs.
    """
    HUMAN   = "human"    # Authenticated via OIDC/JWT — current operational path
    DEVICE  = "device"   # Physical OT device with its own identity credential
    SERVICE = "service"  # Internal BASIS service or adapter process
    GATEWAY = "gateway"  # Protocol bridge (BACnet/IP, Modbus TCP, OPC-UA)
    AGENT   = "agent"    # Autonomous software agent


class Subject(BaseModel):
    """
    The normalized identity of any entity performing an action in BASIS.

    Constructed once per request during token validation and passed through
    the authorization and audit path without modification. Treat as immutable.

    For HUMAN subjects (current path), fields map from Keycloak JWT claims:
      id    ← JWT "sub"                   (stable UUID across sessions)
      name  ← JWT "preferred_username"    (human-readable, used in logs)
      roles ← JWT "realm_access.roles"    (Keycloak realm role assignments)
      email ← JWT "email"                 (informational only)

    For future DEVICE / SERVICE / GATEWAY subjects, the same fields will be
    populated from device certificates, service tokens, or broker credentials.
    The policy layer does not care how the Subject was constructed — only what
    it contains.
    """

    id:    str                    # Stable unique identifier — JWT sub for humans
    name:  str                    # Human-readable label — preferred_username for humans
    type:  SubjectType = SubjectType.HUMAN
    roles: list[str]   = []       # Granted roles — from JWT realm_access.roles
    email: Optional[str] = None   # From JWT email claim — informational

    model_config = {"frozen": True}  # Immutable — created once, never mutated

    def has_role(self, *roles: str) -> bool:
        """Return True if this subject holds at least one of the given roles."""
        return bool(set(self.roles) & set(roles))

    def __str__(self) -> str:
        return f"{self.type.value}:{self.name}"


def subject_from_jwt(payload: dict) -> Subject:
    """
    Resolve a decoded Keycloak JWT payload into a typed Subject.

    This is the single translation boundary between the raw JWT world and the
    BASIS domain model. All callers receive a Subject; none receive a raw dict.

    Example — Bob's operator JWT resolves to:

      Input (decoded JWT payload):
        {
          "sub": "a7b8c9d0-1234-5678-abcd-ef0123456789",
          "preferred_username": "bob",
          "email": "bob@basis.local",
          "realm_access": {
            "roles": ["operator", "default-roles-basis", "offline_access"]
          },
          "iss": "http://localhost:18080/realms/basis",
          "exp": 1735000000
        }

      Output (Subject):
        Subject(
          id="a7b8c9d0-1234-5678-abcd-ef0123456789",
          name="bob",
          type=SubjectType.HUMAN,
          roles=["operator", "default-roles-basis", "offline_access"],
          email="bob@basis.local",
        )

    All JWT-authenticated callers are HUMAN in Stage 7. Other SubjectType
    values will be populated by future authentication paths (device certs,
    service tokens) that construct Subject directly without this function.
    """
    return Subject(
        id=payload.get("sub", "unknown"),
        name=payload.get("preferred_username", "unknown"),
        type=SubjectType.HUMAN,
        roles=payload.get("realm_access", {}).get("roles", []),
        email=payload.get("email"),
    )
