"""
Basis Foundation — JWT Authentication & Authorization
Validates Keycloak-issued access tokens using the realm's JWKS endpoint.

Flow:
  1. Extract Bearer token from Authorization header
  2. Read kid (key ID) from JWT header — identifies which RSA key signed the token
  3. Fetch Keycloak's JWKS (cached, refreshed every 5 min or on unknown kid)
  4. Decode & validate: signature, expiry, issuer
  5. Extract realm_access.roles from payload
  6. Enforce role requirements via require_role() dependency factory
  7. Record authorization decision to audit log (Stage 5)
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

log = logging.getLogger("basis.auth")

# ── Configuration ─────────────────────────────────────────────────────────────
# Internal URL — used for JWKS fetching (container-to-container)
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://keycloak:8080")

# External URL — used for issuer validation.
# The token's `iss` claim is set by Keycloak from the browser-facing hostname,
# so it must match what the browser used to reach Keycloak, not the internal hostname.
KEYCLOAK_EXTERNAL_URL = os.getenv("KEYCLOAK_EXTERNAL_URL", "http://localhost:18080")

KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "basis")

JWKS_URL = f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
EXPECTED_ISSUER = f"{KEYCLOAK_EXTERNAL_URL}/realms/{KEYCLOAK_REALM}"

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
        log.warning("JWT validation failed for kid=%s: %s", kid, exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── Role Helpers ──────────────────────────────────────────────────────────────
def get_roles(payload: dict) -> list[str]:
    """
    Extract realm roles from a decoded JWT payload.

    Keycloak stores realm roles at: payload["realm_access"]["roles"]
    Example: ["viewer", "default-roles-basis", "offline_access", "uma_authorization"]
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
    FastAPI dependency — validates the Bearer token and returns the JWT payload.

    Inject into any endpoint that requires a logged-in user:
        async def my_endpoint(user = Depends(get_current_user)):
    """
    return await validate_token(credentials.credentials)


def require_role(*roles: str):
    """
    FastAPI dependency factory — enforces that the caller holds at least one
    of the specified realm roles.

    Usage:
        @router.get("/operator-only")
        async def op(user = Depends(require_role("operator", "admin"))):
            ...

    Returns HTTP 403 if the user is authenticated but lacks the required role.
    Returns HTTP 401 if no valid token is provided at all.

    Stage 5: Records every authorization decision (allowed and denied) to the
    audit log. The audit call is non-fatal — a logging failure will never
    affect the HTTP response.
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
