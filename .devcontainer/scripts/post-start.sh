#!/usr/bin/env bash
# BASIS — Codespace restart handler
# Runs on every Codespace resume/restart (postStartCommand).
#
# Docker-in-Docker state (images, containers, volumes) does not persist
# across Codespace restarts. This script brings the stack back up using
# already-built images (fast — no rebuild needed) and re-patches Keycloak,
# which re-imports the realm from realm-export.json on each fresh start.
#
# Keycloak still takes 60–90 seconds to complete realm import on restart.
# This script runs in the background so the user can use VS Code immediately.

set -euo pipefail

# ── Shared helpers ─────────────────────────────────────────────────────────────

wait_for_keycloak() {
  local max_attempts=40  # 40 × 10s = ~6 minutes maximum
  local attempt=1

  echo "[restart] Waiting for Keycloak to complete realm import..."
  while [ $attempt -le $max_attempts ]; do
    if curl -sf "http://localhost:18080/realms/master" > /dev/null 2>&1; then
      echo "[restart] Keycloak is ready."
      return 0
    fi
    sleep 10
    attempt=$((attempt + 1))
  done

  echo "[restart] Keycloak did not become ready within the timeout."
  echo "[restart] Run: docker compose logs keycloak"
  return 1
}

patch_keycloak_for_codespaces() {
  local fe_url="$1"

  echo "[restart] Patching Keycloak OIDC client for Codespaces redirect URIs..."

  local admin_token
  admin_token=$(curl -sf -X POST \
    "http://localhost:18080/realms/master/protocol/openid-connect/token" \
    --data-urlencode "grant_type=password" \
    --data-urlencode "client_id=admin-cli" \
    --data-urlencode "username=admin" \
    --data-urlencode "password=admin" \
    | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])") \
    || { echo "[restart] Could not obtain Keycloak admin token."; return 1; }

  local client_json
  client_json=$(curl -sf \
    -H "Authorization: Bearer $admin_token" \
    "http://localhost:18080/admin/realms/basis/clients?clientId=basis-frontend") \
    || { echo "[restart] Could not fetch Keycloak client config."; return 1; }

  local client_uuid
  client_uuid=$(echo "$client_json" | python3 -c "import json,sys; print(json.load(sys.stdin)[0]['id'])")

  echo "$client_json" | python3 - <<PYEOF | curl -sf -X PUT \
    -H "Authorization: Bearer $admin_token" \
    -H "Content-Type: application/json" \
    -d @- \
    "http://localhost:18080/admin/realms/basis/clients/$client_uuid" > /dev/null
import json, sys

clients = json.load(sys.stdin)
client = clients[0]

fe_url = "${fe_url}"
new_uris   = [fe_url + "/*", fe_url]
new_origins = [fe_url]

for u in new_uris:
    if u not in client.get("redirectUris", []):
        client.setdefault("redirectUris", []).append(u)

for o in new_origins:
    if o not in client.get("webOrigins", []):
        client.setdefault("webOrigins", []).append(o)

print(json.dumps(client))
PYEOF

  echo "[restart] Keycloak client updated."
}

# ── Main ──────────────────────────────────────────────────────────────────────

cd "$(dirname "$0")/../.."

echo ""
echo "[restart] BASIS Codespace restarting..."

# Determine if we're in Codespaces
IS_CODESPACES=false
if [ -n "${CODESPACE_NAME:-}" ]; then
  IS_CODESPACES=true
  DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
  FE_URL="https://${CODESPACE_NAME}-5173.${DOMAIN}"
  echo "[restart] Environment: GitHub Codespaces (${CODESPACE_NAME})"
else
  echo "[restart] Environment: Local Dev Container"
fi

# Ensure .env exists (it persists from postCreateCommand, but guard anyway)
if [ ! -f ".env" ]; then
  echo "[restart] .env not found — running full setup instead..."
  exec bash .devcontainer/scripts/post-create.sh
fi

# Bring services back up. Images are already built — this is fast.
# Uses --no-build to skip the build step; --wait blocks until healthy.
echo "[restart] Starting services (images already built — no rebuild)..."
docker compose up -d

echo "[restart] Services started:"
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"

# Wait for Keycloak and re-patch redirect URIs (realm is re-imported from scratch)
wait_for_keycloak

if [ "$IS_CODESPACES" = "true" ]; then
  patch_keycloak_for_codespaces "$FE_URL"
fi

DOMAIN="${GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN:-app.github.dev}"
NAME="${CODESPACE_NAME:-}"

echo ""
echo "[restart] ✓ BASIS is ready."
if [ "$IS_CODESPACES" = "true" ] && [ -n "$NAME" ]; then
  echo "[restart]   Operator Console → https://${NAME}-5173.${DOMAIN}"
  echo "[restart]   API              → https://${NAME}-8000.${DOMAIN}/docs"
  echo "[restart]   Keycloak         → https://${NAME}-18080.${DOMAIN}/admin"
fi
echo ""
