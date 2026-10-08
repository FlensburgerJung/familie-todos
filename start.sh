#!/usr/bin/env bash
# Startet den Familien-ToDo-Server.
set -euo pipefail
cd "$(dirname "$0")"
exec python3 -m app.server "$@"
