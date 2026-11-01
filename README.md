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
  2. schmale Statuszeile: überfällig · heute · bald · zu prüfen
  3. **Jetzt dran** — die Aufgaben des Tages beim Namen, zum Abhaken
  4. die **Bereiche** als Kacheln, die vier häufigsten vorn:
     Todos · Einkauf · Wunschzettel · **Schmerztagebuch** — danach
     Termine · Unternehmungen · Essensideen · PostIt · Merken · Regelmäßig

     Die vier vorderen stehen fest, der Rest folgt der Reihenfolge aus den
     Einstellungen. Das Schmerztagebuch ist dabei kein Bereich, steht aber
     mitten unter ihnen.
  5. **Wer macht was** — je Person, plus „Frei zu vergeben"

  Die Bereiche sind zweistufig: Ein Tipp auf *Todos* zeigt die einzelnen
  Listen (Haushalt, Einkauf, Termine …), ein weiterer deren Einträge.
  „‹ Start" bzw. „‹ Todos" führt zurück. Einstellungen liegen bewusst
  außerhalb, im Tab „Mehr".

### Wo „überfällig · heute · bald" steht

Die Leiste und der Streifen „Jetzt dran" sind die Abkürzung zu dem, was
ansteht — und die taugt nur, wenn sie da ist, wo man gerade ist. Darum
stehen sie nicht nur auf der Startseite, sondern überall, wo es um
Aufgaben geht:

| Ansicht | Leiste |
|---|---|
| Start, Woche | ja |
| Bereich **Todos**, **Termine**, **Regelmäßig** | ja |
| eine Aufgabenliste (Haushalt, Kindergarten …) | ja |
| überfällig · heute · bald · zu prüfen | ja |
| eine Person, „Frei zu vergeben" | ja |
| **Wunschzettel, Merken, Einkauf, Essensideen, PostIt, Unternehmungen** | nein |
| Listen, Bilanz, Mehr, zuletzt erledigt, Schmerztagebuch | nein |

Der Maßstab ist keine Liste von Ausnahmen, sondern die Frage, ob in dem
Bereich Termine überhaupt etwas bedeuten — und das steht schon in der
Datenbank (`areas.dated`). Auf einem Wunschzettel gibt es kein
„überfällig"; vier Kacheln mit Zahlen von woanders drängelten sich dort nur
vor den Inhalt. Für eigene Bereiche, die später unter „Mehr" entstehen,
gilt die Regel ohne weiteres Zutun.

## Schmerztagebuch

Eine eigene Kachel auf der Startseite, kein Bereich: Hier stehen keine
Aufgaben, sondern Messwerte.

Jeder Eintrag hält **Datum, Uhrzeit und eine Stärke von 0 bis 10** fest —
eine visuelle Analogskala (VAS), wie sie in der Schmerzmedizin übliche ist.
Der Schieber läuft von Grün nach Rot, zu jeder Stufe steht ein Wort dabei
(„mittel", „sehr stark"), damit eine 6 auch in drei Monaten noch etwas
sagt. Die Zahl steht immer neben der Farbe — eine Farbe allein trägt hier
nie die Aussage.

- **Eintragen**: Stärke einstellen, fertig. Datum und Uhrzeit setzt die App.
- **Körperstelle**: Stellen, die schon vorkamen, stehen als Knöpfe bereit —
  wer ein Tagebuch führt, hat meist zwei oder drei und will sie nicht jedes
  Mal tippen. Dazu ein freies Notizfeld („nach der Treppe").
- **Verlauf**: ein Balken je Eintrag über 7, 14, 30 oder 90 Tage, mit
  Mittelwert und der Zahl der Einnahmen im selben Zeitraum. Bewusst kein
  Liniendiagramm: Die Einträge liegen zeitlich unregelmäßig, eine Linie
  behauptete zwischen zwei Messungen einen Verlauf, den niemand beobachtet
  hat.
- **Das Tagebuch** darunter, nach Tagen gebündelt — die Form, in der man es
  in einer Sprechstunde vorzeigt.

### Jetzt oder nachgetragen

Ganz oben steht ein Schalter mit zwei Stellungen: **Jetzt** (die Vorgabe) und
**Nachtragen**.

Im schlimmsten Moment greift niemand zum Telefon — Nachtragen muss also
gehen. Nur darf das eine nicht als das andere durchgehen: Ein Wert, der drei
Tage später aus dem Gedächtnis kommt, ist nicht dasselbe wie einer vom
Moment. Darum bekommt jeder nachgetragene Eintrag den Vermerk
**„nachgetragen"**, der im Tagebuch neben dem Eintrag steht, in der
Übersicht mitgezählt wird („4 nachgetragen") und in der Sicherung erhalten
bleibt. Beim Draufhalten steht dabei, *wann* er eingetragen wurde.

Auf **Nachtragen** gestellt, erscheint ein Zeitfeld — mit der jetzigen Zeit
vorbelegt, damit man nur daran dreht —, und der Kasten bekommt einen
farbigen Rand. Der eingestellte Zeitpunkt **gilt für Schmerz und Mittel
gemeinsam**: „Gestern Abend war es eine 8 und ich habe Tilidin genommen" ist
ein Vorgang, nicht zwei. Ein frischer Besuch des Tagebuchs beginnt immer
wieder bei *Jetzt*, damit nichts unbemerkt auf einem alten Zeitpunkt landet.

Ob etwas nachgetragen ist, **sagt der Mensch, nicht die Uhr**: Die App
rechnet das nicht aus Zeitdifferenzen aus. Nur wer schreibt, weiß, ob er aus
dem Moment oder aus der Erinnerung schreibt. (Technisch käme eine Rechnung
hier ohnehin nicht weit — die Uhrzeit des Eintrags kommt vom Handy in
Ortszeit, die des Servers läuft beim Hoster auf UTC.)

### Schmerzmittel

Im selben Fenster lässt sich festhalten, **wann wie viel von welchem Mittel**
genommen wurde. Fünf stehen als Knöpfe bereit, mit ihren handelsüblichen
Stärken:

| Mittel | Stärken |
|---|---|
| Ibuprofen | **400 mg** (vorangestellt), 200, 600, 800 mg |
| Paracetamol | 500, 1000 mg |
| Naproxen | 250, 500 mg |
| Tilidin | 50, 100, 150, 200 mg · 20 Tropfen |
| Novalgin | 500, 1000 mg · 20, 40 Tropfen |

Mittel antippen, Menge antippen — eingetragen, für den oben eingestellten
Zeitpunkt. Die Mengen klappen erst nach dem ersten Tipp auf; sonst stünden
zwanzig Knöpfe gleichzeitig da und man trifft am Telefon den falschen.

Unter **„Anderes Mittel"** geht alles Weitere: beliebiger Name, Menge und
Einheit (mg · Tropfen · Tablette · ml). Die Liste der fünf ist eine
Abkürzung, keine Beschränkung — ein Tagebuch, das nur fünf Mittel kennt,
wäre beim sechsten wertlos.

**Messungen und Einnahmen stehen in einer gemeinsamen Zeitleiste**, nicht in
zwei Listen. „Schmerz 7 um 19:00, Ibu 600 um 19:10, Schmerz 3 um 20:30"
erzählt etwas — zwei getrennte Listen, zwischen denen man hin- und
herrechnet, nicht. Über jedem Tag steht der Schnitt der Messungen und was an
dem Tag genommen wurde, je Mittel zusammengefasst: zwei mal Ibu 400 wird zu
„Ibu 800 mg". Unterschiedliche Einheiten werden nicht verrechnet — 500 mg und
20 Tropfen Novalgin stehen getrennt, weil sie nicht dasselbe sind.

> Die App **hält fest, was genommen wurde — sie gibt keine Dosierungshinweise**.
> Es gibt bewusst keine Tageshöchstmengen und keine Warnungen: Das wäre ein
> Ratschlag, und den kann ein Familienkalender nicht verantworten. Die
> Tagessumme ist eine Angabe, keine Beurteilung.

Messungen und Einnahmen gehören der Person, die am Gerät angemeldet ist, und
stehen in jeder Sicherung. Das ist das einzige in dieser App, was sich nicht
wiederherstellen lässt: Eine Aufgabe schreibt man neu, einen Schmerz von
vorletztem Dienstag nicht.

### Wann ein Modell gefragt wird — und wann nicht

Jeder Modellaufruf kostet. Deshalb gilt eine einfache Regel:

| Eingabe | Modell? |
|---|---|
| **Rein damit** ohne gewählte Liste | **ja** — nur hier muss jemand entscheiden |
| Knöpfe 📋 ToDo · 🛒 Einkauf · 🎁 Wunsch · 🎬 Merken | nein |
| Liste im Auswahlfeld gewählt | nein |
| Direkt in einer Liste eingetragen | nein |

Die Knöpfe nennen einen Bereich, und daraus leitet die App die Liste selbst
ab: die erste des Bereichs — täglicher Bedarf beim Einkauf, Haushalt bei den
Todos. Ist zusätzlich eine Person gewählt und gibt es deren persönliche
Liste, dann die. „Turnbeutel" mit 🛒 und *Thilo* landet also auf *Thilo
persönlich*, ohne dass jemand gefragt werden muss.

Ohne Modell heißt nicht ohne Einordnung: Die Stichwortsuche läuft weiter,
sie kostet nichts. „Müll jeden Montag rausbringen" auf *Haushalt* wird auch
so als wöchentlich erkannt und mit grober Dauer versehen.

Im Auswahlfeld stehen **Täglicher Bedarf** und **Haushalt** unter *Häufig*
ganz oben — die beiden braucht man im Alltag am häufigsten.

Auf einem Einkaufszettel wird niemandem etwas zugewiesen: Der Zettel sagt
schon, um wessen Einkauf es geht, und ein Posten ist keine Aufgabe, die
jemand übernimmt.

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

### „Ich bin bei …"

Die Einkaufszettel sind nach Anlass sortiert — täglicher Bedarf, Baumarkt,
persönlich. Im Laden stellt sich die umgekehrte Frage: nicht „was steht auf
dem Baumarktzettel", sondern „was von allem brauche ich, das es *hier* gibt".
Shampoo steht beim täglichen Bedarf, ist aber bei Rossmann zu haben.

Auf der Einkauf-Seite steht dafür oben **📍 Ich bin bei …**. Laden eintippen,
und das Modell geht alle Einkaufszettel durch:

```
Rossmann — Drogerie
  ☐ Shampoo            Täglicher Bedarf
  ☐ Zahnpasta          Täglicher Bedarf
  ☐ Windeln Größe 4    Täglicher Bedarf
  ☐ Batterien AA       Elektro
  VIELLEICHT AUCH
  ☐ Milch              Täglicher Bedarf
  ☐ Brot               Täglicher Bedarf
```

Abgehakt wird direkt dort, während man im Gang steht. Was es dort nur
manchmal gibt, steht getrennt unter *vielleicht auch* — lieber ehrlich als
falsche Sicherheit. Einen unbekannten Laden sagt das Modell als solchen an,
statt zu raten.

Eine Tabelle „welche Kette führt was" muss niemand pflegen: Das Modell kennt
dm, Rossmann, Budni, Edeka, Obi und so weiter. Benutzte Läden merkt sich die
App und bietet sie beim nächsten Mal zum Antippen an.

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

Auf dem kostenlosen Tarif schläft der Dienst nach 15 Minuten ein; die erste
Aktion danach dauert bis zu einer Minute. Davon soll man möglichst wenig
merken — an drei Stellen:

**Die App öffnet sich sofort.** Hülle, CSS und JavaScript kommen aus dem
Zwischenspeicher, ohne auf den Server zu warten; nachgeladen wird im
Hintergrund. Preis dafür: Eine neue Fassung der App erscheint erst beim
übernächsten Start.

**Einwerfen wartet nie.** Der Eintrag landet zuerst in einer Warteschlange im
Browser, das Feld ist augenblicklich wieder frei. Antwortet der Server
innerhalb von 2,5 Sekunden, siehst du wie gewohnt, wohin er einsortiert
wurde. Sonst:

> 📥 Gemerkt — wird gesendet, sobald der Server wach ist.

Gesendet wird dann im Hintergrund, notfalls erst beim nächsten Öffnen. Jeder
Eintrag trägt eine Kennung, an der der Server ihn wiedererkennt — eine
erneute Zustellung legt ihn kein zweites Mal an.

**Beim Lesen bleibt der Balken.** Wer die Listen ansehen will, wartet weiter
auf den Kaltstart. Nach gut einer Sekunde erscheint dafür oben:

> ⏳ Der Server war eingeschlafen und fährt hoch (12 s). Bitte nicht mehrfach
> tippen, es geht nichts verloren.

Die Sekundenzahl läuft mit. Die Listen erscheinen schon vorher aus dem
Zwischenspeicher, mit einem gelben Hinweis, dass es ein älterer Stand ist.
Ganz abstellen lässt sich das Einschlafen mit einem externen Ping oder dem
Starter-Tarif — beides steht in [EINRICHTUNG.md](EINRICHTUNG.md).

## Einwerfen per Telegram

Optional, und der bequemste Weg: In einen Telegram-Chat schreiben, fertig.
Telegram hält eine nicht zugestellte Nachricht rund einen Tag lang vor und
stellt sie erneut zu — ob der Dienst gerade wach ist, spielt also keine
Rolle.

Je Chat wird einmal festgelegt, wohin er schreibt:

```
/hier einkauf <Familienpasswort>     Bereich — die Einordnung wählt die Liste
/hier taeglicher-bedarf <Passwort>   feste Liste — kein Modellaufruf, sofort
```

Danach wird jede Zeile einer Nachricht ein Eintrag. So lassen sich getrennte
Gruppen für Einkauf, Todos und Wunschzettel führen — oder ein einzelner
Privatchat. `/ichbin <Name>` wirkt nur bei Sammlungen: Ein Wunsch von Thilo
ist ein Wunsch *für* Thilo; bei Aufgaben bleibt der Absender außen vor.

Nicht verbundene Chats können nichts eintragen. Einrichtung in
[EINRICHTUNG.md](EINRICHTUNG.md).

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
requirements.txt      nur online nötig: gunicorn, pg8000, scramp, certifi
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
