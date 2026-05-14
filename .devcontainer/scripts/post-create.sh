#!/usr/bin/env bash
# BASIS — First-time Codespace setup
# Runs once when the Codespace is created (postCreateCommand).
#
# What this script does:
#   1. Copies .env.example → .env
#   2. In Codespaces: rewrites localhost URLs to forwarded-port URLs
#   3. Builds and starts all Docker Compose services
#   4. Waits for Keycloak to complete realm import
#   5. In Codespaces: patches the OIDC client redirect URIs via admin API
#   6. Prints a welcome message with service URLs and demo credentials
#
# Architecture note: this script is a thin convenience layer. It does not
# change any BASIS services, compose configuration, or architecture decisions.
# It only configures the environment and starts the existing stack.

set -euo pipefail

# ── Shared helpers ─────────────────────────────────────────────────────────────

print_banner() {
  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  BASIS — OT Identity Control Plane                              ║"
  echo "║  Architecture demonstration environment                         ║"
  echo "╚══════════════════════════════════════════════════════════════════╝"
  echo ""
}

wait_for_keycloak() {
  local max_attempts=40  # 40 × 10s = ~6 minutes maximum
  local attempt=1

  echo "→ Waiting for Keycloak to complete realm import..."
  echo "  (First startup takes 60–90 seconds)"

  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:18080/realms/master" > /dev/null 2>&1; then
      echo "→ Keycloak is ready."
      return 0
    fi
    printf "  [%d/%d] Keycloak starting..." "$attempt" "$max_attempts"
    sleep 10
    attempt=$((attempt + 1))
    echo " ($(docker compose ps keycloak --format '{{.Status}}' 2>/dev/null || echo 'starting'))"
  done

  echo "✗ Keycloak did not become ready within the timeout."
  echo "  Run: docker compose logs keycloak"
  return 1
}

patch_keycloak_for_codespaces() {
  local fe_url="$1"

  echo "→ Patching Keycloak OIDC client for Codespaces redirect URIs..."

  # Obtain an admin access token from the master realm
  local admin_token
  admin_token=$(curl -sf -X POST \
    "http://localhost:18080/realms/master/protocol/openid-connect/token" \
    --data-urlencode "grant_type=password" \
    --data-urlencode "client_id=admin-cli" \
    --data-urlencode "username=admin" \
    --data-urlencode "password=admin" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])") \
    || { echo "✗ Could not obtain Keycloak admin token. Auth may not work correctly."; return 1; }

  # Fetch the basis-frontend client config
  local client_json
  client_json=$(curl -sf \
    -H "Authorization: Bearer $admin_token" \
    "http://localhost:18080/admin/realms/basis/clients?clientId=basis-frontend") \
    || { echo "✗ Could not fetch Keycloak client config."; return 1; }

  local client_uuid
  client_uuid=$(echo "$client_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")

  # Add the Codespaces frontend URL to redirectUris and webOrigins, then PUT back.
  # The python script is idempotent — it won't add duplicates on repeated runs.
  echo "$client_json" | python3 - <<PYEOF | curl -sf -X PUT \
    -H "Authorization: Bearer $admin_token" \
    -H "Content-Type: application/json" \
    -d @- \
    "http://localhost:18080/admin/realms/basis/clients/$client_uuid" > /dev/null
import json, sys

clients = json.load(sys.stdin)
client = clients[0]

fe_url = "${fe_url}"
new_uris  = [fe_url + "/*", fe_url]
new_origins = [fe_url]

for u in new_uris:
    if u not in client.get("redirectUris", []):
        client.setdefault("redirectUris", []).append(u)

for o in new_origins:
    if o not in client.get("webOrigins", []):
        client.setdefault("webOrigins", []).append(o)

print(json.dumps(client))
PYEOF

  echo "→ Keycloak client updated — redirect URIs now include Codespaces URLs."
}

print_welcome() {
  local is_codespaces="${1:-false}"
  local domain="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  local name="${CODESPACE_NAME:-}"

  echo ""
  echo "╔══════════════════════════════════════════════════════════════════╗"
  echo "║  BASIS is running!                                              ║"
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

# Move to repo root regardless of where Docker mounts us
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

# ── Step 1: Prepare .env ───────────────────────────────────────────────────────

if [ ! -f ".env" ]; then
  echo "→ Creating .env from .env.example..."
  cp .env.example .env
else
  echo "→ .env already exists — skipping copy."
fi

if [ "$IS_CODESPACES" = "true" ]; then
  echo "→ Rewriting .env for Codespaces forwarded-port URLs..."

  # Replace localhost-based URLs with Codespaces forwarded-port URLs.
  # These four values are the only ones that change — everything else
  # (MQTT credentials, internal Docker hostnames) stays the same.
  sed -i "s|KEYCLOAK_EXTERNAL_URL=.*|KEYCLOAK_EXTERNAL_URL=${KC_URL}|" .env
  sed -i "s|VITE_KEYCLOAK_URL=.*|VITE_KEYCLOAK_URL=${KC_URL}|" .env
  sed -i "s|VITE_API_URL=.*|VITE_API_URL=${API_URL}|" .env
  sed -i "s|FRONTEND_URL=.*|FRONTEND_URL=${FE_URL}|" .env

  # KC_PROXY=edge tells Keycloak to trust X-Forwarded-Proto/Host headers
  # from the Codespaces HTTPS proxy. Without this, Keycloak constructs
  # issuer URLs using http:// and the token iss claim won't match.
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
echo "  (First build: 3–5 minutes for image pulls + npm install + pip install)"
echo "  (Subsequent starts: ~60–90s, dominated by Keycloak realm import)"
echo ""

docker compose up --build -d

echo ""
echo "→ All services started. Container status:"
docker compose ps

# ── Step 3: Wait for Keycloak ─────────────────────────────────────────────────

echo ""
wait_for_keycloak

# ── Step 4: Patch Keycloak redirect URIs for Codespaces ──────────────────────

if [ "$IS_CODESPACES" = "true" ]; then
  echo ""
  patch_keycloak_for_codespaces "$FE_URL"
fi

# ── Done ──────────────────────────────────────────────────────────────────────

print_welcome "$IS_CODESPACES"
