#!/usr/bin/env bash
# Richtet die App für den Betrieb zuhause ein: Datenbank, Modell, Autostart.
# Gefahrlos mehrfach ausführbar - bestehende Daten bleiben unangetastet.
set -euo pipefail
cd "$(dirname "$0")"

B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
schritt() { printf "\n%s▸ %s%s\n" "$B" "$1" "$N"; }
ok()      { printf "  %s✓%s %s\n" "$G" "$N" "$1"; }
warn()    { printf "  %s!%s %s\n" "$Y" "$N" "$1"; }
fehler()  { printf "  %s✗%s %s\n" "$R" "$N" "$1"; }
frage()   { printf "  %s [j/n] " "$1"; read -r a; [[ "$a" =~ ^[jJyY] ]]; }

printf "\n%sFamilie ToDos - Einrichtung zuhause%s\n" "$B" "$N"

# --- 1. Python ---------------------------------------------------------
schritt "Python prüfen"
if ! command -v python3 >/dev/null; then
  fehler "python3 nicht gefunden. Auf macOS: Xcode-Befehlszeilenwerkzeuge installieren"
  echo "     mit: xcode-select --install"
  exit 1
fi
VERSION=$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
  ok "Python $VERSION"
else
  fehler "Python $VERSION ist zu alt, nötig ist mindestens 3.10"
  exit 1
fi

# --- 2. Datenbank ------------------------------------------------------
schritt "Datenbank anlegen"
if [ -f data/todos.db ]; then
  ok "data/todos.db besteht bereits - bleibt unverändert"
else
  ok "wird neu angelegt"
fi
mkdir -p data

# --- 3. Modell ---------------------------------------------------------
schritt "Modell für die Einordnung wählen"
OLLAMA_MODELLE=""
if curl -fsS -m 3 http://localhost:11434/api/tags >/dev/null 2>&1; then
  OLLAMA_MODELLE=$(curl -fsS -m 3 http://localhost:11434/api/tags \
    | python3 -c 'import json,sys; print("\n".join(m["name"] for m in json.load(sys.stdin).get("models", [])))')
  if [ -n "$OLLAMA_MODELLE" ]; then
    ok "Ollama läuft. Vorhandene Modelle:"
    echo "$OLLAMA_MODELLE" | sed 's/^/       /'
    ERSTES=$(echo "$OLLAMA_MODELLE" | head -1)
    python3 - "$ERSTES" <<'PY'
import sys
sys.path.insert(0, ".")
from app import db
db.init()
db.set_settings({"ollama_model": sys.argv[1], "provider": "auto"})
PY
    ok "eingetragen: $ERSTES (läuft offline, kostet nichts)"
  else
    warn "Ollama läuft, hat aber kein Modell geladen."
    echo "       Eines holen mit:  ollama pull gemma4:12b-mlx"
  fi
else
  warn "Ollama ist nicht erreichbar (offline-Einordnung nicht verfügbar)."
  echo "       Ollama von ollama.com laden, dann: ollama pull gemma4:12b-mlx"
fi

echo
if frage "Zusätzlich einen Cloud-Anbieter hinterlegen (bessere Einordnung)?"; then
  echo "       1) Claude (Anthropic)   2) Mistral   3) ChatGPT (OpenAI)   0) keinen"
  printf "       Auswahl: "; read -r wahl
  case "$wahl" in
    1) FELD="anthropic_api_key"; NAME="Claude" ;;
    2) FELD="mistral_api_key";   NAME="Mistral" ;;
    3) FELD="openai_api_key";    NAME="OpenAI" ;;
    *) FELD=""; NAME="" ;;
  esac
  if [ -n "$FELD" ]; then
    printf "       Schlüssel für %s (Eingabe bleibt unsichtbar): " "$NAME"
    read -rs SCHLUESSEL; echo
    if [ -n "$SCHLUESSEL" ]; then
      python3 - "$FELD" "$SCHLUESSEL" <<'PY'
import sys
sys.path.insert(0, ".")
from app import config, db
db.init()
config.write_secrets({sys.argv[1]: sys.argv[2]})
PY
      ok "in data/secrets.json gespeichert (nur für dich lesbar)"
    fi
  fi
fi

# --- 4. Selbsttest -----------------------------------------------------
schritt "Selbsttest"
python3 -m app.check

# --- 5. Autostart ------------------------------------------------------
schritt "Automatisch starten?"
PLIST="$HOME/Library/LaunchAgents/de.familie.todos.plist"
if [ -f "$PLIST" ]; then
  ok "Autostart ist bereits eingerichtet"
elif [ "$(uname)" = "Darwin" ] && frage "Server nach jedem Neustart automatisch starten?"; then
  mkdir -p "$HOME/Library/LaunchAgents"
  cat > "$PLIST" <<PLISTENDE
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>de.familie.todos</string>
  <key>ProgramArguments</key><array><string>$(pwd)/start.sh</string></array>
  <key>WorkingDirectory</key><string>$(pwd)</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$(pwd)/data/server.log</string>
  <key>StandardErrorPath</key><string>$(pwd)/data/server.log</string>
</dict></plist>
PLISTENDE
  launchctl unload "$PLIST" 2>/dev/null || true
  launchctl load "$PLIST"
  ok "eingerichtet. Protokoll landet in data/server.log"
  echo "       Abschalten mit: launchctl unload $PLIST"
fi

# --- fertig ------------------------------------------------------------
IP=$(python3 -c 'import sys; sys.path.insert(0,"."); from app.server import local_ip; print(local_ip())')
printf "\n%sFertig.%s\n\n" "$B" "$N"
echo "  Starten:      ./start.sh"
echo "  Im Browser:   http://localhost:8765"
echo "  Auf dem Handy: http://$IP:8765   (gleiches WLAN)"
echo
echo "  Erster Schritt in der App: unter Einstellungen die Familienmitglieder"
echo "  anlegen und ihnen Kompetenzen geben - daran hängt die Zuweisung."
echo
if frage "Jetzt starten?"; then
  exec ./start.sh
fi
