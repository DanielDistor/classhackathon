#!/bin/bash
# manifestme.sh
# Write manifest.json for Posit Connect. Run this on YOUR machine (never in CI)
# after any change to the code, requirements.txt, data or the React build, then
# commit manifest.json. Connect runs api.py (FastAPI), which also serves the
# React dashboard from static/.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./sync_data.sh
[ -f static/index.html ] || { echo "No React build in static/: run  cd ../web && npm run build  first." >&2; exit 1; }
# Record a normal desktop locale, not C.UTF-8 (the deploy workflow warns on a CI-runner locale).
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
python3 -m pip install --quiet rsconnect-python
rsconnect write-manifest fastapi . --entrypoint api:app --overwrite \
  --exclude '*.sh' --exclude '__pycache__' --exclude '.env'
echo "Done. Commit app/manifest.json."
