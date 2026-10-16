#!/bin/bash
# manifestme.sh
# Write manifest.json for Posit Connect. Run this on YOUR machine (never in CI)
# after any change to the code, requirements.txt or data, then commit manifest.json.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

./sync_data.sh
# Record a normal desktop locale, not C.UTF-8 (the deploy workflow warns on a CI-runner locale).
export LC_ALL="${LC_ALL:-en_US.UTF-8}" LANG="${LANG:-en_US.UTF-8}"
python3 -m pip install --quiet rsconnect-python
rsconnect write-manifest shiny . --entrypoint app:app --overwrite \
  --exclude '*.sh' --exclude '__pycache__' --exclude '.env'
echo "Done. Commit app/manifest.json."
