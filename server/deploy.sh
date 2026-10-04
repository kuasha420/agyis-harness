#!/usr/bin/env bash
# ==============================================================================
# PSL Telemetry Hub Staging & Deployment Script (ADR-030)
# Target Host: bd.purrfectsoft.co.uk (CloudPanel Managed VPS)
# ==============================================================================
set -euo pipefail

TARGET_HOST="${1:-bd.purrfectsoft.co.uk}"
REMOTE_USER="${REMOTE_USER:-ops_runner}"
DEPLOY_DIR="${DEPLOY_DIR:-/opt/psl/telemetry-hub}"
COMPOSE_FILE="server/docker-compose.yml"
HUB_PORT="8000"

echo "======================================================================"
echo " 🛰️ Deploying PSL Telemetry Hub to ${TARGET_HOST}"
echo "======================================================================"

# 1. Pre-flight verification of required binaries locally
for bin in ssh rsync curl; do
  if ! command -v "${bin}" >/dev/null 2>&1; then
    echo "✘ Error: Required tool '${bin}' is missing from local host." >&2
    exit 1
  fi
done

echo "✔ Local deployment dependencies verified."

# 2. Synchronize server codebase to remote VPS staging directory
echo "▶ Synchronizing server codebase to ${REMOTE_USER}@${TARGET_HOST}:${DEPLOY_DIR}..."
ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new "${REMOTE_USER}@${TARGET_HOST}" \
  "mkdir -p '${DEPLOY_DIR}/server'"

rsync -avz --delete \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude '.git' \
  --exclude 'data/*.db' \
  "server/" "${REMOTE_USER}@${TARGET_HOST}:${DEPLOY_DIR}/server/"

# 3. Remote configuration & container spin-up
echo "▶ Configuring environment and launching containers on ${TARGET_HOST}..."
ssh -o BatchMode=yes "${REMOTE_USER}@${TARGET_HOST}" bash -s <<REMOTE_SCRIPT
set -euo pipefail

cd "${DEPLOY_DIR}/server"

# Generate or preserve .env file
if [ ! -f .env ]; then
  echo "Generating fresh production .env configuration..."
  PG_PASSWORD=\$(openssl rand -hex 24)
  cat <<ENV_EOF > .env
POSTGRES_DB=psl_telemetry
POSTGRES_USER=psl_admin
POSTGRES_PASSWORD=\${PG_PASSWORD}
PSL_GITHUB_ORG=\${PSL_GITHUB_ORG:-purrfectsoft}
PORT=${HUB_PORT}
ENV_EOF
  chmod 600 .env
fi

# Build and start services using Docker Compose
docker compose up -d --build --remove-orphans

# Health probe check on localhost:8000 (CloudPanel reverse-proxy target)
echo "▶ Waiting for PSL Hub health probe..."
MAX_ATTEMPTS=20
COUNT=0
HEALTHY=0

while [ \$COUNT -lt \$MAX_ATTEMPTS ]; do
  if curl -fsS "http://127.0.0.1:${HUB_PORT}/api/v1/health" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  COUNT=\$((COUNT + 1))
  sleep 2
done

if [ \$HEALTHY -eq 1 ]; then
  echo "✔ PSL Telemetry Hub container is running and healthy on 127.0.0.1:${HUB_PORT}!"
  curl -s "http://127.0.0.1:${HUB_PORT}/api/v1/health" | head -n 1
else
  echo "✘ Container healthcheck failed after \$MAX_ATTEMPTS attempts." >&2
  docker compose logs --tail 50
  exit 1
fi
REMOTE_SCRIPT

echo ""
echo "======================================================================"
echo " ✔ PSL Telemetry Hub deployed successfully to ${TARGET_HOST}"
echo "======================================================================"
echo " CloudPanel NGINX Configuration Checklist:"
echo " 1. Site: bd.purrfectsoft.co.uk (Type: Reverse Proxy)"
echo " 2. Reverse Proxy Target: http://127.0.0.1:${HUB_PORT}"
echo " 3. SSL: Let's Encrypt enabled via CloudPanel UI"
echo " 4. Test Public Health: curl -fsS https://${TARGET_HOST}/api/v1/health"
echo "======================================================================"
