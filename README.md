# Familie ToDos

Ein Feld, in das man einen Gedanken hineinwirft, plus die Angabe, wie eilig es ist.
Den Rest — Liste, zuständige Person, Termin — macht ein Sprachmodell. Nur wenn es
sich unsicher ist, fragt es nach.

Dieselbe App läuft in zwei Betriebsarten:

| | Zuhause | Im Internet |
|---|---|---|
| Speicher | SQLite-Datei | Postgres (Neon) |
| Anmeldung | keine (Heimnetz) | Familienpasswort |
| Modell | Ollama lokal, offline | Claude, Mistral oder ChatGPT |
| Installation | keine | `pip install -r requirements.txt` |
| Start | `./start.sh` | `gunicorn app.wsgi:application` |

Welche Betriebsart gilt, entscheidet allein die Umgebung: Ist `DATABASE_URL`
gesetzt, läuft Postgres, sonst SQLite. Ist `APP_PASSWORD` gesetzt, gibt es eine
Anmeldung, sonst nicht. Am Code ändert sich nichts.

> **Erstes Mal?** → [EINRICHTUNG.md](EINRICHTUNG.md) führt Schritt für Schritt
> durch beide Wege. Kurzfassung: `./einrichten-zuhause.sh` oder
> `./einrichten-online.sh`.

---

## Zuhause starten

```bash
./einrichten-zuhause.sh   # beim ersten Mal
./start.sh                # danach
```

Dann `http://localhost:8765` öffnen. Die WLAN-Adresse für Handys schreibt der
Server beim Start in die Konsole.

Auf dem iPhone in Safari öffnen → Teilen → **Zum Home-Bildschirm**. Dann sieht es
aus wie eine App.

Anderer Port: `./start.sh --port 9000`. Nur lokal, ohne WLAN:
`./start.sh --host 127.0.0.1`.

## Der erste Schritt

Unter **Einstellungen** die Familienmitglieder anlegen und ihnen Kompetenzen geben
("Handwerk", "Behörden", "Kita", "Arzttermine"). Genau daran entscheidet die
Einordnung, wer eine Aufgabe bekommt. Ohne angelegte Personen weist sie niemandem
etwas zu.

Acht Listen sind schon da. Weitere entstehen von selbst: Passt nichts, schlägt das
Modell eine neue Liste vor, und du bestätigst sie einmal.

---

## Im Internet betreiben (Render + Neon)

Renders eigene kostenlose Datenbank läuft nach 30 Tagen ab und wird gelöscht —
deshalb Neon: dort ist der freie Tarif dauerhaft (0,5 GB, kein Ablaufdatum), was
für Familien-Todos um Größenordnungen reicht.

**1. Datenbank bei Neon anlegen**

Auf [neon.com](https://neon.com) ein Projekt erstellen (Region Frankfurt).
Unter *Connection string* die Zeichenkette kopieren — sie sieht so aus:

```
postgresql://benutzer:passwort@ep-xyz-123.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

**2. Vorher prüfen, ob die Verbindung steht**

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
DATABASE_URL='postgresql://…' .venv/bin/python -m app.check
```

Der Selbsttest legt das Schema an, schreibt und löscht testweise einen Eintrag
und sagt, was fehlt. Das dauert zehn Sekunden und erspart Rätselraten im
Deployment-Log.

**3. Code zu GitHub, dann Render**

Auf [render.com](https://render.com) *New → Blueprint* wählen und das Repository
angeben; `render.yaml` ist schon dabei. Diese Umgebungsvariablen eintragen:

| Variable | Wert |
|---|---|
| `APP_PASSWORD` | Das Familienpasswort. **Pflicht** — ohne startet die App nicht. |
| `DATABASE_URL` | Die Zeichenkette von Neon. |
| `ANTHROPIC_API_KEY` | Oder `MISTRAL_API_KEY` / `OPENAI_API_KEY`. |

Online gibt es kein Ollama. Ohne einen dieser Schlüssel bleibt nur die
Stichwortsuche — die App läuft dann, ordnet aber deutlich schlechter ein.

**4. Zum Tarif**

Der freie Render-Tarif schläft nach 15 Minuten ohne Zugriff ein; der erste
Aufruf danach dauert rund eine Minute. Zum Ausprobieren in Ordnung, im Alltag
lästig. *Starter* (ca. 7 $/Monat) schläft nicht ein. Neon bleibt in beiden
Fällen kostenlos.

**5. Daten mitnehmen**

In der lokalen App unter *Einstellungen → Sicherung und Umzug* auf
**Alles herunterladen**, in der Online-App auf **Sicherung einspielen**.
Todos, Listen, Personen und Einstellungen ziehen mit; API-Schlüssel nicht (die
stehen online in den Umgebungsvariablen).

Das funktioniert in beide Richtungen und ist zugleich das Backup.

---

## Welches Modell einordnet

| Anbieter | Wofür | Schlüssel nötig |
|---|---|---|
| **Mistral** | eingestellt; europäisch, günstig | ja |
| **Claude** (Anthropic) | etwas bessere Einordnung | ja |
| **ChatGPT** (OpenAI) | falls dort schon ein Konto | ja |
| **Ollama** | lokal, offline, kostenlos | nein |
| **Nur Regeln** | Stichwortsuche, immer verfügbar | nein |

Wählst du einen Anbieter ausdrücklich, bleibt das eine Vorliebe, kein Ausschluss:
fällt er aus, springt ein lokales Ollama-Modell ein, bevor die Stichwortsuche
greift. Die Kette steht im Einstellungen-Tab.

Auf **Automatisch** wird der Reihe nach probiert: Cloud, dann lokal, dann Regeln.
Fällt etwas aus, rutscht der Einwurf eine Stufe tiefer und landet zur Bestätigung
in der Inbox — verloren geht nichts.

**Schlüssel und Verbindungen** gehören in eine `.env` im Projektordner:

```bash
cp .env.example .env     # dann mit einem Editor ausfüllen
```

Darin stehen `ANTHROPIC_API_KEY`, `MISTRAL_API_KEY`, `OPENAI_API_KEY` sowie für
den Online-Betrieb `APP_PASSWORD` und `DATABASE_URL`. Die Datei wird beim Start
gelesen und ist von Git ausgeschlossen — sie verlässt deinen Rechner nie.

Vorrang, von oben nach unten:

1. echte Umgebungsvariablen (`export …` im Terminal, bei Render das Dashboard)
2. die `.env`
3. `data/secrets.json` — was du im Einstellungen-Tab der App einträgst

Bei Render trägst du die Werte **im Dashboard** ein, nicht in einer Datei.

**Offline mit Ollama:** `ollama pull <modell>`, dann in den Einstellungen eintragen.
Das vorhandene `gemma4:12b-mlx` braucht rund 4 Sekunden pro Einwurf. Denkende
Modelle werden automatisch auf „nicht denken" gestellt — sonst verbrauchen sie ihr
Token-Budget mit Grübeln und antworten gar nicht.

**Kosten:** Ein Einwurf sind etwa 800 Token hinein und 150 hinaus. Mit dem
eingestellten `mistral-small-latest` sind das rund **0,02 Cent** — bei 20 Todos
pro Woche unter 2 Cent im Monat. `mistral-large-latest` kostet gut das Dreifache
und bringt beim Einsortieren wenig; `claude-opus-5` läge bei etwa 0,8 Cent je
Einwurf.

## Wiederkehrende Aufgaben

Wirfst du „Staubsauger täglich leeren" ein, erkennt das Modell die Wiederholung
selbst. Nachträglich geht es auch: Todo antippen (⋯) → **Wiederholung**.

Möglich sind täglich, werktags, wöchentlich, alle zwei Wochen, monatlich,
vierteljährlich und jährlich.

Beim Abhaken entsteht **automatisch der nächste Termin** — immer nur der eine
nächste, kein Vorrat für das ganze Jahr. Gerechnet wird ab dem späteren von
altem Termin und heute: Wer den Müll drei Tage zu spät rausbringt, findet ihn
nicht sofort wieder als überfällig vor. Bei „werktags" wird das Wochenende
übersprungen.

## Aufwand und Bilanz

Jede Aufgabe kann eine geschätzte Dauer haben — das Modell schätzt sie beim
Einwerfen mit (Müll runterbringen 5 Minuten, Wohnung putzen 2 Stunden),
korrigierbar über ⋯ → **Dauer**.

Der Tab **Bilanz** 📊 zeigt daraus:

- **Kennzahlen**: erledigte Aufgaben, aufgewendete Zeit, Schnitt je Aufgabe
- **Geschafft** — wer hat im Zeitraum was erledigt
- **Noch offen** — was gerade auf wem liegt
- **Wo die Arbeit anfällt** — nach Bereich

Umschaltbar zwischen **nach Zeit** und **nach Anzahl**, und das ist der Punkt:
Drei Aufgaben à zwei Stunden sind mehr Arbeit als zehn à fünf Minuten. Beide
Maße stehen bewusst getrennt nebeneinander statt in einem Diagramm vermischt.
Aufgaben ohne Zeitangabe zählen nur bei der Anzahl mit; die App sagt, wie viele
das sind.

## Wie die Termine entstehen

| Knopf | Fällig in |
|---|---|
| Jetzt | heute |
| Bald | 3 Tagen |
| In Wochen | 2 Wochen |
| In Monaten | 2 Monaten |

Steht im Text ein Termin — „am Montag", „bis Monatsende", „vor dem Elternabend" —
gewinnt der. Wer „Montag" schreibt, meint Montag, auch wenn er vorher „Jetzt"
angetippt hat.

## Tabs

- **Start** — die Schaltzentrale, von oben nach unten:
  1. Eingabefeld zum Reinwerfen
  2. schmale Statuszeile: überfällig · heute · zu prüfen
  3. **fünf Bereiche** als Kacheln: Todos · Wunschzettel · Merken ·
     Regelmäßig · Kalender
  4. **Wer macht was** — je Person, plus „Frei zu vergeben"

  Die Bereiche sind zweistufig: Ein Tipp auf *Todos* zeigt die einzelnen
  Listen (Haushalt, Einkauf, Termine …), ein weiterer deren Einträge.
  „‹ Start" bzw. „‹ Todos" führt zurück. Einstellungen liegen bewusst
  außerhalb, im Tab „Mehr".

### Direkt in einer Liste eintragen

Steht man ohnehin schon in der richtigen Liste — etwa im Einkaufszettel oder
auf Thilos Wunschzettel — gibt es dort oben ein Feld **Direkt hinzufügen**.
Der Eintrag wird sofort angelegt, **ohne Sprachmodell**: kein Warten, keine
Kosten. Der Fokus bleibt im Feld, sodass man mehrere Zeilen hintereinander
tippen kann.

Das Modell braucht es nur für das Einwerfen auf der Startseite, wo noch
unklar ist, wohin etwas gehört.

### Von Hand zuordnen

Unter dem Eingabefeld stehen zwei Auswahlfelder: **Liste** und **Wer**. Bleiben
sie auf „automatisch", entscheidet das Modell. Wählst du etwas aus, gilt das —
praktisch bei Wunschzetteln und Einkaufslisten, wo man es ohnehin weiß. Der
Eintrag landet dann direkt in der Liste statt in der Inbox.
- **Listen** — alles Offene, nach Bereich gruppiert.
- **Woche** — sieben Tage untereinander, mit ‹ › durch die Wochen. Was vor der
  laufenden Woche liegt, steht oben unter „Liegengeblieben".
- **Bilanz** — wer hat wie viel geschafft, nach Zeit oder Anzahl.
- **Einstellungen** (am Telefon „Mehr") — Personen, Listen, Anbieter, Schlüssel,
  Kalender, Sicherung.

Am Telefon sitzt die Navigation unten, die Eingabe klappt beim Antippen auf.

**Zurück funktioniert wie gewohnt:** Der Zurück-Knopf des Browsers und die
Zurück-Geste am Telefon gehen eine Ebene in der App zurück, nicht aus ihr
heraus. Erst wenn man am Start angekommen ist, verlässt der nächste Schritt
die App.

### Frei zu vergeben

Auf dem Start steht unter den Personen eine eigene Zeile für alles, was
**niemandem zugewiesen** ist — nach dem Prinzip „macht, wer gerade Luft hat".
Die Zeile hebt sich ab, sobald dort etwas liegt.

## Bereiche und Listen

Die Startseite zeigt **Bereiche** als Kacheln; darunter liegen die einzelnen
Listen. Mitgeliefert werden:

| Bereich | Listen darin | Termine |
|---|---|---|
| **📋 Todos** | Haushalt, Kindergarten, Behörden … | ja |
| **🛒 Einkauf** | Täglicher Bedarf, Baumarkt, Elektro, je Person | nein |
| **📅 Termine** | zu vereinbaren und was feststeht | ja |
| **🎡 Unternehmungen** | Ausflüge, Essen gehen, Kultur | nein |
| **🍲 Essensideen** | Schnell & alltags, Für Gäste, Mal ausprobieren | nein |
| **📌 PostIt** | Notizen und Merkzettel | nur ein Tag |
| **🎁 Wunschzettel** | je Person | nein |
| **🎬 Merken** | Bücher, Filme, Podcasts | nein |

**Eigene Listen** legst du direkt im Bereich an: Kachel antippen, unten steht
ein Feld mit `+`. Eine Liste „🔧 Reparaturen" in den Todos ist in zehn Sekunden
gemacht. (Auch möglich unter *Mehr → Listen*, dort mit mehr Einstellungen.)

**Eigene Bereiche** legst du unter *Mehr → Bereiche* an — mit Name, Emoji und
der Angabe, ob darin Termine und Dauer geführt werden. Danach dort Listen
anlegen. Löschst du einen Bereich, wandern seine Listen zu den Todos; nichts
geht verloren.

Bereiche ohne Termine sind **Sammlungen**: Ihre Einträge haben keine Frist und
keine Dauer, erscheinen nicht unter „überfällig", nicht im Tab „Listen", nicht
bei „frei zu vergeben" und nicht im Kalender. Ein Buchtipp oder „mal an die
Ostsee fahren" soll einen schließlich nicht als überfällig anmahnen.

### Rezept zu einer Essensidee

Unter jedem Eintrag in **🍲 Essensideen** steht ein Knopf **Rezept**. Dort gibt
man die Personenzahl an und optional Wünsche („vegetarisch", „kalorienarm",
„schnell") — das Modell schlägt dann ein Rezept mit Zutaten, Schritten und
Zeitangabe vor. Es wird am Eintrag gespeichert und ist beim nächsten Öffnen
wieder da; mit *Neues Rezept* lässt es sich ersetzen.

Bewusst ein eigener Knopf und nicht automatisch: Ein Rezept will man, wenn man
kochen will — nicht zu jeder Idee, die einem einfällt. Jeder Aufruf kostet
schließlich ein paar Zehntelcent.

### Notizen an Todos

Die Einordnung schreibt häufig einen kurzen Hinweis dazu — was offen bleibt,
welche Angabe fehlt, was zu bedenken ist. Solche Notizen tragen ein kleines
**KI**-Zeichen und stehen kursiv, damit man sie von eigenen unterscheidet.

Über **⋯** lässt sich jede Notiz bearbeiten. Sobald du sie änderst,
verschwindet das Zeichen — dann ist es deine Notiz.

### Notizzettel

Der Bereich **📌 PostIt** ist für alles, was man sich kurz merken will. Eine
Notiz kann einen **Tag** bekommen — dann erscheint sie an diesem Tag ganz oben
auf der Startseite als gelber Zettel und bleibt dort, bis sie abgehakt wird.
Ohne Tag liegt sie einfach in der Kachel.

Notizen sind keine Aufgaben: keine Dauer, keine Wiederholung, nie „überfällig",
nicht im Kalender.

### Empfehlungen für jemanden

In einer Sammlung hat die Person eine andere Bedeutung als bei einer Aufgabe:
Dort steht nicht „wer macht das", sondern **„für wen ist das"** — ein Buch für
Thilo, ein Ausflug für Simone. Das Feld heißt dort entsprechend *Für wen*, und
leer bedeutet *für alle*.

Steht der Name im Text, erkennt die App ihn von selbst: „Die Känguru-Chroniken
für Thilo" landet als Empfehlung bei ihm — auch über den Knopf *Merken*, der
ohne Sprachmodell auskommt.

Wünsche und Medien tauchen nie unter „überfällig" auf, stehen nicht im Kalender
und bekommen keine Dauer — ein Buchtipp hat keine Frist. Sie haben eigene
Kacheln auf dem Start. Die Art lässt sich unter *Mehr → Listen* ändern.

Beim ersten Start nach dem Update werden vorhandene Wunschlisten automatisch
erkannt und eine Liste „Bücher, Filme & Podcasts" angelegt.

Wann etwas automatisch einsortiert wird statt in der Inbox zu landen, steuert die
Schwelle in den Einstellungen (Standard: 70 % Sicherheit).

### Was später dran ist

In jeder Liste trennt eine gestrichelte Linie, was in den nächsten sieben Tagen
ansteht, von dem, was länger hin ist. Beides bleibt sichtbar — wer gerade Luft
hat, soll sehen, was sich vorziehen lässt. Nur die Folgetermine wiederkehrender
Aufgaben stehen unterhalb der Linie, bis sie dran sind.

## Kalender

Die Adresse steht unter *Einstellungen → Kalender* und wird im Kalender als Abo
hinzugefügt (Apple Kalender: Ablage → Neues Kalenderabo). Fällige Todos erscheinen
als ganztägige Termine; pro Person geht auch.

Im Online-Betrieb hängt ein Schlüssel an der Adresse (`?token=…`), weil
Kalender-Programme keine Anmeldung mitschicken können. Wer die Adresse hat, sieht
die Termine — also nur innerhalb der Familie weitergeben.

## Wenn der Server erst aufwachen muss

Auf dem kostenlosen Tarif schläft der Dienst nach 15 Minuten ein. Die erste
Aktion danach dauert dann bis zu einer Minute. Damit niemand in der Zeit
ungeduldig weitertippt, erscheint nach gut einer Sekunde oben ein Balken:

> ⏳ Der Server war eingeschlafen und fährt hoch (12 s). Bitte nicht mehrfach
> tippen, es geht nichts verloren.

Die Sekundenzahl läuft mit, damit man sieht, dass etwas passiert. Beim Öffnen
der App erscheinen die Listen schon vorher aus dem Zwischenspeicher — dann mit
einem gelben Hinweis, dass es ein älterer Stand ist.

## Offline

Die Web-App bleibt geöffnet nutzbar, auch wenn der Server weg ist. Was du in der
Zwischenzeit einwirfst, wird lokal gemerkt und automatisch nachgereicht, sobald
der Server wieder antwortet. Das Abzeichen oben rechts zeigt, wie viel wartet.

## Sicherheit

Zuhause läuft die App **ohne Anmeldung** — jeder im selben WLAN kann die Listen
lesen und ändern. Fürs Heimnetz ist das gewollt; ins offene Internet gehört sie so
nicht. Nur lokal: `./start.sh --host 127.0.0.1`.

Sobald `APP_PASSWORD` gesetzt ist, verlangt jede Seite und jeder API-Aufruf eine
Anmeldung; das Sitzungs-Cookie hält 90 Tage. Nach zehn Fehlversuchen von derselben
Adresse ist 15 Minuten Pause. Erkennt die App, dass sie bei einem Hoster ohne
Passwort läuft, verweigert sie den Start.

## Automatisch starten (nur zuhause)

```bash
cat > ~/Library/LaunchAgents/de.familie.todos.plist <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>de.familie.todos</string>
  <key>ProgramArguments</key>
  <array><string>/Users/Felix/Documents/Familie/ToDos/start.sh</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict></plist>
PLIST
launchctl load ~/Library/LaunchAgents/de.familie.todos.plist
```

Wieder abschalten: `launchctl unload ~/Library/LaunchAgents/de.familie.todos.plist`.

## Dateien

```
EINRICHTUNG.md        Schritt-für-Schritt-Anleitung für beide Wege
einrichten-zuhause.sh Einrichtung zuhause (Datenbank, Modell, Autostart)
einrichten-online.sh  Vorbereitung fürs Internet (.venv, Passwort, Datenbanktest)
start.sh              Start zuhause
render.yaml           Bauplan für Render (kein Dockerfile nötig)
.python-version       Python-Version für Render
requirements.txt      nur online nötig: gunicorn + pg8000
app/
  wsgi.py             die Anwendung: Routen, Anmeldung, Export
  server.py           Start zuhause (Server aus der Standardbibliothek)
  store.py            Datenbank: SQLite oder Postgres, gleiches SQL
  db.py               Tabellen und Abfragen
  auth.py             Familienpasswort und Sitzungen
  classify.py         Prompt, Schema, Providerwahl, Nachbearbeitung
  heuristic.py        Einordnung nach Stichwörtern (offline)
  config.py           Einstellungen und Schlüssel
  calendar_ics.py     Kalender-Feed
  constants.py        Zeithorizonte, Datumslogik
  check.py            Selbsttest: python3 -m app.check
  llm/                anthropic.py · mistral.py · openai.py · ollama.py
web/                  Oberfläche (HTML, CSS, JS, Service Worker)
data/                 todos.db und secrets.json — nur lokal, nicht teilen
```

## Sichern

Zuhause genügt das Kopieren der Datei:

```bash
cp data/todos.db ~/Desktop/todos-backup-$(date +%F).db
```

Betriebsartunabhängig geht es über *Einstellungen → Sicherung und Umzug*.
