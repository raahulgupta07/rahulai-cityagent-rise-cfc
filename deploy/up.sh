#!/usr/bin/env bash
# City Agent RISE — one-command production start.
#
#   bash deploy/up.sh            # SINGLE container (recommended: UI + API on one port)
#   bash deploy/up.sh nginx      # multi-container, Nginx front
#   bash deploy/up.sh caddy      # multi-container, Caddy front (auto-TLS)
#
# Do NOT hand-edit the compose files. This script always runs a correct, complete stack.
set -euo pipefail
cd "$(dirname "$0")/.."

MODE="${1:-single}"
case "$MODE" in
  single) COMPOSE="docker-compose.single.yml" ;;
  nginx)  COMPOSE="docker-compose.nginx.yml" ;;
  caddy)  COMPOSE="docker-compose.prod.yml" ;;
  *) echo "unknown mode '$MODE' (use: single | nginx | caddy)"; exit 1 ;;
esac

if [ ! -f .env.prod ]; then
  echo "ERROR: .env.prod not found."
  echo "  cp .env.example .env.prod   then fill SECRET_KEY, SUPERADMIN_*, HTTP_PORT, ORIGIN, FABRIC_*"
  exit 1
fi

# stop any previously-running variant so ports don't clash
for f in docker-compose.yml docker-compose.prod.yml docker-compose.nginx.yml docker-compose.single.yml; do
  [ -f "$f" ] && docker compose -f "$f" --env-file .env.prod down 2>/dev/null || true
done

echo ">> building + starting stack via $COMPOSE (mode=$MODE) ..."
docker compose -f "$COMPOSE" --env-file .env.prod up -d --build

echo
docker compose -f "$COMPOSE" --env-file .env.prod ps

PORT="$(grep -E '^HTTP_PORT=' .env.prod | cut -d= -f2 || true)"; PORT="${PORT:-80}"
echo
echo ">> Stack up (mode=$MODE). Open:"
echo "     http://<server-ip>:${PORT}             <- the app (UI + API on one port)"
echo "     http://<server-ip>:${PORT}/api/health  <- {\"ok\":true,...}"
echo ">> Open port ${PORT} in the security group."
