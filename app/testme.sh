#!/bin/bash
# testme.sh
# Run the dashboard locally, one command, no arguments. Then open http://127.0.0.1:8000

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./sync_data.sh
if python3 -c "import shiny, lifelines" >/dev/null 2>&1; then
    python3 -m shiny run app.py --host 127.0.0.1 --port 8000
else
    uv run --with numpy --with pandas --with scipy --with lifelines --with matplotlib --with shiny shiny run app.py --host 127.0.0.1 --port 8000
fi
