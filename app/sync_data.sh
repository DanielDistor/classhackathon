#!/bin/bash
# sync_data.sh
# Copy the test datasets (the CSVs in ../data/) into app/data/, because Posit
# Connect only receives what is inside this folder. tests/test_app.py fails if
# the copy ever differs from ../data/, so re-run this after data/simulate.py.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

for d in ../data/*/; do
  [ -f "${d}flights.csv" ] || continue   # only dataset folders
  name="$(basename "$d")"
  mkdir -p "data/$name"
  cp "$d"*.csv "data/$name/"
done
echo "Copied test datasets into app/data/: $(ls data | tr '\n' ' ')"
