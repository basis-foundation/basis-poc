"""
Basis Foundation — Authentication & Authorization
Stage 7: Identity-aware policy architecture.

Authentication flow (unchanged from Stage 6):
  1. Extract Bearer token from Authorization header
  2. Read kid (key ID) from JWT header
  3. Fetch Keycloak's JWKS (cached 5 min, force-refreshed on unknown kid)
  4. Decode & validate: signature, expiry, issuer
  5. Resolve JWT payload → Subject via subject_from_jwt()

Authorization flow (new in Stage 7):
  6. PolicyEngine evaluates Subject + action + optional resource_id
  7. RoleBasedPolicy checks _ACTION_ROLES table → PolicyResult
  8. Allowed: return Subject to handler
     Denied:  record audit event, raise HTTP 403

Why require_action() replaces require_role()
─────────────────────────────────────────────
require_role("operator", "admin") couples each endpoint to the current role names.
require_action("write:hvac:setpoint") decouples the endpoint from the role model.
The mapping from action → roles lives in policy/rbac.py, not scattered across routers.

This means:
  - Adding a "supervisor" role that can send HVAC commands = 1 line in rbac.py.
  - The setpoint endpoint is untouched.

require_role() is preserved as a legacy shim. It is no longer called by any
BASIS router in Stage 7 but remains for backward compatibility and as a
fallback during incremental migrations.

Subject resolution
──────────────────
subject_from_jwt() translates the raw JWT payload dict into a typed Subject.
This happens once per request at the authentication boundary. All downstream
code (policy evaluation, audit recording, route handlers) works with Subject.

Example — Bob authenticates:
  JWT payload → {"sub": "a7b8...", "preferred_username": "bob",
                  "realm_access": {"roles": ["operator", ...]}, ...}
  Subject     → Subject(id="a7b8...", name="bob", type=HUMAN,
                        roles=["operator", ...], email="bob@basis.local")
  Action      → "write:hvac:setpoint"
  PolicyResult → allowed=True (operator is in WRITE_HVAC_SETPOINT roles)
  Audit        → AUDIT outcome=allowed  subject=bob  action=write:hvac:setpoint  ...
"""

import os
import time
import logging
from typing import Optional

import httpx
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError

from audit import audit_logger
from domain.events import AuditEvent
from domain.subject import Subject, subject_from_jwt
from policy import engine as policy_engine

log = logging.getLogger("basis.auth")

# ── Configuration ─────────────────────────────────────────────────────────────
# Internal URL — used for JWKS fetching (container-to-container)
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")

# External URL — used for issuer validation.
# The token's `iss` claim is set by Keycloak from the browser-facing hostname,
# so it must match what the browser used to reach Keycloak, not the internal hostname.
# In Codespaces this is the forwarded-port URL (e.g. https://<name>-18080.app.github.dev).
KEYCLOAK_EXTERNAL_URL = os.getenv("KEYCLOAK_EXTERNAL_URL", "http://localhost:18080")

KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "basis")

JWKS_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
EXPECTED_ISSUER = f"{KEYCLOAK_EXTERNAL_URL}/realms/{KEYCLOAK_REALM}"

# Logged once at import time so the issuer expectation is visible in startup output.
log.info("Auth configured — JWKS: %s  expected_issuer: %s", JWKS_URL, EXPECTED_ISSUER)

JWKS_TTL_SECONDS = 300  # refresh JWKS cache every 5 minutes

# ── JWKS Cache ────────────────────────────────────────────────────────────────
# Mutable dict so functions can update it without global declarations.
_jwks: dict = {"keys": [], "fetched_at": 0.0}


async def _fetch_jwks(force: bool = False) -> list[dict]:
    """
    Return the list of JWK keys from Keycloak's JWKS endpoint.
    Results are cached for JWKS_TTL_SECONDS seconds.
    Pass force=True to bypass the cache (e.g., after an unknown-kid response).
    """
    now = time.monotonic()
    stale = (now - _jwks["fetched_at"]) > JWKS_TTL_SECONDS

    if force or not _jwks["keys"] or stale:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(JWKS_URL, timeout=5.0)
                resp.raise_for_status()
                data = resp.json()
                _jwks["keys"] = data.get("keys", [])
                _jwks["fetched_at"] = now
                log.info(
                    "JWKS refreshed from %s — %d key(s) loaded",
                    JWKS_URL, len(_jwks["keys"]),
                )
        except Exception as exc:
            if not _jwks["keys"]:
                # No cached keys — cannot validate anything
                log.error("JWKS fetch failed and cache is empty: %s", exc)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Identity provider unavailable — cannot validate credentials.",
                )
            # Use stale cache rather than failing all requests
            log.warning("JWKS refresh failed (%s) — serving stale cached keys", exc)

    return _jwks["keys"]


# ── Token Validation ──────────────────────────────────────────────────────────
async def validate_token(token: str) -> dict:
    """
    Fully validate a Keycloak JWT access token.

    Checks:
      - Well-formed JWT structure
      - Signature (via matching JWKS key)
      - Expiry (exp claim)
      - Issuer (iss claim must match EXPECTED_ISSUER)

    Returns the decoded payload dict on success.
    Raises HTTP 401 on any failure.
    """
    # Step 1: read the JWT header without verifying — we need the kid
    try:
        header = jwt.get_unverified_header(token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    kid = header.get("kid")

    # Step 2: find the matching signing key
    keys = await _fetch_jwks()
    matching = [k for k in keys if k.get("kid") == kid]

    if not matching:
        # Unknown kid — Keycloak may have rotated its keys; force a refresh
        log.info("kid=%s not in cache, forcing JWKS refresh", kid)
        keys = await _fetch_jwks(force=True)
        matching = [k for k in keys if k.get("kid") == kid]

    if not matching:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token signed with unknown key.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Step 3: decode and validate
    # Before full verification, peek at the unverified claims so we can log a
    # precise failure reason (especially issuer mismatches, which are the most
    # common cause of auth failures in proxied/Codespaces environments).
    try:
        unverified = jwt.get_unverified_claims(token)
        token_iss  = unverified.get("iss", "(missing)")
        token_sub  = unverified.get("preferred_username") or unverified.get("sub", "(unknown)")
        if token_iss != EXPECTED_ISSUER:
            log.warning(
                "JWT issuer mismatch — expected=%r  got=%r  subject=%s",
                EXPECTED_ISSUER, token_iss, token_sub,
            )
    except Exception:
        token_iss = "(unreadable)"
        token_sub = "(unknown)"

    try:
        payload = jwt.decode(
            token,
            matching[0],          # python-jose accepts a JWK dict directly
            algorithms=["RS256"],
            # Keycloak access tokens may not include `aud` for the API client,
            # so we skip audience verification and rely on issuer + signature.
            options={"verify_aud": False},
            issuer=EXPECTED_ISSUER,
        )
        return payload

    except JWTError as exc:
        # Log the specific failure so it's diagnosable in docker compose logs api.
        log.warning(
            "JWT validation failed — kid=%s  iss=%r  subject=%s: %s",
            kid, token_iss, token_sub, exc,
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Role Helpers (legacy — used by require_role shim and /me endpoint) ────────
def get_roles(payload: dict) -> list[str]:
    """
    Extract realm roles from a decoded JWT payload.

    Keycloak stores realm roles at: payload["realm_access"]["roles"]
    Example: ["viewer", "default-roles-basis", "offline_access", "uma_authorization"]

    Prefer subject.roles when working with a Subject object.
    This function is retained for the /me endpoint and the require_role() shim.
    """
    return payload.get("realm_access", {}).get("roles", [])


def has_any_role(payload: dict, *roles: str) -> bool:
    """Return True if the user holds at least one of the given roles."""
    user_roles = set(get_roles(payload))
    return bool(user_roles & set(roles))


# ── FastAPI Dependencies ───────────────────────────────────────────────────────
_bearer = HTTPBearer(
    scheme_name="Keycloak Bearer Token",
    description="Paste a Keycloak access token to authorize Swagger UI requests.",
)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
) -> dict:
    """
    FastAPI dependency — validates the Bearer token and returns the raw JWT payload.

    Used by:
      - get_current_subject() (wraps this to produce a Subject)
      - /api/me endpoint (needs raw JWT fields like iss and exp)
      - require_role() shim (legacy path)

    New code should prefer get_current_subject() or require_action().
    """
    return await validate_token(credentials.credentials)


async def get_current_subject(
    payload: dict = Depends(get_current_user),
) -> Subject:
    """
    FastAPI dependency — validates the Bearer token and returns a typed Subject.

    This is the preferred dependency for endpoints that need identity information
    without an authorization gate (e.g., /api/me).

    For endpoints that also need authorization, use require_action() instead —
    it calls get_current_user internally and returns a Subject on success.
    """
    return subject_from_jwt(payload)


# ── Stage 7: require_action() — primary authorization dependency ───────────────
def require_action(action: str, resource_id: Optional[str] = None):
    """
    FastAPI dependency factory — enforces that the caller is authorized to
    perform the specified action, evaluated by the PolicyEngine.

    Usage:
        @router.post("/hvac/{zone}/setpoint")
        async def set_setpoint(
            subject: Subject = Depends(require_action("write:hvac:setpoint")),
        ):
            # subject is a fully resolved Subject; authorization is already confirmed.
            ...

    Flow:
        1. Validate Bearer token → JWT payload (via get_current_user)
        2. Resolve JWT payload → Subject (via subject_from_jwt)
        3. PolicyEngine.evaluate(subject, action, resource_id) → PolicyResult
        4. Record AuditEvent (allowed or denied — always recorded)
        5a. Allowed → return Subject to the handler
        5b. Denied  → raise HTTP 403 with the policy's reason

    Why this returns Subject (not dict):
        Route handlers receive typed domain objects, not raw JWT dicts.
        subject.name, subject.id, subject.roles — no more .get() with defaults.

    Why resource_id is optional here:
        For path-parameterized resources (e.g., /hvac/{zone}/setpoint), the
        zone is not known at dependency setup time. Pass resource_id=None here;
        the handler records the resource in its command_dispatch audit event.
        Stage 8 will introduce zone-scoped policies that need resource_id.
    """
    async def _enforce(
        request: Request,
        payload: dict = Depends(get_current_user),
    ) -> Subject:
        subject  = subject_from_jwt(payload)
        result   = policy_engine.evaluate(subject, action, resource_id)
        endpoint = f"{request.method} {request.url.path}"

        # Record the authorization decision — always, regardless of outcome.
        # Audit failures are non-fatal (AuditLogger swallows exceptions).
        await audit_logger.record(AuditEvent(
            subject_id=subject.id,
            subject_name=subject.name,
            subject_type=subject.type.value,
            subject_roles=subject.roles,
            action=action,
            resource_id=resource_id,
            endpoint=endpoint,
            outcome="allowed" if result.allowed else "denied",
            reason=None if result.allowed else result.reason,
        ))

        if not result.allowed:
            log.warning(
                "403  subject='%s'  type=%s  roles=%s  action='%s'  policy=%s",
                subject.name, subject.type.value, subject.roles,
                action, result.evaluated_by,
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=result.reason,
            )

        return subject

    return _enforce


# ── Legacy shim: require_role() ────────────────────────────────────────────────
def require_role(*roles: str):
    """
    Legacy FastAPI dependency factory — enforces that the caller holds at least
    one of the specified realm roles.

    Stage 7 status: SHIM — no longer called by any BASIS router.
    All routers have been migrated to require_action().

    Retained for:
      - Backward compatibility if external code depends on this function.
      - As a fallback during future incremental migrations.
      - Reference: documents what require_action() replaced.

    The original implementation is preserved unchanged so that any existing
    caller continues to receive exactly the same behavior as Stage 6.
    Returns the raw JWT payload dict (not a Subject) — callers must use
    user.get("preferred_username") etc. as before.
    """
    async def _enforce(
        request: Request,
        user: dict = Depends(get_current_user),
    ) -> dict:
        username   = user.get("preferred_username", "unknown")
        subject_id = user.get("sub", "unknown")
        user_roles = get_roles(user)
        endpoint   = f"{request.method} {request.url.path}"

        if not has_any_role(user, *roles):
            reason = (
                f"Access denied. Required role: {' or '.join(roles)}. "
                f"Your roles: {user_roles or ['(none)']}"
            )
            log.warning(
                "403 for user='%s' roles=%s — required one of %s",
                username, user_roles, list(roles),
            )
            await audit_logger.record(AuditEvent(
                subject_id=subject_id,
                subject_name=username,
                subject_roles=user_roles,
                action="api_access",
                endpoint=endpoint,
                outcome="denied",
                reason=reason,
            ))
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=reason,
            )

        await audit_logger.record(AuditEvent(
            subject_id=subject_id,
            subject_name=username,
            subject_roles=user_roles,
            action="api_access",
            endpoint=endpoint,
            outcome="allowed",
        ))
        return user

    return _enforce
