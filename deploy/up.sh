#!/usr/bin/env bash
# City Agent RISE — one-command production start (Nginx front).
#
#   bash deploy/up.sh            # start / update the stack
#   bash deploy/up.sh caddy      # use Caddy (auto-TLS) instead of Nginx
#
# Do NOT hand-edit the compose files. This script always runs the correct full stack
# (front proxy + api + web) so you never end up hitting the raw api port.
set -euo pipefail
cd "$(dirname "$0")/.."

FRONT="${1:-nginx}"
if [ "$FRONT" = "caddy" ]; then
  COMPOSE="docker-compose.prod.yml"
else
  COMPOSE="docker-compose.nginx.yml"
fi

if [ ! -f .env.prod ]; then
  echo "ERROR: .env.prod not found."
  echo "  cp .env.example .env.prod   then fill SECRET_KEY, SUPERADMIN_*, HTTP_PORT, ORIGIN, FABRIC_*"
  exit 1
fi

# stop any previously-running variant so ports don't clash
for f in docker-compose.yml docker-compose.prod.yml docker-compose.nginx.yml; do
  [ -f "$f" ] && docker compose -f "$f" --env-file .env.prod down 2>/dev/null || true
done

echo ">> building + starting stack via $COMPOSE ..."
docker compose -f "$COMPOSE" --env-file .env.prod up -d --build

echo
docker compose -f "$COMPOSE" --env-file .env.prod ps

PORT="$(grep -E '^HTTP_PORT=' .env.prod | cut -d= -f2 || true)"; PORT="${PORT:-80}"
echo
echo ">> Stack up (front=$FRONT). Open:"
echo "     http://<server-ip>:${PORT}            <- login UI (go here, NOT the api port)"
echo "     http://<server-ip>:${PORT}/api/health <- {\"ok\":true,...}"
echo ">> Open port ${PORT} in the EC2 security group."
