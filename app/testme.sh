#!/bin/bash
# testme.sh
# Run the dashboard locally, one command, no arguments. Then open http://127.0.0.1:8000
# It serves the FastAPI app (api.py): the JSON API under /api/, its docs at /docs,
# and the React dashboard (built from ../web into static/) at /.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./sync_data.sh
# Build the React app if it has never been built (needs Node.js 20+). After editing
# ../web/src, rebuild with: cd ../web && npm run build   (or use npm run dev there)
if [ ! -f static/index.html ] && command -v npm >/dev/null 2>&1; then
    (cd ../web && npm ci && npm run build)
fi
if python3 -c "import fastapi, uvicorn, lifelines" >/dev/null 2>&1; then
    python3 -m uvicorn api:app --host 127.0.0.1 --port 8000
else
    uv run --with-requirements requirements.txt uvicorn api:app --host 127.0.0.1 --port 8000
fi
