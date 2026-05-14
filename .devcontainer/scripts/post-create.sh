#!/usr/bin/env bash
# BASIS — First-time Codespace setup
# Runs once when the Codespace is created (postCreateCommand).
#
# What this script does:
#   1. Copies .env.example → .env
#   2. In Codespaces: rewrites localhost URLs to forwarded-port URLs
#   3. Builds and starts all Docker Compose services
#   4. Waits for Keycloak HTTP server (master realm ready)
#   5. Waits for basis realm import to complete
#   6. In Codespaces: waits for basis-frontend client, then patches redirect URIs
#   7. Prints a welcome message with service URLs and demo credentials
#
# Architecture note: this script is a thin convenience layer. It does not
# change any BASIS services, compose configuration, or architecture decisions.
# It only configures the environment and starts the existing stack.

set -euo pipefail

# ── Helpers ────────────────────────────────────────────────────────────────────

print_banner() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  BASIS — OT Identity Control Plane                              ║"
  echo "║  Architecture demonstration environment                         ║"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  echo ""
}

# Stage 1: Wait for Keycloak's HTTP server to accept requests.
# Checks the master realm — always the first realm available, does not
# indicate that the basis realm import has completed.
wait_for_keycloak_http() {
  local max_attempts=40  # 40 × 10s = ~6 min
  local attempt=1

  echo "→ Waiting for Keycloak readiness..."
  echo "  (First startup: 60–90 seconds)"

  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:18080/realms/master" > /dev/null 2>&1; then
      echo "→ Keycloak HTTP server is up."
      return 0
    fi
    printf "  [%d/%d] Keycloak starting" "$attempt" "$max_attempts"
    local kc_status
    kc_status=$(docker compose ps keycloak --format '{{.Status}}' 2>/dev/null || echo "unknown")
    echo " ($kc_status)"
    sleep 10
    attempt=$((attempt + 1))
  done

  echo "✗ Keycloak did not respond within the timeout."
  echo "  Run: docker compose logs keycloak"
  return 1
}

# Stage 2: Wait for the basis realm import to complete.
# Keycloak imports custom realms after the master realm is ready.
# The basis realm endpoint returns 200 only after import finishes.
wait_for_basis_realm() {
  local max_attempts=24  # 24 × 5s = 2 min
  local attempt=1

  echo "→ Waiting for basis realm import..."

  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:18080/realms/basis" > /dev/null 2>&1; then
      echo "→ basis realm is ready."
      return 0
    fi
    echo "  [${attempt}/${max_attempts}] Waiting for basis realm..."
    sleep 5
    attempt=$((attempt + 1))
  done

  echo "✗ basis realm was not available after ${max_attempts} attempts."
  echo "  This usually means realm import failed. Run: docker compose logs keycloak"
  return 1
}

# Obtains a Keycloak admin token from the master realm.
# Retries on failure — the admin endpoint may not be immediately usable
# even after the master realm is reachable via HTTP.
get_admin_token() {
  local max_attempts=12  # 12 × 5s = 1 min
  local attempt=1
  local token

  echo "→ Obtaining Keycloak admin token..."

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
      echo "  Admin token obtained."
      # Print to stdout so the caller can capture it
      echo "$token"
      return 0
    fi

    echo "  [${attempt}/${max_attempts}] Waiting for admin API..."
    sleep 5
    attempt=$((attempt + 1))
  done

  echo "✗ Could not obtain Keycloak admin token after ${max_attempts} attempts."
  return 1
}

# Stage 3: Fetch and validate the basis-frontend client, then patch redirect URIs.
# The client may not be queryable immediately after the realm is ready —
# this function retries until it finds a valid (non-empty) client response.
patch_keycloak_for_codespaces() {
  local fe_url="$1"
  local max_attempts=12  # 12 × 5s = 1 min
  local attempt=1
  local admin_token client_json client_count client_uuid http_status

  # Get admin token (with retry)
  admin_token=$(get_admin_token) || return 1

  # Wait for the basis-frontend client to be queryable
  echo "→ Waiting for basis-frontend client..."

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
      echo "  basis-frontend client found."
      break
    fi

    echo "  [${attempt}/${max_attempts}] Waiting for basis-frontend client..."
    sleep 5
    attempt=$((attempt + 1))
  done

  if [ "${client_count:-0}" -lt 1 ]; then
    echo "✗ basis-frontend client not found after ${max_attempts} attempts."
    echo "  Run: docker compose logs keycloak"
    return 1
  fi

  # Extract and validate the client UUID before touching anything
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
    echo "✗ Could not extract a valid UUID from basis-frontend client response."
    return 1
  fi

  echo "→ Patching basis-frontend (id: ${client_uuid})"
  echo "  Adding redirect URI: ${fe_url}"

  # Build the updated client JSON — append URIs only if not already present.
  # The fe_url is passed via environment variable to avoid shell-interpolation
  # issues inside the Python string literal.
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
" <<< "$client_json") || { echo "✗ Failed to build updated client JSON."; return 1; }

  if [ -z "${updated_json:-}" ]; then
    echo "✗ Updated client JSON is empty — aborting PUT."
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
    echo "→ Redirect URI patched successfully (HTTP 204)."
  else
    echo "✗ Keycloak client update returned HTTP ${http_status:-unknown} (expected 204)."
    echo "  Run: docker compose logs keycloak"
    return 1
  fi
}

print_welcome() {
  local is_codespaces="${1:-false}"
  local domain="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  local name="${CODESPACE_NAME:-}"

  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  BASIS Codespaces environment ready                             ║"
  echo "╠══════════════════════════════════════════════════════════════════╣"

  if [ "$is_codespaces" = "true" ] && [ -n "$name" ]; then
    printf "║  %-64s║\n" "  Operator Console → https://${name}-5173.${domain}"
    printf "║  %-64s║\n" "  API (Swagger)    → https://${name}-8000.${domain}/docs"
    printf "║  %-64s║\n" "  Keycloak Admin   → https://${name}-18080.${domain}/admin"
  else
    echo "║  Operator Console → http://localhost:5173                       ║"
    echo "║  API (Swagger)    → http://localhost:8000/docs                  ║"
    echo "║  Keycloak Admin   → http://localhost:18080/admin                ║"
  fi

  echo "║                                                                  ║"
  echo "║  Demo credentials (all share password: demo123)                 ║"
  echo "║    alice  → viewer   (telemetry only, commands blocked)         ║"
  echo "║    bob    → operator (telemetry + HVAC + Modbus commands)       ║"
  echo "║    carol  → admin    (full access + audit log)                  ║"
  echo "║                                                                  ║"
  echo "║  Keycloak admin: admin / admin                                  ║"
  echo "║                                                                  ║"
  echo "║  Read README.md for the full architecture walkthrough.          ║"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  echo ""
}

# ── Main ──────────────────────────────────────────────────────────────────────

print_banner

# Move to repo root regardless of where the devcontainer mounts us
cd "$(dirname "$0")/../.."

echo "→ Checking environment..."

IS_CODESPACES=false
if [ -n "${CODESPACE_NAME:-}" ]; then
  IS_CODESPACES=true
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  KC_URL="https://${CODESPACE_NAME}-18080.${DOMAIN}"
  API_URL="https://${CODESPACE_NAME}-8000.${DOMAIN}"
  FE_URL="https://${CODESPACE_NAME}-5173.${DOMAIN}"
  echo "  Environment: GitHub Codespaces"
  echo "  Codespace:   ${CODESPACE_NAME}"
  echo "  Keycloak:    ${KC_URL}"
  echo "  API:         ${API_URL}"
  echo "  Frontend:    ${FE_URL}"
else
  echo "  Environment: Local Dev Container (VS Code)"
fi
echo ""

# ── Step 1: Prepare .env ──────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
  echo "→ Creating .env from .env.example..."
  cp .env.example .env
else
  echo "→ .env already exists — skipping copy."
fi

if [ "$IS_CODESPACES" = "true" ]; then
  echo "→ Rewriting .env for Codespaces forwarded-port URLs..."

  # Replace the four browser-facing URLs. Internal Docker hostnames
  # (keycloak:8080, mosquitto) are deliberately left unchanged.
  sed -i "s|KEYCLOAK_EXTERNAL_URL=.*|KEYCLOAK_EXTERNAL_URL=${KC_URL}|" .env
  sed -i "s|VITE_KEYCLOAK_URL=.*|VITE_KEYCLOAK_URL=${KC_URL}|" .env
  sed -i "s|VITE_API_URL=.*|VITE_API_URL=${API_URL}|" .env
  sed -i "s|FRONTEND_URL=.*|FRONTEND_URL=${FE_URL}|" .env

  # KC_PROXY=edge tells Keycloak to trust X-Forwarded-Proto/Host headers
  # from the Codespaces HTTPS proxy. Without this, Keycloak constructs
  # issuer URLs using http:// and JWT iss validation fails.
  if ! grep -q "^KC_PROXY=" .env; then
    echo "KC_PROXY=edge" >> .env
  else
    sed -i "s|^KC_PROXY=.*|KC_PROXY=edge|" .env
  fi

  echo "→ .env updated for Codespaces."
fi

# ── Step 2: Start all services ────────────────────────────────────────────────

echo ""
echo "→ Building and starting BASIS services..."
echo "  First build: 3–5 minutes (image pulls + npm install + pip install)"
echo "  Subsequent starts: ~60–90s (dominated by Keycloak realm import)"
echo ""

docker compose up --build -d

echo ""
echo "→ Services launched:"
docker compose ps

# ── Step 3: Wait for Keycloak in two stages ───────────────────────────────────

echo ""
wait_for_keycloak_http
echo ""
wait_for_basis_realm

# ── Step 4: Patch Keycloak redirect URIs for Codespaces ──────────────────────

if [ "$IS_CODESPACES" = "true" ]; then
  echo ""
  patch_keycloak_for_codespaces "$FE_URL"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

print_welcome "$IS_CODESPACES"
