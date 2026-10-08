"""Fachliche Datenzugriffe.

Das SQL ist bewusst so geschrieben, dass es auf SQLite und Postgres gleich
läuft - welche der beiden es ist, entscheidet `store` anhand von DATABASE_URL.
"""

from __future__ import annotations

import datetime as dt
import json
import uuid

from . import store
from .constants import LIST_KINDS, now_ts, slugify

# DOUBLE PRECISION statt REAL und ON CONFLICT statt INSERT OR IGNORE: beides
# verstehen SQLite und Postgres, sodass es nur ein Schema gibt.
SCHEMA = """
CREATE TABLE IF NOT EXISTS lists (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    emoji       TEXT NOT NULL DEFAULT '📋',
    description TEXT NOT NULL DEFAULT '',
    keywords    TEXT NOT NULL DEFAULT '[]',
    kind        TEXT NOT NULL DEFAULT 'tasks',
    in_overview INTEGER NOT NULL DEFAULT 1,
    sort        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS areas (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    emoji       TEXT NOT NULL DEFAULT '📂',
    hint        TEXT NOT NULL DEFAULT '',
    dated       INTEGER NOT NULL DEFAULT 1,
    sort        INTEGER NOT NULL DEFAULT 0,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS people (
    id         TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    emoji      TEXT NOT NULL DEFAULT '🙂',
    skills     TEXT NOT NULL DEFAULT '[]',
    role       TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS todos (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    raw_input     TEXT NOT NULL DEFAULT '',
    note          TEXT NOT NULL DEFAULT '',
    list_id       TEXT,
    assignee_id   TEXT,
    horizon       TEXT NOT NULL DEFAULT 'soon',
    due_date      TEXT,
    priority      TEXT NOT NULL DEFAULT 'normal',
    status        TEXT NOT NULL DEFAULT 'open',
    confidence    DOUBLE PRECISION NOT NULL DEFAULT 0,
    question      TEXT NOT NULL DEFAULT '',
    tags          TEXT NOT NULL DEFAULT '[]',
    engine        TEXT NOT NULL DEFAULT '',
    suggestion    TEXT NOT NULL DEFAULT '{}',
    repeat_rule   TEXT NOT NULL DEFAULT '',
    minutes       INTEGER NOT NULL DEFAULT 0,
    created_from  TEXT NOT NULL DEFAULT '',
    done_by       TEXT NOT NULL DEFAULT '',
    note_source   TEXT NOT NULL DEFAULT '',
    created_at    TEXT NOT NULL,
    done_at       TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    "key"   TEXT PRIMARY KEY,
    "value" TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    label      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_todos_status ON todos(status);
CREATE INDEX IF NOT EXISTS idx_todos_due ON todos(due_date);
"""

SEED_LISTS = [
    ("haushalt", "Haushalt", "🏠", "Putzen, Reparaturen, Wäsche, Müll, Garten",
     ["putzen", "waschen", "müll", "reparieren", "garten", "staubsaugen", "spülmaschine", "glühbirne"]),
    ("einkauf", "Einkauf", "🛒", "Lebensmittel und Besorgungen",
     ["kaufen", "einkaufen", "besorgen", "milch", "brot", "supermarkt", "drogerie", "windeln"]),
    ("kindergarten", "Kindergarten", "🎒", "Alles rund um Kita und Schule",
     ["kita", "kindergarten", "erzieherin", "elternabend", "schule", "turnbeutel", "brotdose"]),
    ("gesundheit", "Gesundheit & Termine", "🩺", "Arzt, Impfungen, Vorsorge, Behörden",
     ["arzt", "termin", "impfung", "zahnarzt", "u-untersuchung", "rezept", "apotheke", "amt"]),
    ("hausverwaltung", "Hausverwaltung", "🏢", "Schriftverkehr mit Vermieter und Verwaltung",
     ["hausverwaltung", "vermieter", "nebenkosten", "mietminderung", "heizung", "kündigung", "schreiben"]),
    ("finanzen", "Finanzen & Papierkram", "📑", "Rechnungen, Versicherungen, Verträge, Steuer",
     ["rechnung", "überweisen", "versicherung", "vertrag", "steuer", "kündigen", "abo"]),
    ("wunschliste", "Wunschliste", "🎁", "Geschenkideen und Wünsche",
     ["geschenk", "wunsch", "geburtstag", "weihnachten", "idee für"], "wishes"),
    ("medien", "Bücher, Filme & Podcasts", "🎬", "Was wir mal lesen, sehen oder hören wollen",
     ["buch", "lesen", "film", "serie", "schauen", "podcast", "hören", "kino", "hörbuch"],
     "media"),
    ("termine", "Termine", "📅", "Was in den Familienkalender eingetragen werden muss",
     ["termin", "uhr", "treffen", "besprechung", "elternabend", "geburtstag",
      "vorstellung", "abholen", "bringen"], "appointments"),
    ("familie", "Familie & Freizeit", "🌳", "Ausflüge, Besuche, gemeinsame Planung",
     ["ausflug", "besuch", "urlaub", "planen", "spielplatz", "oma", "opa"]),
]

DEFAULT_SETTINGS = {
    "provider": "auto",
    "confidence_threshold": "0.7",
    "anthropic_model": "claude-opus-5",
    "mistral_model": "mistral-small-latest",
    "openai_model": "gpt-4o-mini",
    "ollama_model": "gemma4:12b-mlx",
    "ollama_url": "http://localhost:11434",
    "auto_assign": "1",
    # Wird beim ersten Start durch einen Zufallswert ersetzt: Kalender-Abos
    # können keine Cookies mitschicken, deshalb hängt am Feed ein eigener Schlüssel.
    "calendar_token": "",
}


# Spalten, die nach dem ersten Release dazugekommen sind. SQLite kennt kein
# "ADD COLUMN IF NOT EXISTS", deshalb wird der Fehler bei vorhandener Spalte
# geschluckt - das funktioniert in beiden Datenbanken gleich.
LATER_COLUMNS = [
    ("todos", "repeat_rule", "TEXT NOT NULL DEFAULT ''"),
    ("todos", "minutes", "INTEGER NOT NULL DEFAULT 0"),
    ("lists", "kind", "TEXT NOT NULL DEFAULT 'tasks'"),
    ("people", "role", "TEXT NOT NULL DEFAULT ''"),
    ("todos", "created_from", "TEXT NOT NULL DEFAULT ''"),
    ("lists", "in_overview", "INTEGER NOT NULL DEFAULT 1"),
    ("todos", "done_by", "TEXT NOT NULL DEFAULT ''"),
    ("todos", "note_source", "TEXT NOT NULL DEFAULT ''"),
]


def _migrate_columns() -> None:
    """Fehlende Spalten ergänzen. Muss vor jedem Zugriff darauf laufen."""
    for table, column, ddl in LATER_COLUMNS:
        try:
            store.execute(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}")
        except Exception:
            pass   # Spalte ist bereits vorhanden


def _seed_lists() -> None:
    """Startlisten - nur wenn die Datenbank noch gar keine Liste hat."""
    if store.one("SELECT 1 AS x FROM lists LIMIT 1"):
        return
    store.execute_many([
        ("INSERT INTO lists (id, name, emoji, description, keywords, kind, sort, created_at)"
         " VALUES (?,?,?,?,?,?,?,?)",
         (lid, name, emoji, desc, json.dumps(keywords, ensure_ascii=False),
          rest[0] if rest else "tasks", i, now_ts()))
        for i, (lid, name, emoji, desc, keywords, *rest) in enumerate(SEED_LISTS)
    ])


# Die Bereiche der obersten Ebene. Stehen in der Datenbank, nicht im Code -
# so lassen sich eigene anlegen, ohne die App zu ändern. Die Spalte
# lists.kind verweist auf areas.id.
SEED_AREAS = [
    ("tasks", "Todos", "📋", "Haushalt, Papierkram, Behörden …", 1),
    ("shopping", "Einkauf", "🛒", "Täglicher Bedarf, Baumarkt, persönlich …", 0),
    ("appointments", "Termine", "📅", "Zu vereinbaren und was feststeht", 1),
    ("activities", "Unternehmungen", "🎡", "Ausflüge, Essen gehen, Kultur", 0),
    ("postits", "PostIt", "📌", "Notizen und Merkzettel", 0),
    ("wishes", "Wunschzettel", "🎁", "Geschenkideen je Person", 0),
    ("media", "Merken", "🎬", "Bücher, Filme, Podcasts", 0),
]

# Listen, die beim ersten Mal in einem neuen Bereich entstehen
SEED_AREA_LISTS = {
    "postits": [
        ("notizen", "Notizen", "📌", "Was man sich kurz merken will"),
    ],
    "activities": [
        ("ausfluege", "Ausflüge & Reisen", "🧭", "Ostsee, Wochenenden, Tagestouren"),
        ("essen-gehen", "Essen gehen", "🍽", "Restaurants, die wir mal ausprobieren wollen"),
        ("kultur", "Kultur & mit Kind", "🎭", "Theater, Ausstellungen, Konzerte"),
    ],
}


def get_areas() -> list[dict]:
    rows = store.query("SELECT * FROM areas ORDER BY sort, name")
    return [{"id": r["id"], "name": r["name"], "emoji": r["emoji"],
             "hint": r["hint"], "dated": bool(r["dated"]), "sort": r["sort"]}
            for r in rows]


def area_is_dated(kind: str) -> bool:
    """Hat dieser Bereich Termine und Dauer? Unbekanntes gilt als Aufgabe."""
    row = store.one("SELECT dated FROM areas WHERE id=?", (kind or "tasks",))
    return bool(row["dated"]) if row else True


def create_area(name: str, emoji: str = "📂", hint: str = "",
                dated: bool = False) -> dict:
    base = slugify(name)
    area_id, n = base, 2
    while store.one("SELECT 1 AS x FROM areas WHERE id=?", (area_id,)):
        area_id, n = f"{base}-{n}", n + 1
    row = store.one("SELECT COALESCE(MAX(sort), 0) AS m FROM areas")
    store.execute(
        "INSERT INTO areas (id, name, emoji, hint, dated, sort, created_at)"
        " VALUES (?,?,?,?,?,?,?)",
        (area_id, name.strip()[:40], emoji or "📂", hint.strip()[:80],
         1 if dated else 0, (row["m"] or 0) + 1, now_ts()))
    return next(a for a in get_areas() if a["id"] == area_id)


def update_area(area_id: str, fields: dict) -> dict | None:
    sets, values = [], []
    for key in {"name", "emoji", "hint"} & fields.keys():
        sets.append(f"{key}=?")
        values.append(str(fields[key])[:80])
    if "dated" in fields:
        sets.append("dated=?")
        values.append(1 if fields["dated"] else 0)
    if sets:
        values.append(area_id)
        store.execute(f"UPDATE areas SET {', '.join(sets)} WHERE id=?", values)
    return next((a for a in get_areas() if a["id"] == area_id), None)


def delete_area(area_id: str) -> None:
    """Bereich entfernen; seine Listen wandern zu den Aufgaben."""
    store.execute_many([
        ("UPDATE lists SET kind='tasks' WHERE kind=?", (area_id,)),
        ("DELETE FROM areas WHERE id=?", (area_id,)),
    ])


def _seed_areas() -> None:
    store.execute_many([
        ("INSERT INTO areas (id, name, emoji, hint, dated, sort, created_at)"
         " VALUES (?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
         (aid, name, emoji, hint, dated, i, now_ts()))
        for i, (aid, name, emoji, hint, dated) in enumerate(SEED_AREAS)
    ])
    # Zu jedem frisch angelegten Bereich die vorgesehenen Listen
    for area_id, eintraege in SEED_AREA_LISTS.items():
        if store.one("SELECT 1 AS x FROM lists WHERE kind=? LIMIT 1", (area_id,)):
            continue
        row = store.one("SELECT COALESCE(MAX(sort), 0) AS m FROM lists")
        rang = (row["m"] or 0) + 1
        for lid, name, emoji, beschreibung in eintraege:
            store.execute(
                "INSERT INTO lists (id, name, emoji, description, keywords, kind,"
                " in_overview, sort, created_at) VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT (id) DO NOTHING",
                (lid, name, emoji, beschreibung, "[]", area_id, 0, rang, now_ts()))
            rang += 1


def _migrate_data() -> None:
    """Inhaltliche Anpassungen an bestehenden Datenbanken.

    Läuft nach dem Seeding: würde diese Funktion vorher eine Liste anlegen,
    hielte das Seeding die Datenbank für bereits gefüllt und die Startlisten
    fehlten für immer.
    """
    # Bestehende Wunschlisten erkennen und umtypisieren.
    for row in store.query("SELECT id, name FROM lists WHERE kind = 'tasks'"):
        text = f"{row['id']} {row['name']}".lower()
        if "wunsch" in text or "geschenk" in text:
            store.execute("UPDATE lists SET kind='wishes' WHERE id=?", (row["id"],))

    # Einkaufszettel aufschluesseln: eine Ebene mit mehreren Zetteln statt
    # einer einzigen Liste. Laeuft nur einmal - danach gibt es shopping-Listen.
    if not store.one("SELECT 1 AS x FROM lists WHERE kind='shopping' LIMIT 1"):
        row = store.one("SELECT COALESCE(MAX(sort), 0) AS m FROM lists")
        rang = (row["m"] or 0) + 1

        # Den vorhandenen Einkauf behalten und zum taeglichen Bedarf machen -
        # die Eintraege darin bleiben, wo sie sind.
        if store.one("SELECT 1 AS x FROM lists WHERE id='einkauf'"):
            store.execute(
                "UPDATE lists SET kind='shopping', name=?, emoji=?, description=?"
                " WHERE id='einkauf'",
                ("Täglicher Bedarf", "🛒", "Lebensmittel und was im Haushalt ausgeht"))

        weitere = [
            ("einkauf-baumarkt", "Baumarkt", "🔩", "Werkzeug, Material, Garten"),
            ("einkauf-elektro", "Elektro", "🔌", "Geräte, Kabel, Zubehör"),
            ("einkauf-langfristig", "Langfristig", "🗓", "Größere Anschaffungen, nichts Eiliges"),
        ]
        for person in store.query("SELECT id, name FROM people ORDER BY created_at"):
            weitere.append((f"einkauf-{person['id']}", f"{person['name']} persönlich",
                            "👤", f"Was {person['name']} persönlich braucht"))

        for lid, name, emoji, beschreibung in weitere:
            store.execute(
                "INSERT INTO lists (id, name, emoji, description, keywords, kind,"
                " in_overview, sort, created_at) VALUES (?,?,?,?,?,?,?,?,?)"
                " ON CONFLICT (id) DO NOTHING",
                (lid, name, emoji, beschreibung, "[]", "shopping", 0, rang, now_ts()))
            rang += 1

    # Sammellisten fluten die Gesamtuebersicht mit Einzelposten: ein
    # Einkaufszettel hat zwanzig Zeilen, die dort nichts zu suchen haben.
    store.execute(
        "UPDATE lists SET in_overview=0 WHERE kind IN ('wishes', 'media', 'shopping')")

    # Eine Terminliste, falls noch keine da ist.
    if not store.one("SELECT 1 AS x FROM lists WHERE kind='appointments' LIMIT 1"):
        row = store.one("SELECT COALESCE(MAX(sort), 0) AS m FROM lists")
        store.execute(
            "INSERT INTO lists (id, name, emoji, description, keywords, kind, sort, created_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
            ("termine", "Termine", "📅",
             "Was in den Familienkalender eingetragen werden muss",
             json.dumps(["termin", "uhr", "treffen", "besprechung", "elternabend",
                         "geburtstag", "abholen", "bringen"], ensure_ascii=False),
             "appointments", (row["m"] or 0) + 1, now_ts()))

    # Eine Liste für Bücher, Filme und Podcasts, falls noch keine da ist.
    if not store.one("SELECT 1 AS x FROM lists WHERE kind='media' LIMIT 1"):
        row = store.one("SELECT COALESCE(MAX(sort), 0) AS m FROM lists")
        store.execute(
            "INSERT INTO lists (id, name, emoji, description, keywords, kind, sort, created_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
            ("medien", "Bücher, Filme & Podcasts", "🎬",
             "Was wir mal lesen, sehen oder hören wollen",
             json.dumps(["buch", "lesen", "film", "serie", "schauen", "podcast",
                         "hören", "netflix", "kino", "hörbuch"], ensure_ascii=False),
             "media", (row["m"] or 0) + 1, now_ts()))


def init() -> None:
    store.script(SCHEMA)
    _migrate_columns()
    _seed_areas()
    _seed_lists()
    _migrate_data()
    store.execute_many([
        ('INSERT INTO settings ("key", "value") VALUES (?,?) ON CONFLICT ("key") DO NOTHING',
         (key, value))
        for key, value in DEFAULT_SETTINGS.items()
    ])
    if not get_settings().get("calendar_token"):
        import secrets as _secrets
        set_settings({"calendar_token": _secrets.token_urlsafe(18)})


# --- Settings -----------------------------------------------------------

def get_settings() -> dict[str, str]:
    return {r["key"]: r["value"] for r in store.query('SELECT "key", "value" FROM settings')}


def set_settings(values: dict) -> None:
    statements = [
        ('INSERT INTO settings ("key", "value") VALUES (?,?)'
         ' ON CONFLICT ("key") DO UPDATE SET "value" = excluded."value"', (key, str(value)))
        for key, value in values.items() if key in DEFAULT_SETTINGS
    ]
    if statements:
        store.execute_many(statements)


# --- Listen -------------------------------------------------------------

def _list_row(row: dict) -> dict:
    return {
        "id": row["id"], "name": row["name"], "emoji": row["emoji"],
        "description": row["description"], "keywords": json.loads(row["keywords"] or "[]"),
        "kind": row.get("kind") or "tasks",
        "inOverview": bool(row["in_overview"]) if row.get("in_overview") is not None else True,
        "sort": row["sort"],
    }


def get_lists() -> list[dict]:
    return [_list_row(r) for r in store.query("SELECT * FROM lists ORDER BY sort, name")]


def get_list(list_id: str) -> dict | None:
    row = store.one("SELECT * FROM lists WHERE id=?", (list_id,))
    return _list_row(row) if row else None


def create_list(name: str, emoji: str = "📋", description: str = "",
                keywords: list | None = None, kind: str = "tasks") -> dict:
    base = slugify(name)
    list_id, n = base, 2
    while store.one("SELECT 1 AS x FROM lists WHERE id=?", (list_id,)):
        list_id, n = f"{base}-{n}", n + 1
    row = store.one("SELECT COALESCE(MAX(sort), 0) AS m FROM lists")
    store.execute(
        "INSERT INTO lists (id, name, emoji, description, keywords, kind, sort, created_at)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (list_id, name.strip(), emoji or "📋", description,
         json.dumps(keywords or [], ensure_ascii=False),
         kind if store.one("SELECT 1 AS x FROM areas WHERE id=?", (kind,)) else "tasks",
         (row["m"] or 0) + 1, now_ts()),
    )
    return get_list(list_id)


def update_list(list_id: str, fields: dict) -> dict | None:
    sets, values = [], []
    for key in {"name", "emoji", "description", "sort", "kind"} & fields.keys():
        sets.append(f"{key}=?")
        values.append(fields[key])
    if "inOverview" in fields:
        sets.append("in_overview=?")
        values.append(1 if fields["inOverview"] else 0)
    if "keywords" in fields:
        sets.append("keywords=?")
        values.append(json.dumps(fields["keywords"], ensure_ascii=False))
    if not sets:
        return get_list(list_id)
    values.append(list_id)
    store.execute(f"UPDATE lists SET {', '.join(sets)} WHERE id=?", values)
    return get_list(list_id)


def delete_list(list_id: str) -> None:
    store.execute_many([
        ("UPDATE todos SET list_id=NULL WHERE list_id=?", (list_id,)),
        ("DELETE FROM lists WHERE id=?", (list_id,)),
    ])


# --- Personen -----------------------------------------------------------

def _person_row(row: dict) -> dict:
    return {"id": row["id"], "name": row["name"], "emoji": row["emoji"],
            "skills": json.loads(row["skills"] or "[]"),
            "role": row.get("role") or ""}


def get_people() -> list[dict]:
    return [_person_row(r) for r in store.query("SELECT * FROM people ORDER BY created_at")]


def get_person(person_id: str) -> dict | None:
    row = store.one("SELECT * FROM people WHERE id=?", (person_id,))
    return _person_row(row) if row else None


def create_person(name: str, emoji: str = "🙂", skills: list | None = None,
                  role: str = "") -> dict:
    base = slugify(name)
    person_id, n = base, 2
    while store.one("SELECT 1 AS x FROM people WHERE id=?", (person_id,)):
        person_id, n = f"{base}-{n}", n + 1
    store.execute(
        "INSERT INTO people (id, name, emoji, skills, role, created_at)"
        " VALUES (?,?,?,?,?,?)",
        (person_id, name.strip(), emoji or "🙂",
         json.dumps(skills or [], ensure_ascii=False), role.strip()[:60], now_ts()),
    )
    return get_person(person_id)


def update_person(person_id: str, fields: dict) -> dict | None:
    sets, values = [], []
    for key in {"name", "emoji", "role"} & fields.keys():
        sets.append(f"{key}=?")
        values.append(str(fields[key])[:60])
    if "skills" in fields:
        sets.append("skills=?")
        values.append(json.dumps(fields["skills"], ensure_ascii=False))
    if not sets:
        return get_person(person_id)
    values.append(person_id)
    store.execute(f"UPDATE people SET {', '.join(sets)} WHERE id=?", values)
    return get_person(person_id)


def delete_person(person_id: str) -> None:
    store.execute_many([
        ("UPDATE todos SET assignee_id=NULL WHERE assignee_id=?", (person_id,)),
        ("DELETE FROM people WHERE id=?", (person_id,)),
    ])


# --- Todos --------------------------------------------------------------

def _todo_row(row: dict) -> dict:
    return {
        "id": row["id"], "title": row["title"], "rawInput": row["raw_input"],
        "note": row["note"], "listId": row["list_id"], "assigneeId": row["assignee_id"],
        "horizon": row["horizon"], "dueDate": row["due_date"], "priority": row["priority"],
        "status": row["status"], "confidence": row["confidence"], "question": row["question"],
        "tags": json.loads(row["tags"] or "[]"), "engine": row["engine"],
        "repeat": row.get("repeat_rule") or "",
        "minutes": int(row.get("minutes") or 0),
        "suggestion": json.loads(row["suggestion"] or "{}"),
        "createdAt": row["created_at"], "doneAt": row["done_at"],
        "createdFrom": row.get("created_from") or "",
        "doneBy": row.get("done_by") or "",
        "noteSource": row.get("note_source") or "",
    }


def get_todos(include_done: bool = True) -> list[dict]:
    sql = "SELECT * FROM todos"
    if not include_done:
        sql += " WHERE status <> 'done'"
    sql += " ORDER BY (CASE WHEN due_date IS NULL THEN 1 ELSE 0 END), due_date, created_at"
    return [_todo_row(r) for r in store.query(sql)]


def get_todo(todo_id: str) -> dict | None:
    row = store.one("SELECT * FROM todos WHERE id=?", (todo_id,))
    return _todo_row(row) if row else None


def create_todo(data: dict) -> dict:
    todo_id = data.get("id") or uuid.uuid4().hex[:12]
    store.execute(
        "INSERT INTO todos (id, title, raw_input, note, list_id, assignee_id, horizon,"
        " due_date, priority, status, confidence, question, tags, engine, suggestion,"
        " created_at, done_at, repeat_rule, minutes, created_from, note_source)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            todo_id,
            (data.get("title") or "").strip() or "Ohne Titel",
            data.get("rawInput", ""), data.get("note", ""),
            data.get("listId"), data.get("assigneeId"),
            data.get("horizon", "soon"), data.get("dueDate"),
            data.get("priority", "normal"), data.get("status", "open"),
            float(data.get("confidence", 0) or 0), data.get("question", ""),
            json.dumps(data.get("tags", []), ensure_ascii=False),
            data.get("engine", ""),
            json.dumps(data.get("suggestion", {}), ensure_ascii=False),
            data.get("createdAt") or now_ts(), data.get("doneAt"),
            data.get("repeat", ""), int(data.get("minutes") or 0),
            data.get("createdFrom", ""), data.get("noteSource", ""),
        ),
    )
    return get_todo(todo_id)


def update_todo(todo_id: str, fields: dict) -> dict | None:
    column_for = {
        "title": "title", "note": "note", "listId": "list_id", "assigneeId": "assignee_id",
        "horizon": "horizon", "dueDate": "due_date", "priority": "priority",
        "status": "status", "question": "question", "confidence": "confidence",
        "repeat": "repeat_rule", "minutes": "minutes",
        "noteSource": "note_source",
    }
    sets, values = [], []
    for key, column in column_for.items():
        if key in fields:
            sets.append(f"{column}=?")
            values.append(fields[key])
    if "tags" in fields:
        sets.append("tags=?")
        values.append(json.dumps(fields["tags"], ensure_ascii=False))
    # Eine von Hand geaenderte Notiz gehoert nicht mehr dem Modell.
    if "note" in fields and "noteSource" not in fields:
        sets.append("note_source=?")
        values.append("")
    if fields.get("status") == "done":
        sets.append("done_at=?")
        values.append(now_ts())
        # Wer abgehakt hat, ist verlaesslicher als wem es zugewiesen war.
        sets.append("done_by=?")
        values.append(str(fields.get("doneBy") or "")[:60])
    elif "status" in fields:
        sets.append("done_at=?")
        values.append(None)
        sets.append("done_by=?")
        values.append("")
    if not sets:
        return get_todo(todo_id)
    values.append(todo_id)
    store.execute(f"UPDATE todos SET {', '.join(sets)} WHERE id=?", values)
    return get_todo(todo_id)


def delete_todo(todo_id: str) -> None:
    store.execute("DELETE FROM todos WHERE id=?", (todo_id,))


def recently_done(hours: int = 24) -> list[dict]:
    """Was zuletzt abgehakt wurde - zum Zurückholen nach einem Fehlgriff."""
    since = (dt.datetime.now() - dt.timedelta(hours=int(hours))).isoformat()
    rows = store.query(
        "SELECT * FROM todos WHERE status='done' AND done_at IS NOT NULL"
        " AND done_at >= ? ORDER BY done_at DESC", (since,))
    return [_todo_row(r) for r in rows]


def follow_up_of(todo_id: str) -> dict | None:
    """Der beim Abhaken erzeugte Folgetermin, falls er noch offen ist."""
    row = store.one(
        "SELECT * FROM todos WHERE created_from=? AND status <> 'done'"
        " ORDER BY created_at DESC", (todo_id,))
    return _todo_row(row) if row else None


def purge_done(before_days: int = 30) -> int:
    # Grenzdatum in Python rechnen - date('now', ...) kennt nur SQLite.
    cutoff = (dt.datetime.now() - dt.timedelta(days=int(before_days))).isoformat()
    return store.execute(
        "DELETE FROM todos WHERE status='done' AND done_at IS NOT NULL AND done_at < ?",
        (cutoff,),
    )


# --- Sitzungen ----------------------------------------------------------

def create_session(token: str, expires_at: str, label: str = "") -> None:
    store.execute(
        "INSERT INTO sessions (token, created_at, expires_at, label) VALUES (?,?,?,?)",
        (token, now_ts(), expires_at, label),
    )


def session_valid(token: str) -> bool:
    row = store.one("SELECT expires_at FROM sessions WHERE token=?", (token,))
    return bool(row and row["expires_at"] > now_ts())


def delete_session(token: str) -> None:
    store.execute("DELETE FROM sessions WHERE token=?", (token,))


def purge_sessions() -> int:
    return store.execute("DELETE FROM sessions WHERE expires_at < ?", (now_ts(),))


# --- Export / Import ----------------------------------------------------

EXPORT_VERSION = 1


def export_all() -> dict:
    """Alle Nutzdaten - ohne Sitzungen und ohne Zugangsschlüssel."""
    return {
        "version": EXPORT_VERSION,
        "exportedAt": now_ts(),
        "backend": store.backend(),
        "lists": get_lists(),
        "people": get_people(),
        "todos": get_todos(),
        "settings": get_settings(),
    }


def import_all(data: dict, replace: bool = True) -> dict:
    """Export wieder einspielen. `replace` leert vorher die Tabellen."""
    if not isinstance(data, dict) or "todos" not in data or "lists" not in data:
        raise ValueError("Das sieht nicht nach einer Sicherung dieser App aus.")
    if int(data.get("version", 0)) > EXPORT_VERSION:
        raise ValueError("Die Sicherung stammt aus einer neueren Version der App.")

    statements: list[tuple[str, tuple]] = []
    if replace:
        statements += [("DELETE FROM todos", ()), ("DELETE FROM lists", ()),
                       ("DELETE FROM people", ())]

    for entry in data.get("lists", []):
        statements.append((
            "INSERT INTO lists (id, name, emoji, description, keywords, kind, sort, created_at)"
            " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
            (entry["id"], entry.get("name", entry["id"]), entry.get("emoji", "📋"),
             entry.get("description", ""),
             json.dumps(entry.get("keywords", []), ensure_ascii=False),
             entry.get("kind", "tasks"), int(entry.get("sort", 0)), now_ts())))

    for entry in data.get("people", []):
        statements.append((
            "INSERT INTO people (id, name, emoji, skills, role, created_at)"
            " VALUES (?,?,?,?,?,?) ON CONFLICT (id) DO NOTHING",
            (entry["id"], entry.get("name", entry["id"]), entry.get("emoji", "🙂"),
             json.dumps(entry.get("skills", []), ensure_ascii=False),
             entry.get("role", ""), now_ts())))

    for entry in data.get("todos", []):
        statements.append((
            "INSERT INTO todos (id, title, raw_input, note, list_id, assignee_id, horizon,"
            " due_date, priority, status, confidence, question, tags, engine, suggestion,"
            " created_at, done_at, repeat_rule, minutes)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)"
            " ON CONFLICT (id) DO NOTHING",
            (entry.get("id") or uuid.uuid4().hex[:12], entry.get("title", "Ohne Titel"),
             entry.get("rawInput", ""), entry.get("note", ""), entry.get("listId"),
             entry.get("assigneeId"), entry.get("horizon", "soon"), entry.get("dueDate"),
             entry.get("priority", "normal"), entry.get("status", "open"),
             float(entry.get("confidence", 0) or 0), entry.get("question", ""),
             json.dumps(entry.get("tags", []), ensure_ascii=False), entry.get("engine", ""),
             json.dumps(entry.get("suggestion", {}), ensure_ascii=False),
             entry.get("createdAt") or now_ts(), entry.get("doneAt"),
             entry.get("repeat", ""), int(entry.get("minutes") or 0))))

    store.execute_many(statements)
    for key, value in (data.get("settings") or {}).items():
        if key in DEFAULT_SETTINGS:
            set_settings({key: value})

    return {"lists": len(data.get("lists", [])), "people": len(data.get("people", [])),
            "todos": len(data.get("todos", []))}
