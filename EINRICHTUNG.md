# Einrichtung — Schritt für Schritt

Zwei Wege. Du kannst beide nutzen, nacheinander oder parallel.

* **Weg A — Zuhause.** Läuft auf dem Mac, im Heimnetz, offline möglich. Kostet nichts.
* **Weg B — Im Internet.** Von überall erreichbar, mit Passwort. Kostet 0–7 € im Monat.

Für beide gibt es ein Skript, das die Arbeit macht.

---

## Vorab: die vier Begriffe

**Docker brauchst du nicht.** Render erkennt ein Python-Projekt an der Datei
`requirements.txt` und baut es selbst — ohne Dockerfile, ohne Container-Wissen.
Docker wäre nur nötig, wenn die App etwas Exotisches bräuchte. Tut sie nicht.

**Umgebungsvariablen** sind Einstellungen, die *neben* dem Code liegen statt
darin. Das Familienpasswort oder ein API-Schlüssel gehören nicht ins Repository
— sonst stünden sie bei GitHub für alle lesbar. Stattdessen trägst du sie bei
Render in ein Formular ein, und die App liest sie beim Start. Diese App nutzt vier:

| Variable | Bedeutung | Wo gebraucht |
|---|---|---|
| `APP_PASSWORD` | Familienpasswort. Gesetzt = Anmeldung an. | nur online (Pflicht) |
| `DATABASE_URL` | Adresse der Postgres-Datenbank. Gesetzt = Postgres statt SQLite. | nur online |
| `ANTHROPIC_API_KEY` | Schlüssel fürs Modell (oder `MISTRAL_…` / `OPENAI_…`) | online, zuhause optional |
| `PORT` | Setzt Render selbst. | automatisch |

Genau daran erkennt die App, in welcher Betriebsart sie läuft. Am Code ändert
sich nichts.

**`.venv`** ist ein Ordner, in dem Python-Zusatzpakete landen, statt sich über
dein System zu verteilen. Brauchst du nur für Weg B — Weg A läuft ohne jede
Installation.

**Blueprint (`render.yaml`)** ist der Bauplan: Er sagt Render, wie gebaut und
gestartet wird. Die Datei liegt schon im Projekt, du musst sie nicht anfassen.

---

## Weg A — Zuhause

### 1. Einrichten

```bash
cd ~/Documents/Familie/ToDos
./einrichten-zuhause.sh
```

Das Skript prüft Python, legt die Datenbank an, sucht ein Ollama-Modell,
fragt optional nach einem Cloud-Schlüssel, bietet den Autostart an und führt
zum Schluss einen Selbsttest aus. Du kannst es jederzeit erneut laufen lassen —
vorhandene Daten bleiben unangetastet.

### 2. Starten

```bash
./start.sh
```

Im Terminal stehen dann zwei Adressen: eine für diesen Mac, eine fürs WLAN.

### 3. Aufs Handy holen

Die WLAN-Adresse (`http://192.168.…:8765`) in Safari öffnen →
Teilen → **Zum Home-Bildschirm**. Danach startet sie wie eine App.

### 4. Familie anlegen

In der App unter **Einstellungen** die Personen eintragen und ihnen Kompetenzen
geben: „Handwerk", „Behörden", „Kita", „Arzttermine". Daran entscheidet die
Einordnung, wer eine Aufgabe bekommt. Ohne Personen weist sie niemandem etwas zu.

**Fertig.** Alles Weitere — Listen, Termine — entsteht beim Benutzen.

---

## Weg B — Im Internet (Render + Neon)

### 1. Datenbank bei Neon anlegen

Auf [neon.com](https://neon.com) anmelden (kostenlos, keine Kreditkarte) und
ein Projekt erstellen, Region **Frankfurt**. Danach auf **Connection string**
klicken und die Zeile kopieren. Sie sieht so aus:

```
postgresql://name:passwort@ep-still-bird-123.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

> Warum Neon und nicht Renders eigene Datenbank? Renders kostenlose Postgres
> wird nach 30 Tagen gelöscht. Neons kostenloser Tarif läuft dauerhaft.

### 2. Vorbereiten

```bash
./einrichten-online.sh
```

Das Skript legt `.venv` an, installiert gunicorn und pg8000, erzeugt auf Wunsch
ein Familienpasswort, **prüft deine Neon-Verbindung** und legt bei Bedarf das
Git-Repository an. Am Ende stehen alle Werte in `data/zugangsdaten-online.txt`.

Der Datenbanktest ist der wichtige Teil: Er legt die Tabellen an und schreibt
testweise einen Eintrag. Wenn hier etwas klemmt, siehst du es in zehn Sekunden
statt später im Deployment-Log.

### 3. Code zu GitHub

Auf [github.com](https://github.com) ein **leeres, privates** Repository anlegen
(ohne README ankreuzen), dann:

```bash
git remote add origin git@github.com:DEINNAME/familie-todos.git
git push -u origin main
```

Deine Daten und Schlüssel gehen dabei nicht mit — der Ordner `data/` ist
ausgeschlossen.

### 4. Bei Render einrichten

1. Auf [render.com](https://render.com) anmelden (mit GitHub verbinden)
2. **New → Blueprint** → dein Repository wählen
3. Render liest `render.yaml` und schlägt den Dienst vor
4. Unter **Environment Variables** eintragen — die Werte stehen in
   `data/zugangsdaten-online.txt`:

   | Key | Value |
   |---|---|
   | `APP_PASSWORD` | dein Familienpasswort |
   | `DATABASE_URL` | die Zeile von Neon |
   | `ANTHROPIC_API_KEY` | dein Modell-Schlüssel |

5. **Apply / Create** — der erste Build dauert ein paar Minuten

Danach läuft die App unter `https://familie-todos.onrender.com` (oder ähnlich).
Beim ersten Aufruf fragt sie nach dem Familienpasswort; danach bleibt das Gerät
90 Tage angemeldet.

### 5. Daten mitnehmen

Zuhause: **Einstellungen → Sicherung und Umzug → Alles herunterladen**.
Online: **Sicherung einspielen** und die Datei wählen.

Das geht in beide Richtungen und ist zugleich dein Backup.

### 6. Kalender abonnieren

Die Adresse steht unter **Einstellungen → Kalender** — online hängt ein
Schlüssel daran (`?token=…`), weil Kalender-Programme keine Anmeldung
mitschicken können. Wer die Adresse hat, sieht die Termine: also nur in der
Familie weitergeben.

---

## Was kostet das?

| Posten | Kostenlos | Bezahlt |
|---|---|---|
| Neon (Datenbank) | 0,5 GB, dauerhaft — reicht völlig | — |
| Render (Dienst) | schläft nach 15 Min ein, ~1 Min Kaltstart | ca. 7 $/Monat, schläft nicht |
| Modell | Ollama zuhause: 0 € | ca. 0,8 Cent pro Einwurf |

Anfangen kannst du komplett kostenlos. Wenn das Einschlafen nervt, ist der
Wechsel auf *Starter* ein Klick im Render-Dashboard.

---

## Wenn etwas klemmt

**Immer zuerst:**

```bash
python3 -m app.check                                  # zuhause
DATABASE_URL='postgresql://…' .venv/bin/python -m app.check   # online
```

| Problem | Ursache | Lösung |
|---|---|---|
| App startet bei Render nicht, Log sagt „APP_PASSWORD ist nicht gesetzt" | Absicht — ohne Passwort wäre die Liste öffentlich | Variable bei Render eintragen |
| „Der Treiber pg8000 fehlt" | `DATABASE_URL` gesetzt, Pakete nicht installiert | `.venv/bin/pip install -r requirements.txt` |
| Einordnung ist online plötzlich schlecht | Kein API-Schlüssel gesetzt; online gibt es kein Ollama | Schlüssel als Umgebungsvariable eintragen |
| Erster Aufruf dauert ewig | Kostenloser Render-Tarif schläft nach 15 Min | normal — oder auf Starter wechseln |
| Ollama antwortet nicht | Modell nicht geladen oder Ollama aus | `ollama list` prüfen, Ollama starten |
| Kalender bleibt leer | Schlüssel fehlt in der Adresse | Adresse aus Einstellungen neu kopieren |
| Anmeldung wird nicht angenommen | Nach 10 Fehlversuchen 15 Minuten Sperre | warten, Passwort in der Zugangsdatei nachsehen |

Das Server-Log findest du bei Render unter **Logs**, zuhause bei eingerichtetem
Autostart in `data/server.log`.

---

## Zwischen beiden wechseln

Die Betriebsart hängt allein an den Umgebungsvariablen — du kannst denselben
Ordner für beides nutzen:

```bash
./start.sh                                    # zuhause, SQLite, ohne Anmeldung

APP_PASSWORD=test DATABASE_URL='postgresql://…' \
  .venv/bin/gunicorn app.wsgi:application --bind 0.0.0.0:8765
                                              # wie online, zum Ausprobieren
```

Die zweite Zeile ist exakt das, was Render ausführt.
