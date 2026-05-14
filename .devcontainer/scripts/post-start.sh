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

  # Progress messages go to stderr so that callers can capture the token cleanly:
  #   admin_token=$(get_admin_token)
  # captures only the token line; all status output appears in the terminal.
  log "Obtaining Keycloak admin token..." >&2

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
      log "  Admin token obtained." >&2
      echo "$token"   # stdout only — this is what the caller captures
      return 0
    fi

    log "  [${attempt}/${max_attempts}] Waiting for admin API..." >&2
    sleep 5
    attempt=$((attempt + 1))
  done

  log "✗ Could not obtain Keycloak admin token after ${max_attempts} attempts." >&2
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

  # Temp files keep all intermediate data off stdin/pipes.
  # Using pipes for large JSON blobs or Python scripts risks buffering issues
  # and stdin conflicts; files are unambiguous.
  local tmp_client tmp_script tmp_updated tmp_resp
  tmp_client=$(mktemp)
  tmp_script=$(mktemp)
  tmp_updated=$(mktemp)
  tmp_resp=$(mktemp)
  # Guaranteed cleanup whether we return 0 or 1 (bash RETURN trap)
  trap 'rm -f "$tmp_client" "$tmp_script" "$tmp_updated" "$tmp_resp"' RETURN

  # Get admin token — progress goes to stderr, token goes to stdout
  admin_token=$(get_admin_token) || return 1

  log "Waiting for basis-frontend client..."

  while [ $attempt -le $max_attempts ]; do
    client_json=$(curl -s \
      -H "Authorization: Bearer $admin_token" \
      "http://localhost:18080/admin/realms/basis/clients?clientId=basis-frontend" \
      2>/dev/null) || true

    # Validate: must be a non-empty JSON array
    client_count=$(printf '%s' "${client_json:-[]}" \
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

  # Write to temp file — all subsequent Python steps read from here, not stdin
  printf '%s' "$client_json" > "$tmp_client"

  # Extract and validate the client UUID
  client_uuid=$(python3 -c "
import json, sys
with open(sys.argv[1]) as f:
    clients = json.load(f)
if not clients:
    sys.exit(1)
c = clients[0]
if c.get('clientId') != 'basis-frontend':
    print(f'ERROR: unexpected clientId {c.get(\"clientId\")!r}', file=sys.stderr)
    sys.exit(1)
print(c['id'])
" "$tmp_client") || { log "✗ Could not extract a valid UUID from basis-frontend client."; return 1; }

  log "Patching basis-frontend (id: ${client_uuid})"
  log "  Frontend URL: ${fe_url}"

  # Write the transform script to a temp file.
  # Three URI forms cover the Keycloak OIDC redirect check:
  #   exact:          https://name-5173.app.github.dev
  #   trailing slash: https://name-5173.app.github.dev/
  #   wildcard:       https://name-5173.app.github.dev/*
  cat > "$tmp_script" << 'PYEOF'
import json, sys, os

with open(os.environ['TMP_IN']) as f:
    clients = json.load(f)

if not clients:
    print('ERROR: empty client list', file=sys.stderr)
    sys.exit(1)

client = clients[0]
if client.get('clientId') != 'basis-frontend':
    print(f'ERROR: unexpected clientId {client.get("clientId")!r}', file=sys.stderr)
    sys.exit(1)

fe_url   = os.environ['BASIS_FE_URL']
base_url = fe_url.rstrip('/')

new_uris    = [base_url, base_url + '/', base_url + '/*']
new_origins = [base_url]

for u in new_uris:
    if u not in client.get('redirectUris', []):
        client.setdefault('redirectUris', []).append(u)

for o in new_origins:
    if o not in client.get('webOrigins', []):
        client.setdefault('webOrigins', []).append(o)

with open(os.environ['TMP_OUT'], 'w') as f:
    json.dump(client, f)
PYEOF

  TMP_IN="$tmp_client" TMP_OUT="$tmp_updated" BASIS_FE_URL="$fe_url" \
    python3 "$tmp_script" \
    || { log "✗ Failed to build updated client JSON."; return 1; }

  if [ ! -s "$tmp_updated" ]; then
    log "✗ Updated client JSON is empty — aborting PUT."
    return 1
  fi

  # PUT the updated client representation to Keycloak.
  # No -f flag: we need the response body on failure for diagnostics.
  # Keycloak returns 204 No Content on success, empty body.
  log "Sending PUT to Keycloak Admin API..."
  http_status=$(curl -s -X PUT \
    -H "Authorization: Bearer $admin_token" \
    -H "Content-Type: application/json" \
    --data-binary "@$tmp_updated" \
    -o "$tmp_resp" \
    -w "%{http_code}" \
    "http://localhost:18080/admin/realms/basis/clients/$client_uuid")

  if [ "${http_status:-0}" != "204" ]; then
    log "✗ Keycloak PUT returned HTTP ${http_status:-unknown} (expected 204)."
    log "  Response body: $(cat "$tmp_resp" 2>/dev/null || echo '(empty)')"
    log "  Run: docker compose logs keycloak"
    return 1
  fi

  log "PUT accepted (HTTP 204). Verifying persisted configuration..."

  # Verification: re-GET the client and confirm all required URIs were written.
  # Fails loudly if any URI is missing — do not silently continue.
  local verify_json
  verify_json=$(curl -s \
    -H "Authorization: Bearer $admin_token" \
    "http://localhost:18080/admin/realms/basis/clients?clientId=basis-frontend" \
    2>/dev/null) || true

  printf '%s' "$verify_json" > "$tmp_client"

  cat > "$tmp_script" << 'PYEOF'
import json, sys, os

with open(os.environ['TMP_IN']) as f:
    clients = json.load(f)

if not clients:
    print('ERROR: empty verification response', file=sys.stderr)
    sys.exit(1)

client = clients[0]
fe_url   = os.environ['BASIS_FE_URL']
base_url = fe_url.rstrip('/')

required_uris    = [base_url, base_url + '/', base_url + '/*']
required_origins = [base_url]
actual_uris      = client.get('redirectUris', [])
actual_origins   = client.get('webOrigins', [])

missing_uris    = [u for u in required_uris    if u not in actual_uris]
missing_origins = [o for o in required_origins if o not in actual_origins]

if missing_uris or missing_origins:
    if missing_uris:
        print(f'ERROR: redirectUris missing after PUT: {missing_uris}', file=sys.stderr)
    if missing_origins:
        print(f'ERROR: webOrigins missing after PUT: {missing_origins}', file=sys.stderr)
    sys.exit(1)

# Print final verified state so it appears in the terminal log
print('    redirectUris:')
for u in sorted(actual_uris):
    print(f'      {u}')
print('    webOrigins:')
for o in sorted(actual_origins):
    print(f'      {o}')
PYEOF

  local verify_output
  verify_output=$(TMP_IN="$tmp_client" BASIS_FE_URL="$fe_url" python3 "$tmp_script") \
    || {
      log "✗ Verification FAILED — Codespaces URIs not found in Keycloak after PUT."
      log "  OIDC login redirects will fail until this is resolved."
      log "  Check: docker compose logs keycloak"
      return 1
    }

  log "Verification passed. basis-frontend final configuration:"
  echo "$verify_output"
  log "Redirect URI patching complete."
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
