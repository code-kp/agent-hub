#!/bin/zsh

set -u

collect_pids() {
  {
    lsof -nP -iTCP:3000 -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2}'
    lsof -nP -iTCP:8000 -sTCP:LISTEN 2>/dev/null | awk 'NR>1 {print $2}'
  } | sort -u
}

for _ in {1..5}; do
  PIDS=$(collect_pids)
  if [[ -z "${PIDS}" ]]; then
    exit 0
  fi
  kill ${=PIDS} 2>/dev/null || true
  sleep 1
done

for _ in {1..5}; do
  PIDS=$(collect_pids)
  if [[ -z "${PIDS}" ]]; then
    exit 0
  fi
  kill -9 ${=PIDS} 2>/dev/null || true
  sleep 1
done

PIDS=$(collect_pids)
if [[ -n "${PIDS}" ]]; then
  echo "Ports 3000 or 8000 are still occupied: ${PIDS}" >&2
  exit 1
fi
