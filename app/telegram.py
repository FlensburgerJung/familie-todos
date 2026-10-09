"""Einwerfen über Telegram.

Warum überhaupt: Beim kostenlosen Tarif schläft der Dienst nach einer
Viertelstunde ohne Zugriff ein und braucht danach bis zu einer Minute zum
Aufwachen. Wer schnell etwas loswerden will, wartet nicht so lange - und
lässt es dann eben bleiben.

Telegram löst das, ohne dass wir selbst eine Warteschlange bauen müssen:
Nicht zugestellte Updates hält Telegram vor und stellt sie erneut zu (rund
24 Stunden lang, nachzusehen in `getWebhookInfo` unter
`pending_update_count`). Für die Familie heißt das: Nachricht abgeschickt,
fertig. Ob der Dienst gerade wach ist, spielt keine Rolle - die Bestätigung
trudelt eben etwas später ein.

Eingerichtet wird nichts fest im Code. Welcher Chat auf welche Liste zeigt,
sagt man dem Bot im Chat selbst (`/hier einkauf`). So funktionieren drei
Gruppen genauso wie eine Gruppe mit Themen oder ein einzelner Privatchat.
"""

from __future__ import annotations

import os
import secrets as _secrets

from . import auth, db
from .constants import slugify

# Mehr Zeilen nimmt eine Nachricht nicht entgegen. Ein versehentlich
# eingefügter Roman soll nicht hundert Einträge erzeugen.
MAX_ZEILEN = 20

HILFE = (
    "So funktioniert's:\n\n"
    "Einfach schreiben, was anfällt — jede Zeile wird ein Eintrag.\n\n"
    "/hier <Ziel> — diesen Chat mit einer Liste oder einem Bereich verbinden, "
    "z. B. /hier einkauf oder /hier todos\n"
    "/hier — zeigt, womit dieser Chat gerade verbunden ist\n"
    "/weg — Verbindung wieder lösen\n"
    "/ichbin <Name> — sagt, wer du bist (zählt nur bei Sammlungen wie "
    "Wunschzettel: dann ist der Eintrag für dich)\n"
    "/wer — zeigt, als wen der Bot dich kennt\n"
    "/hilfe — dieser Text"
)


def token() -> str:
    return (os.environ.get("TELEGRAM_BOT_TOKEN") or "").strip()


def enabled() -> bool:
    return bool(token())


def secret() -> str:
    return (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()


def secret_ok(header_value: str | None) -> bool:
    """Prüft den Header, mit dem Telegram sich ausweist.

    Ohne gesetztes Geheimnis wird nicht geprüft - dann schützt nur noch die
    Freigabe einzelner Chats. Beim Hoster ist das zu wenig, deshalb verlangt
    `check_startup` dort ein Geheimnis.
    """
    erwartet = secret()
    if not erwartet:
        return True
    return _secrets.compare_digest((header_value or "").strip(), erwartet)


def check_startup() -> None:
    """Kein Bot im Internet ohne Webhook-Geheimnis."""
    if enabled() and auth.is_hosted() and not secret():
        raise SystemExit(
            "\n  Abbruch: TELEGRAM_BOT_TOKEN ist gesetzt, TELEGRAM_WEBHOOK_SECRET\n"
            "  aber nicht. Ohne das Geheimnis könnte jeder dem Dienst vortäuschen,\n"
            "  Telegram zu sein. In den Umgebungsvariablen nachtragen.\n"
        )


# --- Ziel eines Chats ---------------------------------------------------

def _finde_ziel(wort: str) -> tuple[str, str, str] | None:
    """Sucht Bereich oder Liste zu einem Stichwort.

    Rückgabe: (area_id, list_id, Anzeigename). Genau eins von beiden ist
    gesetzt - ein Bereich lässt die Einordnung die Liste wählen, eine Liste
    legt sie fest.
    """
    gesucht = slugify(wort) or wort.strip().lower()
    if not gesucht:
        return None

    for area in db.get_areas():
        if area["id"] == gesucht or slugify(area["name"]) == gesucht:
            return (area["id"], "", f"{area['emoji']} {area['name']}")

    for liste in db.get_lists():
        if liste["id"] == gesucht or slugify(liste["name"]) == gesucht:
            return ("", liste["id"], f"{liste['emoji']} {liste['name']}")

    # Zweiter Versuch: Teiltreffer im Namen, damit "baumarkt" auch den
    # Einkaufszettel "Baumarkt" findet, wenn er anders heißt.
    for liste in db.get_lists():
        if gesucht in slugify(liste["name"]):
            return ("", liste["id"], f"{liste['emoji']} {liste['name']}")

    return None


def _ziel_name(bindung: dict) -> str:
    if bindung.get("listId"):
        liste = db.get_list(bindung["listId"])
        return f"{liste['emoji']} {liste['name']}" if liste else "(gelöschte Liste)"
    area = next((a for a in db.get_areas() if a["id"] == bindung.get("areaId")), None)
    return f"{area['emoji']} {area['name']}" if area else "(gelöschter Bereich)"


def _moegliche_ziele() -> str:
    bereiche = ", ".join(a["id"] for a in db.get_areas())
    return f"Mögliche Bereiche: {bereiche}.\nOder der Name einer einzelnen Liste."


# --- Befehle ------------------------------------------------------------

def _befehl_hier(chat_id: str, chat_titel: str, rest: str) -> str:
    bindung = db.telegram_chat(chat_id)

    if not rest:
        if bindung:
            return f"Dieser Chat schreibt nach: {_ziel_name(bindung)}"
        return ("Dieser Chat ist noch mit nichts verbunden.\n\n"
                "/hier <Ziel> verbindet ihn. " + _moegliche_ziele())

    teile = rest.split()
    wort = teile[0]
    passwort = teile[1] if len(teile) > 1 else ""

    # Einen noch nicht verbundenen Chat darf nur anbinden, wer das
    # Familienpasswort kennt - der Bot ist über seinen Namen auffindbar.
    # Ein bereits verbundener Chat gilt als freigegeben.
    if auth.enabled() and not bindung:
        if not _secrets.compare_digest(passwort, auth.password()):
            return ("Dafür brauche ich das Familienpasswort:\n"
                    "/hier " + wort + " <Passwort>\n\n"
                    "Die Nachricht danach am besten löschen.")

    ziel = _finde_ziel(wort)
    if not ziel:
        return f"„{wort}“ kenne ich nicht.\n\n" + _moegliche_ziele()

    area_id, list_id, name = ziel
    db.bind_telegram_chat(chat_id, area_id, list_id, chat_titel)
    if list_id:
        return (f"Verbunden. Alles hier landet ab jetzt auf {name}.\n"
                "Jede Zeile wird ein eigener Eintrag.")
    return (f"Verbunden. Alles hier landet ab jetzt im Bereich {name} — "
            "welche Liste genau, entscheidet die Einordnung.")


def _befehl_ichbin(chat_id: str, tg_user: str, rest: str) -> str:
    if not rest:
        person_id = db.telegram_person(tg_user)
        person = db.get_person(person_id) if person_id else None
        if person:
            return f"Ich kenne dich als {person['emoji']} {person['name']}."
        return ("Ich weiß noch nicht, wer du bist.\n"
                "/ichbin <Name> — " + ", ".join(p["name"] for p in db.get_people()))

    gesucht = rest.strip().lower()
    for person in db.get_people():
        if person["name"].lower() == gesucht or person["id"] == gesucht:
            db.bind_telegram_user(tg_user, person["id"])
            return (f"Alles klar, {person['emoji']} {person['name']}.\n"
                    "Bei Sammlungen wie dem Wunschzettel sind deine Einträge "
                    "damit für dich.")
    namen = ", ".join(p["name"] for p in db.get_people())
    return f"„{rest}“ kenne ich nicht. Vorhanden: {namen}"


# --- Hauptweg -----------------------------------------------------------

def handle(update: dict, capture) -> dict | None:
    """Verarbeitet ein Telegram-Update.

    `capture` ist die Einwurf-Funktion der App - hereingereicht, damit dieses
    Modul nichts von der WSGI-Schicht wissen muss.

    Rückgabe ist der Antwortkörper für den Webhook: Telegram führt eine darin
    beschriebene Methode gleich mit aus, das spart den Rückruf.
    """
    nachricht = update.get("message") or update.get("channel_post")
    if not isinstance(nachricht, dict):
        return None

    absender = nachricht.get("from") or {}
    if absender.get("is_bot"):
        return None

    chat = nachricht.get("chat") or {}
    chat_id = str(chat.get("id") or "")
    if not chat_id:
        return None
    chat_titel = (chat.get("title") or chat.get("first_name") or "")[:80]
    tg_user = str(absender.get("id") or "")

    text = (nachricht.get("text") or nachricht.get("caption") or "").strip()
    if not text:
        return None

    def antwort(inhalt: str) -> dict:
        return {"method": "sendMessage", "chat_id": chat.get("id"),
                "text": inhalt[:4000]}

    # --- Befehle ---
    if text.startswith("/"):
        kopf, _, rest = text.partition(" ")
        # In Gruppen hängt Telegram den Botnamen an: /hier@familienbot
        befehl = kopf.split("@", 1)[0].lower()
        rest = rest.strip()

        if befehl in ("/start", "/hilfe", "/help"):
            return antwort(HILFE)
        if befehl == "/hier":
            return antwort(_befehl_hier(chat_id, chat_titel, rest))
        if befehl == "/weg":
            if not db.telegram_chat(chat_id):
                return antwort("Dieser Chat war mit nichts verbunden.")
            db.unbind_telegram_chat(chat_id)
            return antwort("Verbindung gelöst. Hier landet nichts mehr in der App.")
        if befehl == "/ichbin":
            return antwort(_befehl_ichbin(chat_id, tg_user, rest))
        if befehl == "/wer":
            return antwort(_befehl_ichbin(chat_id, tg_user, ""))
        return antwort(f"Den Befehl {befehl} kenne ich nicht.\n\n" + HILFE)

    # --- Normaler Text ---
    bindung = db.telegram_chat(chat_id)
    if not bindung:
        # Kein unverbundener Chat darf schreiben: Der Bot ist über seinen
        # Namen auffindbar, sonst stünde Fremdes auf dem Einkaufszettel.
        return antwort("Dieser Chat ist noch nicht verbunden.\n\n"
                       "/hier <Ziel> <Familienpasswort> verbindet ihn.\n"
                       + _moegliche_ziele())

    person_id = db.telegram_person(tg_user)

    # Bei Sammlungen heißt die Person „für wen", bei Aufgaben „wer macht das".
    # Den Absender als Zuständigen einzutragen wäre im zweiten Fall falsch:
    # Wer den tropfenden Wasserhahn meldet, hat ihn nicht zu reparieren.
    area_id = bindung.get("areaId") or ""
    if bindung.get("listId"):
        liste = db.get_list(bindung["listId"])
        area_id = (liste or {}).get("kind", "tasks")
    fuer_person = person_id if (area_id and not db.area_is_dated(area_id)) else ""

    zeilen = [z.strip() for z in text.splitlines() if z.strip()][:MAX_ZEILEN]
    erledigt, fehler = [], []
    for zeile in zeilen:
        try:
            ergebnis = capture({
                "text": zeile,
                "listId": bindung.get("listId") or "",
                "kind": bindung.get("areaId") or "",
                "assigneeId": fuer_person,
                # Die Kennung macht aus einer erneuten Zustellung keinen
                # zweiten Eintrag - Telegram stellt im Zweifel mehrfach zu.
                "clientId": f"tg-{update.get('update_id')}-{len(erledigt) + len(fehler)}",
            })
            todo = ergebnis["todo"]
            liste = db.get_list(todo["listId"]) if todo.get("listId") else None
            erledigt.append(
                f"✓ {todo['title']}"
                + (f" → {liste['emoji']} {liste['name']}" if liste else " → zu prüfen"))
        except Exception as fehler_objekt:        # noqa: BLE001 - Antwort statt Absturz
            fehler.append(f"✗ {zeile[:60]}: {fehler_objekt}")

    return antwort("\n".join(erledigt + fehler) or "Nichts eingetragen.")
