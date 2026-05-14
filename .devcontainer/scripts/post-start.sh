#!/usr/bin/env bash
# BASIS — Codespace restart handler
# Runs on every Codespace resume/restart (postStartCommand).
#
# Docker-in-Docker state does not persist across Codespace restarts — images,
# containers, and volumes start fresh each time. This script brings the stack
# back up and re-patches Keycloak (which re-imports the realm from scratch
# on every Docker restart).
#
# Images are already built, so startup is faster than postCreateCommand
# (~60–90 seconds, dominated by Keycloak realm import).

set -euo pipefail

# ── Helpers ────────────────────────────────────────────────────────────────────

log() { echo "[basis] $*"; }

# Stage 1: Wait for Keycloak's HTTP server.
# Checks master realm — does not confirm basis realm import is complete.
wait_for_keycloak_http() {
  local max_attempts=40  # 40 × 10s = ~6 min
  local attempt=1

  log "Waiting for Keycloak readiness..."

  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:18080/realms/master" > /dev/null 2>&1; then
      log "Keycloak HTTP server is up."
      return 0
    fi
    log "  [${attempt}/${max_attempts}] Keycloak starting..."
    sleep 10
    attempt=$((attempt + 1))
  done

  log "✗ Keycloak did not respond within the timeout."
  log "  Run: docker compose logs keycloak"
  return 1
}

# Stage 2: Wait for the basis realm import to complete.
wait_for_basis_realm() {
  local max_attempts=24  # 24 × 5s = 2 min
  local attempt=1

  log "Waiting for basis realm import..."

  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:18080/realms/basis" > /dev/null 2>&1; then
      log "basis realm is ready."
      return 0
    fi
    log "  [${attempt}/${max_attempts}] Waiting for basis realm..."
    sleep 5
    attempt=$((attempt + 1))
  done

  log "✗ basis realm was not available after ${max_attempts} attempts."
  log "  Run: docker compose logs keycloak"
  return 1
}

# Obtains a Keycloak admin token from the master realm, with retry.
get_admin_token() {
  local max_attempts=12  # 12 × 5s = 1 min
  local attempt=1
  local token

  log "Obtaining Keycloak admin token..."

  while [ $attempt -le $max_attempts ]; do
    token=$(curl -sf -X POST \
      "http://localhost:18080/realms/master/protocol/openid-connect/token" \
      --data-urlencode "grant_type=password" \
      --data-urlencode "client_id=admin-cli" \
      --data-urlencode "username=admin" \
      --data-urlencode "password=admin" \
      2>/dev/null \
      | python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token',''))" \
      2>/dev/null) || true

    if [ -n "${token:-}" ]; then
      log "  Admin token obtained."
      echo "$token"
      return 0
    fi

    log "  [${attempt}/${max_attempts}] Waiting for admin API..."
    sleep 5
    attempt=$((attempt + 1))
  done

  log "✗ Could not obtain Keycloak admin token after ${max_attempts} attempts."
  return 1
}

# Stage 3: Wait for basis-frontend client, then patch redirect URIs.
# Retries until the client is queryable — it may not exist immediately
# after the realm endpoint becomes available.
patch_keycloak_for_codespaces() {
  local fe_url="$1"
  local max_attempts=12  # 12 × 5s = 1 min
  local attempt=1
  local admin_token client_json client_count client_uuid http_status

  admin_token=$(get_admin_token) || return 1

  log "Waiting for basis-frontend client..."

  while [ $attempt -le $max_attempts ]; do
    client_json=$(curl -sf \
      -H "Authorization: Bearer $admin_token" \
      "http://localhost:18080/admin/realms/basis/clients?clientId=basis-frontend" \
      2>/dev/null) || true

    # Validate: must be a non-empty JSON array
    client_count=$(echo "${client_json:-[]}" \
      | python3 -c "import json,sys; print(len(json.load(sys.stdin)))" 2>/dev/null \
      || echo "0")

    if [ "${client_count}" -ge 1 ]; then
      log "  basis-frontend client found."
      break
    fi

    log "  [${attempt}/${max_attempts}] Waiting for basis-frontend client..."
    sleep 5
    attempt=$((attempt + 1))
  done

  if [ "${client_count:-0}" -lt 1 ]; then
    log "✗ basis-frontend client not found after ${max_attempts} attempts."
    log "  Run: docker compose logs keycloak"
    return 1
  fi

  # Extract and validate the client UUID
  client_uuid=$(echo "$client_json" \
    | python3 -c "
import json, sys
clients = json.load(sys.stdin)
if not clients:
    sys.exit(1)
c = clients[0]
if c.get('clientId') != 'basis-frontend':
    print(f'ERROR: unexpected clientId {c.get(\"clientId\")!r}', file=sys.stderr)
    sys.exit(1)
print(c['id'])
" 2>/dev/null) || true

  if [ -z "${client_uuid:-}" ]; then
    log "✗ Could not extract a valid UUID from basis-frontend client response."
    return 1
  fi

  log "Patching basis-frontend (id: ${client_uuid})"
  log "  Adding redirect URI: ${fe_url}"

  # Build updated client JSON. fe_url passed via env var to avoid
  # shell-interpolation issues inside the Python string literal.
  local updated_json
  updated_json=$(BASIS_FE_URL="$fe_url" python3 -c "
import json, sys, os

raw = sys.stdin.read()
clients = json.loads(raw)
if not clients:
    print('ERROR: empty client list', file=sys.stderr)
    sys.exit(1)

client = clients[0]
if client.get('clientId') != 'basis-frontend':
    print(f'ERROR: unexpected clientId {client.get(\"clientId\")!r}', file=sys.stderr)
    sys.exit(1)

fe_url      = os.environ['BASIS_FE_URL']
new_uris    = [fe_url + '/*', fe_url]
new_origins = [fe_url]

for u in new_uris:
    if u not in client.get('redirectUris', []):
        client.setdefault('redirectUris', []).append(u)

for o in new_origins:
    if o not in client.get('webOrigins', []):
        client.setdefault('webOrigins', []).append(o)

print(json.dumps(client))
" <<< "$client_json") || { log "✗ Failed to build updated client JSON."; return 1; }

  if [ -z "${updated_json:-}" ]; then
    log "✗ Updated client JSON is empty — aborting PUT."
    return 1
  fi

  # PUT the updated client. Keycloak returns 204 No Content on success.
  http_status=$(echo "$updated_json" | curl -sf -X PUT \
    -H "Authorization: Bearer $admin_token" \
    -H "Content-Type: application/json" \
    -d @- \
    -o /dev/null \
    -w "%{http_code}" \
    "http://localhost:18080/admin/realms/basis/clients/$client_uuid" \
    2>/dev/null) || true

  if [ "${http_status:-0}" = "204" ]; then
    log "Redirect URI patched successfully (HTTP 204)."
  else
    log "✗ Keycloak client update returned HTTP ${http_status:-unknown} (expected 204)."
    log "  Run: docker compose logs keycloak"
    return 1
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")/../.."

echo ""
log "BASIS Codespace restarting..."

IS_CODESPACES=false
if [ -n "${CODESPACE_NAME:-}" ]; then
  IS_CODESPACES=true
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  FE_URL="https://${CODESPACE_NAME}-5173.${DOMAIN}"
  log "Environment: GitHub Codespaces (${CODESPACE_NAME})"
else
  log "Environment: Local Dev Container"
fi

# Guard: if .env is missing, fall back to full setup
if [ ! -f ".env" ]; then
  log ".env not found — running full setup instead..."
  exec bash .devcontainer/scripts/post-create.sh
fi

# Bring services up. Images are cached — no rebuild needed.
log "Starting services (images already built — no rebuild)..."
docker compose up -d

echo ""
log "Services launched:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Wait for Keycloak in two stages, then patch
echo ""
wait_for_keycloak_http
echo ""
wait_for_basis_realm

if [ "$IS_CODESPACES" = "true" ]; then
  echo ""
  patch_keycloak_for_codespaces "$FE_URL"
fi

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
NAME="${CODESPACE_NAME:-}"

echo ""
log "✓ BASIS Codespaces environment ready."
if [ "$IS_CODESPACES" = "true" ] && [ -n "$NAME" ]; then
  log "  Operator Console → https://${NAME}-5173.${DOMAIN}"
  log "  API              → https://${NAME}-8000.${DOMAIN}/docs"
  log "  Keycloak Admin   → https://${NAME}-18080.${DOMAIN}/admin"
fi
echo ""
