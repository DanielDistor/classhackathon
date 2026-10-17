#!/bin/bash
# testme.sh
# Run the dashboard locally, one command, no arguments. Then open http://127.0.0.1:8000
# (From the repo folder, ./run.sh does the same thing.)
#
# It installs anything missing, rebuilds the React app (../web) if its code changed,
# and serves the FastAPI app (api.py): the dashboard at /, the API under /api/, docs at /docs.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./sync_data.sh

# 1. Python packages
if ! python3 -c "import fastapi, uvicorn, lifelines, pandas" >/dev/null 2>&1; then
    echo "Installing the Python packages (first run only)..."
    python3 -m pip install --quiet -r requirements.txt
fi

# 2. The React app: rebuild static/ when anything in ../web is newer than the last build.
#    Without Node.js the committed build in static/ is used as is.
WEB=../web
if command -v npm >/dev/null 2>&1; then
    if [ ! -d "$WEB/node_modules" ]; then
        echo "Installing the React packages (first run only)..."
        (cd "$WEB" && npm ci --silent)
    fi
    if [ ! -f static/index.html ] || [ -n "$(find "$WEB/src" "$WEB/index.html" "$WEB/package.json" "$WEB/vite.config.js" -newer static/index.html 2>/dev/null | head -1)" ]; then
        echo "React code changed: rebuilding the dashboard..."
        (cd "$WEB" && npm run build --silent)
    fi
elif [ ! -f static/index.html ]; then
    echo "No dashboard build found and Node.js is not installed: install Node.js 20+ from nodejs.org" >&2
    exit 1
fi

echo "Dashboard: http://127.0.0.1:8000   (Ctrl+C to stop)"
python3 -m uvicorn api:app --host 127.0.0.1 --port 8000
