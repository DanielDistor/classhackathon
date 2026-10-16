#!/bin/bash
# deployme.sh
# Deploy the dashboard to the course Posit Connect server from your machine.
# Needs CONNECT_SERVER and CONNECT_API_KEY (handed out at the event) in a
# gitignored app/.env file, or an rsconnect account you already added.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

python3 -m pip install --quiet rsconnect-python
if [ -f ".env" ]; then
  # shellcheck disable=SC1091
  source .env
fi

rsconnect deploy shiny \
  ${CONNECT_SERVER:+--server "$CONNECT_SERVER"} \
  ${CONNECT_API_KEY:+--api-key "$CONNECT_API_KEY"} \
  --entrypoint app:app \
  --title "Drone Fleet Reliability Monitor" \
  --exclude '*.sh' --exclude '__pycache__' --exclude '.env' \
  .
