#!/bin/bash
# run.sh: start the dashboard. One command, from the repo folder:  ./run.sh
# Then open http://127.0.0.1:8000. Installs what's missing and rebuilds the React
# app if its code changed (see app/testme.sh).
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/app/testme.sh"
