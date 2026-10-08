#!/usr/bin/env bash
# Bereitet das Deployment bei Render vor: Abhängigkeiten, Passwort,
# Datenbanktest gegen Neon, Git-Repository. Deployt nichts von selbst -
# am Ende steht, was bei Render einzutragen ist.
set -euo pipefail
cd "$(dirname "$0")"

B=$'\033[1m'; G=$'\033[32m'; Y=$'\033[33m'; R=$'\033[31m'; N=$'\033[0m'
schritt() { printf "\n%s▸ %s%s\n" "$B" "$1" "$N"; }
ok()      { printf "  %s✓%s %s\n" "$G" "$N" "$1"; }
warn()    { printf "  %s!%s %s\n" "$Y" "$N" "$1"; }
fehler()  { printf "  %s✗%s %s\n" "$R" "$N" "$1"; }
frage()   { printf "  %s [j/n] " "$1"; read -r a; [[ "$a" =~ ^[jJyY] ]]; }

ENVDATEI=".env"

printf "\n%sFamilie ToDos - Vorbereitung für den Betrieb im Internet%s\n" "$B" "$N"
echo   "Kein Docker nötig: Render baut die App als normales Python-Projekt."

# --- 1. Arbeitsumgebung ------------------------------------------------
schritt "Arbeitsumgebung anlegen (.venv)"
echo "  Ein eigener Ordner für die Zusatzpakete - so bleibt dein System sauber"
echo "  und die Version zuhause läuft weiter ganz ohne Installation."
if [ ! -d .venv ]; then
  python3 -m venv .venv
  ok ".venv angelegt"
else
  ok ".venv besteht bereits"
fi
./.venv/bin/pip install --quiet --upgrade pip
./.venv/bin/pip install --quiet -r requirements.txt
ok "gunicorn und pg8000 installiert ($(./.venv/bin/python -c 'import pg8000; print("pg8000 " + pg8000.__version__)'))"

# --- 2. Familienpasswort -----------------------------------------------
schritt "Familienpasswort festlegen"
echo "  Damit melden sich alle an. Ohne dieses Passwort startet die App"
echo "  im Internet nicht - eine offene Todo-Liste wäre schlimmer."
if frage "Ein sicheres Passwort erzeugen lassen?"; then
  APP_PASSWORD=$(python3 -c "
import secrets
woerter = ['anker','birke','dachs','esche','feder','garten','hafen','insel','kiesel',
           'lupine','moewe','nebel','otter','pappel','quelle','regen','sturm','tanne',
           'ufer','veilchen','wiese','zeder']
print('-'.join(secrets.choice(woerter) for _ in range(4)))")
  ok "erzeugt: $APP_PASSWORD"
  echo "       (vier Wörter, leicht zu diktieren, trotzdem nicht zu raten)"
else
  printf "  Passwort eingeben: "; read -rs APP_PASSWORD; echo
  if [ ${#APP_PASSWORD} -lt 8 ]; then
    fehler "Zu kurz - mindestens 8 Zeichen."
    exit 1
  fi
  ok "übernommen"
fi

# --- 3. Datenbank ------------------------------------------------------
schritt "Datenbank bei Neon"
echo "  1. Auf neon.com anmelden und ein Projekt anlegen (Region Frankfurt)"
echo "  2. Dort auf 'Connection string' klicken und die Zeile kopieren"
echo "     Sie beginnt mit  postgresql://  und endet auf  ?sslmode=require"
echo
printf "  Hier einfügen (leer lassen zum Überspringen): "
read -r DATABASE_URL

if [ -n "$DATABASE_URL" ]; then
  case "$DATABASE_URL" in
    postgres://*|postgresql://*) ;;
    *) fehler "Das sieht nicht nach einer Postgres-Adresse aus."; exit 1 ;;
  esac
  schritt "Verbindung zur Datenbank prüfen"
  if DATABASE_URL="$DATABASE_URL" ./.venv/bin/python -m app.check; then
    ok "Datenbank ist bereit"
  else
    fehler "Der Selbsttest hat etwas gefunden - siehe oben."
    frage "Trotzdem weitermachen?" || exit 1
  fi
else
  warn "übersprungen - ohne DATABASE_URL läuft online keine dauerhafte Datenbank"
fi

# --- 4. Modellzugang ---------------------------------------------------
schritt "Modell für die Einordnung im Internet"
echo "  Online gibt es kein Ollama. Ohne Schlüssel bleibt nur die Stichwortsuche."
echo "  1) Claude (Anthropic)   2) Mistral   3) ChatGPT (OpenAI)   0) später"
printf "  Auswahl: "; read -r wahl
LLM_KEY=""; LLM_VAR=""
case "$wahl" in
  1) LLM_VAR="ANTHROPIC_API_KEY" ;;
  2) LLM_VAR="MISTRAL_API_KEY" ;;
  3) LLM_VAR="OPENAI_API_KEY" ;;
esac
if [ -n "$LLM_VAR" ]; then
  printf "  Schlüssel für %s: " "$LLM_VAR"; read -rs LLM_KEY; echo
  [ -n "$LLM_KEY" ] && ok "gemerkt" || warn "leer gelassen"
fi

# --- 5. Git ------------------------------------------------------------
schritt "Git-Repository"
echo "  Render holt den Code aus einem Repository bei GitHub."
if [ -d .git ]; then
  ok "Repository besteht bereits"
else
  if frage "Jetzt ein Git-Repository anlegen und alles committen?"; then
    git init -q
    git add -A
    git -c user.email="${GIT_AUTHOR_EMAIL:-felix.brackel@posteo.de}" \
        -c user.name="${GIT_AUTHOR_NAME:-Felix}" \
        commit -q -m "Familien-ToDo-App: lokal und online betreibbar"
    ok "angelegt und committet ($(git rev-list --count HEAD) Commit)"
    echo "       Als Nächstes bei github.com ein leeres Repository anlegen, dann:"
    echo "         git remote add origin git@github.com:DEINNAME/familie-todos.git"
    echo "         git push -u origin main"
  else
    warn "übersprungen - für Render wird es aber gebraucht"
  fi
fi

# --- 6. Zusammenfassung ------------------------------------------------
# Werte in die .env schreiben - dieselbe Datei, die die App beim Start liest.
if [ -f "$ENVDATEI" ]; then
  cp "$ENVDATEI" "$ENVDATEI.backup"
  warn "Bestehende .env gesichert als .env.backup"
fi
{
  echo "# Familie ToDos - lokale Einstellungen"
  echo "# Erstellt am $(date '+%d.%m.%Y %H:%M'). Wird nicht zu GitHub hochgeladen."
  echo
  echo "APP_PASSWORD=$APP_PASSWORD"
  if [ -n "$DATABASE_URL" ]; then echo "DATABASE_URL=$DATABASE_URL"; else echo "# DATABASE_URL="; fi
  if [ -n "$LLM_KEY" ]; then echo "$LLM_VAR=$LLM_KEY"; else echo "# ANTHROPIC_API_KEY="; fi
} > "$ENVDATEI"
chmod 600 "$ENVDATEI"

printf "\n%sVorbereitet.%s\n\n" "$B" "$N"
echo "  Die Werte stehen in .env (nur für dich lesbar, nicht in Git)."
echo
echo "  Weiter bei Render:"
echo "   1. Code zu GitHub hochladen (siehe oben)"
echo "   2. render.com  ->  New  ->  Blueprint  ->  dein Repository wählen"
echo "      render.yaml liegt schon dabei, Render liest es von selbst"
echo "   3. Bei den Environment Variables die Werte aus der Datei eintragen"
echo "   4. Create  -  der erste Build dauert ein paar Minuten"
echo "   5. Danach die Adresse öffnen und mit dem Familienpasswort anmelden"
echo "   6. Daten mitnehmen: zuhause unter Einstellungen 'Alles herunterladen',"
echo "      online 'Sicherung einspielen'"
echo
echo "  Hinweis zum Tarif: der kostenlose Render-Dienst schläft nach 15 Minuten"
echo "  ein, der erste Aufruf danach dauert rund eine Minute. Starter (ca. 7 \$)"
echo "  schläft nicht. Neon bleibt in beiden Fällen kostenlos."
echo
