"""Selbsttest: prüft Konfiguration, Datenbank und Modellzugang.

    python3 -m app.check

Vor dem ersten Deployment gegen die echte Datenbank laufen lassen:

    DATABASE_URL='postgresql://...' python3 -m app.check
"""

from __future__ import annotations

import os
import sys
import uuid

from . import auth, classify, config, db, store, telegram

OK, FAIL, INFO = "  ✓", "  ✗", "  ·"


def main() -> int:
    problems = 0

    print("\nBetriebsart")
    print(f"{INFO} Speicher:   {store.describe()}")
    print(f"{INFO} Umgebung:   {'Hoster' if auth.is_hosted() else 'lokal'}")
    print(f"{INFO} Anmeldung:  {'Passwort gesetzt' if auth.enabled() else 'aus'}")
    print(f"{INFO} Telegram:   {'Bot aktiv' if telegram.enabled() else 'aus'}")
    if telegram.enabled() and auth.is_hosted() and not telegram.secret():
        print(f"{FAIL} TELEGRAM_WEBHOOK_SECRET fehlt - der Webhook wäre ungeschützt.")

    if auth.is_hosted() and not auth.enabled():
        print(f"{FAIL} Bei einem Hoster ohne APP_PASSWORD wären die Listen öffentlich.")
        problems += 1

    print("\nDatenbank")
    try:
        db.init()
        print(f"{OK} Verbindung steht, Schema ist angelegt")
    except Exception as exc:
        print(f"{FAIL} Verbindung fehlgeschlagen: {exc}")
        if store.backend() == "postgres":
            print(f"{INFO} Bei Neon: die Zeichenkette aus 'Connection string' nehmen,")
            print(f"{INFO} inklusive ?sslmode=require, und pg8000 installieren.")
        return 1

    # Kompletter Schreib-Lese-Lösch-Zyklus - der sagt mehr als ein reines SELECT.
    probe_id = "selftest-" + uuid.uuid4().hex[:8]
    try:
        db.create_todo({"id": probe_id, "title": "Selbsttest", "listId": None,
                        "dueDate": "2030-01-01", "status": "inbox"})
        written = db.get_todo(probe_id)
        assert written and written["title"] == "Selbsttest"
        db.update_todo(probe_id, {"status": "done"})
        assert db.get_todo(probe_id)["doneAt"]
        db.delete_todo(probe_id)
        assert db.get_todo(probe_id) is None
        print(f"{OK} Anlegen, Ändern, Lesen und Löschen funktionieren")
    except Exception as exc:
        print(f"{FAIL} Schreibtest fehlgeschlagen: {exc}")
        problems += 1
        try:
            db.delete_todo(probe_id)
        except Exception:
            pass

    counts = (len(db.get_lists()), len(db.get_people()), len(db.get_todos()))
    print(f"{INFO} Inhalt: {counts[0]} Listen, {counts[1]} Personen, {counts[2]} Todos")
    if telegram.enabled():
        for chat in db.telegram_chats():
            ziel = db.get_list(chat["listId"]) if chat["listId"] else None
            name = ziel["name"] if ziel else (chat["areaId"] or "?")
            print(f"{INFO} Telegram-Chat „{chat['title'] or chat['chatId']}“ -> {name}")

    try:
        export = db.export_all()
        db.import_all(export, replace=False)
        print(f"{OK} Sicherung lässt sich erzeugen und wieder einspielen")
    except Exception as exc:
        print(f"{FAIL} Export/Import fehlgeschlagen: {exc}")
        problems += 1

    print("\nEinordnung")
    cfg = config.load()
    chain = classify.provider_chain(cfg)
    if chain:
        print(f"{OK} Reihenfolge: {' -> '.join(chain + ['heuristic'])}")
    else:
        print(f"{INFO} Kein Modell erreichbar - es greifen die Stichwort-Regeln.")
        if auth.is_hosted():
            print(f"{FAIL} Online gibt es kein Ollama. Ohne API-Schlüssel bleibt nur die")
            print(f"     Stichwortsuche. Einen Schlüssel als Umgebungsvariable setzen.")
            problems += 1

    for field, env_var in config.KEY_FIELDS.items():
        status = config.key_status()[field]
        if status:
            print(f"{INFO} {env_var}: {status}")

    print("\nModelltest")
    lists, people = db.get_lists(), db.get_people()
    result, engine, issues = classify.classify(
        "Milch und Brot einkaufen", "soon", lists, people, cfg)
    print(f"{OK} „Milch und Brot einkaufen\" -> Liste '{result['list'] or '—'}', "
          f"fällig {result['due_date']}, {int(result['confidence'] * 100)} % sicher [{engine}]")
    for issue in issues:
        print(f"{INFO} übersprungen: {issue}")

    print()
    if problems:
        print(f"  {problems} Punkt(e) zu klären.\n")
        return 1
    print("  Alles in Ordnung.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
