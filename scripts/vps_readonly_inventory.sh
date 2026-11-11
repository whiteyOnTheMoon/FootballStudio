#!/usr/bin/env bash
# Read-only and deliberately low-detail inventory; no credentials or config.
set -uo pipefail
printf '%s\n' 'FootballStudio: read-only VPS preflight'
printf '\nOS: '
if [[ -f /etc/os-release ]]; then
  ( . /etc/os-release; printf '%s\n' "${PRETTY_NAME:-unknown}" )
else
  uname -s
fi
printf 'CPUs: '
getconf _NPROCESSORS_ONLN 2>/dev/null || echo unavailable
printf '\nMemory summary (MiB):\n'
free -m 2>/dev/null | awk 'NR==1 || $1=="Mem:" { print }' || true
printf '\nFree space for /home/ap:\n'
df -h /home/ap 2>/dev/null || true
printf '\nDocker/Compose versions:\n'
docker --version 2>/dev/null || true
docker compose version 2>/dev/null || true
printf '\nHost cloudflared systemd status (no service configuration):\n'
systemctl is-active cloudflared.service 2>/dev/null || true
printf '\nRunning cloudflared Docker containers (name/image/networks only):\n'
docker ps --format '{{.Names}} | {{.Image}} | {{.Networks}}' 2>/dev/null |
  grep -Ei 'cloudflared|cloudflare' || true
printf '\nDocker network names (no inspect/env values):\n'
docker network ls --format '{{.Name}}' 2>/dev/null || true
printf '\nOrigin port 18080 listeners (empty means none detected):\n'
ss -ltn 2>/dev/null | grep -E '[:.]18080[[:space:]]' || true
printf '\nFootballStudio target directory:\n'
if [[ -e /home/ap/footballstudio ]]; then
  echo 'EXISTS: inspect manually, do not overwrite'
else
  echo 'NOT PRESENT: /home/ap/footballstudio'
fi
printf '\nDo not paste credentials, .env, tokens, Docker inspect Env, or service units.\n'
