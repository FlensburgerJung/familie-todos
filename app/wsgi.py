"""Die Anwendung als WSGI-App.

Zuhause startet `app.server` sie mit dem Server aus der Standardbibliothek,
online übernimmt gunicorn dieselbe App. Eine Code-Basis, zwei Betriebsarten.
"""

from __future__ import annotations

import json
import re
import threading
import traceback
from pathlib import Path
from urllib.parse import parse_qs

from . import auth, calendar_ics, classify, config, db, store
from .constants import (
    DEFAULT_HORIZON,
    EFFORTS,
    LIST_KINDS,
    HORIZONS,
    PRIORITIES,
    REPEATS,
    clamp_due_date,
    next_occurrence,
    snap_effort,
)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"

MIME_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".webmanifest": "application/manifest+json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}

MAX_BODY = 2 * 1024 * 1024        # normale Anfragen
MAX_IMPORT_BODY = 32 * 1024 * 1024  # eine eingespielte Sicherung darf größer sein


class ApiError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


# --- Fachlogik ----------------------------------------------------------

def _state() -> dict:
    cfg = config.load()
    settings = db.get_settings()
    return {
        "todos": db.get_todos(),
        "recentlyDone": db.recently_done(24),
        "lists": db.get_lists(),
        "people": db.get_people(),
        "settings": {k: v for k, v in settings.items() if k != "calendar_token"},
        "keys": config.key_status(),
        "horizons": {key: spec["label"] for key, spec in HORIZONS.items()},
        "repeats": {key: spec["label"] for key, spec in REPEATS.items()},
        "efforts": EFFORTS,
        "areas": db.get_areas(),
        "listKinds": {a["id"]: a["name"] for a in db.get_areas()},
        "engineChain": classify.provider_chain(cfg) + ["heuristic"],
        "deployment": {
            "backend": store.backend(),
            "hosted": auth.is_hosted(),
            "authEnabled": auth.enabled(),
            "calendarToken": settings.get("calendar_token", ""),
        },
    }


def _capture(payload: dict) -> dict:
    text = (payload.get("text") or "").strip()
    if not text:
        raise ApiError("Der Text ist leer.")
    horizon = payload.get("horizon") or DEFAULT_HORIZON
    if horizon not in HORIZONS:
        horizon = DEFAULT_HORIZON

    cfg = config.load()
    lists, people = db.get_lists(), db.get_people()

    # Ein Knopf wie „Wunsch" sagt die Art, nicht die Liste. Dann kommen nur
    # Listen dieser Art in Frage - und gibt es davon nur eine, erübrigt sich
    # der Modellaufruf ganz.
    kind_hint = (payload.get("kind") or "").strip()
    if kind_hint and any(a["id"] == kind_hint for a in db.get_areas()):
        passende = [entry for entry in lists if entry.get("kind") == kind_hint]
        if len(passende) == 1:
            payload = {**payload, "listId": passende[0]["id"]}
        elif passende:
            lists = passende

    # Eine ausdrückliche Wahl beim Einwerfen schlägt die Einordnung. Dann muss
    # das Modell nur noch Titel, Dauer und Termin herausarbeiten.
    chosen_list = (payload.get("listId") or "").strip()
    chosen_person = (payload.get("assigneeId") or "").strip()
    if chosen_list and not any(entry["id"] == chosen_list for entry in lists):
        chosen_list = ""
    if chosen_person and not any(person["id"] == chosen_person for person in people):
        chosen_person = ""

    # Steht die Liste schon fest und ist es eine Merkliste, gibt es nichts zu
    # entscheiden: Titel ist der Text, Termin und Dauer entfallen ohnehin.
    target_now = db.get_list(chosen_list) if chosen_list else None
    if target_now and not db.area_is_dated(target_now.get("kind", "tasks")):
        # Steht die Liste fest, erübrigt sich der Modellaufruf. Ein im Text
        # genannter Name soll trotzdem ankommen - "das Buch für Thilo" ist eine
        # Empfehlung fuer ihn. Reine Namenssuche, kostet nichts.
        if not chosen_person:
            kleingeschrieben = text.lower()
            for person in people:
                if person["name"].lower() in kleingeschrieben:
                    chosen_person = person["id"]
                    break

        todo = db.create_todo({
            "title": text[:120], "rawInput": text, "listId": chosen_list,
            "assigneeId": chosen_person or None,
            "status": "open", "confidence": 1.0, "engine": "manuell",
        })
        return {"todo": todo, "engine": "manuell", "problems": [], "autoFiled": True}

    result, engine, problems = classify.classify(text, horizon, lists, people, cfg,
                                                 db.get_areas())

    if chosen_list:
        result["list"] = chosen_list
        result["new_list"] = ""
        result["question"] = ""
        result["confidence"] = 1.0
    if chosen_person:
        result["assignee"] = chosen_person

    try:
        threshold = float(cfg.get("confidence_threshold", 0.7))
    except (TypeError, ValueError):
        threshold = 0.7

    if cfg.get("auto_assign") != "1" and not chosen_person:
        result["assignee"] = ""

    confident = (result["confidence"] >= threshold and bool(result["list"])
                 and not result["question"])

    # Merklisten bekommen keinen Termin, keine Dauer und keine Wiederholung -
    # ein Buchtipp hat keine Frist, egal was das Modell vorschlägt.
    target = db.get_list(result["list"]) if result["list"] else None
    if target and not db.area_is_dated(target.get("kind", "tasks")):
        result["due_date"] = None
        result["minutes"] = 0
        result["repeat"] = ""
        # Die Person bleibt erhalten: in einer Sammlung heisst sie nicht
        # "wer macht das", sondern "fuer wen ist das" - ein Buchtipp fuer
        # Thilo, ein Ausflug fuer Simone. Leer heisst: fuer alle.
    elif target and target.get("kind") == "appointments":
        # Auf der Terminliste heisst „kein Datum" = noch zu vereinbaren. Ein
        # aus dem Zeithorizont errechnetes Datum wuerde das verwischen.
        genannt = (raw_due or "").strip() if (raw_due := result.get("_raw_due")) else ""
        if not genannt:
            result["due_date"] = None

    todo = db.create_todo({
        "title": result["title"], "rawInput": text, "note": result["note"],
        "listId": result["list"] or None, "assigneeId": result["assignee"] or None,
        "horizon": horizon, "dueDate": result["due_date"], "priority": result["priority"],
        "repeat": result.get("repeat", ""), "minutes": result.get("minutes", 0),
        "status": "open" if confident else "inbox", "confidence": result["confidence"],
        "question": result["question"], "tags": result["tags"], "engine": engine,
        "suggestion": {"newList": result["new_list"], "newListEmoji": result["new_list_emoji"]},
    })
    return {"todo": todo, "engine": engine, "problems": problems, "autoFiled": confident}


def _create_todo(payload: dict) -> dict:
    """Direkt anlegen, ohne Sprachmodell.

    Für den Fall, dass man ohnehin schon in der richtigen Liste steht: dort
    etwas hinzuzufügen soll weder Geld kosten noch auf eine Antwort warten.
    """
    title = (payload.get("title") or "").strip()
    if not title:
        raise ApiError("Bitte etwas eintragen.")

    list_id = (payload.get("listId") or "").strip()
    target = db.get_list(list_id) if list_id else None
    if list_id and not target:
        raise ApiError("Diese Liste gibt es nicht.", 404)

    assignee = (payload.get("assigneeId") or "").strip()
    if assignee and not db.get_person(assignee):
        assignee = ""

    horizon = payload.get("horizon") if payload.get("horizon") in HORIZONS else DEFAULT_HORIZON
    dated = db.area_is_dated((target or {}).get("kind", "tasks"))

    # Ein Datum wird uebernommen, wenn es ausdruecklich mitkommt - auch in
    # einer Sammlung. Ein Merkzettel "Donnerstag Turnbeutel" ist kein Termin
    # mit Frist, hat aber einen Tag, an dem er auftauchen soll.
    due = (clamp_due_date(payload.get("dueDate"), horizon)
           if payload.get("dueDate") else None)

    return {"todo": db.create_todo({
        "title": title[:120],
        "rawInput": title,
        "listId": list_id or None,
        "assigneeId": assignee or None,
        "horizon": horizon,
        "dueDate": due,
        "minutes": snap_effort(payload.get("minutes")) if dated else 0,
        "repeat": payload.get("repeat", "") if dated else "",
        "priority": "normal",
        "status": "open",
        "confidence": 1.0,
        "engine": "manuell",
    })}


def _restore(todo_id: str) -> dict:
    """Ein versehentlich abgehaktes Todo zurückholen.

    Bei wiederkehrenden Aufgaben entsteht beim Abhaken der nächste Termin.
    Der muss mit verschwinden, sonst steht die Aufgabe doppelt da.
    """
    todo = db.get_todo(todo_id)
    if not todo:
        raise ApiError("Todo nicht gefunden.", 404)
    if todo["status"] != "done":
        return {"todo": todo, "removedFollowUp": False}

    follow_up = db.follow_up_of(todo_id)
    if follow_up:
        db.delete_todo(follow_up["id"])

    return {"todo": db.update_todo(todo_id, {"status": "open"}),
            "removedFollowUp": bool(follow_up)}


def _confirm(todo_id: str, payload: dict) -> dict:
    todo = db.get_todo(todo_id)
    if not todo:
        raise ApiError("Todo nicht gefunden.", 404)

    fields: dict = {"status": "open", "question": "", "confidence": 1.0}

    new_list_name = (payload.get("newListName") or "").strip()
    if new_list_name:
        created = db.create_list(new_list_name, (payload.get("newListEmoji") or "📋")[:4],
                                 payload.get("newListDescription", ""),
                                 kind=payload.get("newListKind", "tasks"))
        fields["listId"] = created["id"]
    elif "listId" in payload:
        fields["listId"] = payload["listId"] or None

    if "assigneeId" in payload:
        fields["assigneeId"] = payload["assigneeId"] or None
    if "title" in payload and payload["title"].strip():
        fields["title"] = payload["title"].strip()
    if "note" in payload:
        fields["note"] = payload["note"]
    if payload.get("priority") in PRIORITIES:
        fields["priority"] = payload["priority"]
    if payload.get("repeat") in REPEATS:
        fields["repeat"] = payload["repeat"]
    if "minutes" in payload:
        fields["minutes"] = snap_effort(payload["minutes"])
    if payload.get("horizon") in HORIZONS:
        fields["horizon"] = payload["horizon"]
    if payload.get("dueDate"):
        fields["dueDate"] = clamp_due_date(payload["dueDate"],
                                           fields.get("horizon", todo["horizon"]))

    if not fields.get("listId") and not todo["listId"]:
        raise ApiError("Bitte eine Liste wählen.")

    target = db.get_list(fields.get("listId") or todo["listId"])
    if target and not db.area_is_dated(target.get("kind", "tasks")):
        fields["dueDate"] = None
        fields["repeat"] = ""

    return {"todo": db.update_todo(todo_id, fields)}


def _repeat_next(todo: dict) -> dict | None:
    """Beim Abhaken einer wiederkehrenden Aufgabe den nächsten Termin anlegen.

    Es entsteht immer nur der eine nächste Eintrag, nicht ein Vorrat für das
    ganze Jahr - abgehakt wird schließlich in unregelmäßigen Abständen.
    """
    rule = todo.get("repeat") or ""
    if rule not in REPEATS or rule == "":
        return None
    due = next_occurrence(rule, todo.get("dueDate"))
    if not due:
        return None
    return db.create_todo({
        "title": todo["title"],
        "rawInput": todo.get("rawInput", ""),
        "note": todo.get("note", ""),
        "listId": todo.get("listId"),
        "assigneeId": todo.get("assigneeId"),
        "horizon": todo.get("horizon", "soon"),
        "dueDate": due,
        "priority": todo.get("priority", "normal"),
        "minutes": todo.get("minutes", 0),
        "status": "open",
        "confidence": 1.0,
        "tags": todo.get("tags", []),
        "engine": todo.get("engine", ""),
        "repeat": rule,
        "createdFrom": todo["id"],
    })


def _patch_todo(todo_id: str, payload: dict) -> dict:
    todo = db.get_todo(todo_id)
    if not todo:
        raise ApiError("Todo nicht gefunden.", 404)
    fields = {}
    for key in ("title", "note", "listId", "assigneeId", "priority", "status", "tags"):
        if key in payload:
            fields[key] = payload[key]
    if payload.get("doneBy") and db.get_person(payload["doneBy"]):
        fields["doneBy"] = payload["doneBy"]
    if payload.get("horizon") in HORIZONS:
        fields["horizon"] = payload["horizon"]
    if payload.get("repeat") in REPEATS:
        fields["repeat"] = payload["repeat"]
    if "minutes" in payload:
        fields["minutes"] = snap_effort(payload["minutes"])
    if "dueDate" in payload:
        fields["dueDate"] = payload["dueDate"] or None
    if fields.get("priority") not in PRIORITIES:
        fields.pop("priority", None)
    if fields.get("status") not in ("inbox", "open", "done"):
        fields.pop("status", None)

    # Erst nach dem Speichern nachsehen: die Wiederholung kann im selben
    # Aufruf geändert worden sein.
    updated = db.update_todo(todo_id, fields)
    follow_up = None
    if fields.get("status") == "done" and todo["status"] != "done":
        follow_up = _repeat_next(updated)
    return {"todo": updated, "next": follow_up}


def _import(payload: dict) -> dict:
    data = payload.get("data") if "data" in payload else payload
    try:
        result = db.import_all(data, replace=bool(payload.get("replace", True)))
    except ValueError as exc:
        raise ApiError(str(exc)) from exc
    return {"imported": result}


ROUTES: list[tuple[str, str, object]] = [
    ("GET", r"^/api/state$", lambda m, p: _state()),
    ("GET", r"^/api/health$", lambda m, p: {"ok": True, "backend": store.backend()}),
    ("POST", r"^/api/capture$", lambda m, p: _capture(p)),
    ("POST", r"^/api/todos$", lambda m, p: _create_todo(p)),
    ("POST", r"^/api/todos/([\w-]+)/confirm$", lambda m, p: _confirm(m.group(1), p)),
    ("POST", r"^/api/todos/([\w-]+)/restore$", lambda m, p: _restore(m.group(1))),
    ("GET", r"^/api/recent$", lambda m, p: {"todos": db.recently_done(24)}),
    ("PATCH", r"^/api/todos/([\w-]+)$", lambda m, p: _patch_todo(m.group(1), p)),
    ("DELETE", r"^/api/todos/([\w-]+)$",
     lambda m, p: (db.delete_todo(m.group(1)), {"ok": True})[1]),
    ("POST", r"^/api/areas$",
     lambda m, p: {"area": db.create_area(p.get("name", ""), p.get("emoji", "📂"),
                                          p.get("hint", ""), bool(p.get("dated")))}),
    ("PATCH", r"^/api/areas/([\w-]+)$", lambda m, p: {"area": db.update_area(m.group(1), p)}),
    ("DELETE", r"^/api/areas/([\w-]+)$",
     lambda m, p: (db.delete_area(m.group(1)), {"ok": True})[1]),
    ("POST", r"^/api/lists$",
     lambda m, p: {"list": db.create_list(p.get("name", ""), p.get("emoji", "📋"),
                                          p.get("description", ""), p.get("keywords", []),
                                          p.get("kind", "tasks"))}),
    ("PATCH", r"^/api/lists/([\w-]+)$", lambda m, p: {"list": db.update_list(m.group(1), p)}),
    ("DELETE", r"^/api/lists/([\w-]+)$",
     lambda m, p: (db.delete_list(m.group(1)), {"ok": True})[1]),
    ("POST", r"^/api/people$",
     lambda m, p: {"person": db.create_person(p.get("name", ""), p.get("emoji", "🙂"),
                                              p.get("skills", []), p.get("role", ""))}),
    ("PATCH", r"^/api/people/([\w-]+)$", lambda m, p: {"person": db.update_person(m.group(1), p)}),
    ("DELETE", r"^/api/people/([\w-]+)$",
     lambda m, p: (db.delete_person(m.group(1)), {"ok": True})[1]),
    ("PUT", r"^/api/settings$",
     lambda m, p: (db.set_settings(p), config.write_secrets(p), _state())[2]),
    ("POST", r"^/api/maintenance/unlock$",
     lambda m, p: {"cleared": auth.clear_all_attempts()}),
    ("POST", r"^/api/maintenance/purge$",
     lambda m, p: {"removed": db.purge_done(int(p.get("days", 30)))}),
    ("POST", r"^/api/import$", lambda m, p: _import(p)),
]


# --- WSGI ---------------------------------------------------------------

class Request:
    def __init__(self, environ: dict):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET").upper()
        self.path = environ.get("PATH_INFO", "/") or "/"
        self.query = parse_qs(environ.get("QUERY_STRING", ""))
        self.cookie = environ.get("HTTP_COOKIE", "")

    @property
    def secure(self) -> bool:
        forwarded = self.environ.get("HTTP_X_FORWARDED_PROTO", "")
        return forwarded == "https" or self.environ.get("wsgi.url_scheme") == "https"

    @property
    def origin(self) -> str:
        forwarded = self.environ.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()
        return self.environ.get("REMOTE_ADDR", "?")

    def body(self, limit: int = MAX_BODY) -> dict:
        try:
            length = int(self.environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            length = 0
        if length <= 0:
            return {}
        if length > limit:
            raise ApiError("Die Anfrage ist zu groß.", 413)
        raw = self.environ["wsgi.input"].read(length)
        try:
            data = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(f"Ungültiges JSON: {exc}") from exc
        return data if isinstance(data, dict) else {}


class Response:
    def __init__(self, status: int, body: bytes, content_type: str, headers=None):
        self.status = status
        self.body = body
        self.content_type = content_type
        self.headers = headers or []


def json_response(data, status: int = 200, headers=None) -> Response:
    return Response(status, json.dumps(data, ensure_ascii=False).encode("utf-8"),
                    "application/json; charset=utf-8", headers)


def serve_static(path: str) -> Response:
    # /share ist das Ziel der Android-Teilen-Funktion und liefert die App aus;
    # den geteilten Text liest die Oberflaeche aus der Adresse.
    if path in ("/", "", "/share"):
        path = "/index.html"
    target = (WEB_DIR / path.lstrip("/")).resolve()
    if not str(target).startswith(str(WEB_DIR.resolve())) or not target.is_file():
        return Response(404, b"Nicht gefunden", "text/plain; charset=utf-8")
    return Response(200, target.read_bytes(),
                    MIME_TYPES.get(target.suffix, "application/octet-stream"))


def _calendar(request: Request, person_id: str | None) -> Response:
    """Kalender-Abos schicken keine Cookies - deshalb der Token in der URL."""
    if auth.enabled() and not auth.is_signed_in(request.cookie):
        token = (request.query.get("token") or [""])[0]
        expected = db.get_settings().get("calendar_token", "")
        if not expected or token != expected:
            return Response(403, b"Kalender-Schluessel fehlt oder stimmt nicht.",
                            "text/plain; charset=utf-8")

    todos = db.get_todos(include_done=False)
    people = db.get_people()
    name = "Familie ToDos"
    if person_id:
        person = db.get_person(person_id)
        if not person:
            return Response(404, b"Person nicht gefunden", "text/plain; charset=utf-8")
        todos = [t for t in todos if t["assigneeId"] == person_id]
        name = f"ToDos {person['name']}"

    dated = {a["id"] for a in db.get_areas() if a["dated"]}
    ics = calendar_ics.build(todos, db.get_lists(), people, name, dated)
    return Response(200, ics.encode("utf-8"), "text/calendar; charset=utf-8",
                    [("Content-Disposition", f'inline; filename="{person_id or "familie"}.ics"')])


def _handle(request: Request) -> Response:
    path = request.path

    # --- ohne Anmeldung erreichbar ---
    # Bewusst ohne Datenbankzugriff: Der Hoster erkennt am offenen Port, dass
    # der Dienst lebt. Haengt diese Antwort an der Datenbank, gilt der Start
    # als gescheitert, sobald die Datenbank langsam ist.
    if path == "/api/health":
        return json_response({"ok": True, "backend": store.backend()})

    # Alles Weitere braucht die Tabellen.
    ensure_booted()

    if path == "/api/people-public" and request.method == "GET":
        # Nur Name und Emoji, damit die Anmeldemaske die Auswahl zeigen kann.
        ensure_booted()
        return json_response({"people": [
            {"id": p["id"], "name": p["name"], "emoji": p["emoji"]}
            for p in db.get_people()]})

    if path == "/api/session" and request.method == "GET":
        return json_response({"authEnabled": auth.enabled(),
                              "signedIn": auth.is_signed_in(request.cookie)})

    if path == "/api/login" and request.method == "POST":
        wartezeit = auth.seconds_until_retry(request.origin)
        if wartezeit > 0:
            minuten = max(1, round(wartezeit / 60))
            raise ApiError(
                f"Zu viele Fehlversuche. Bitte in {minuten} "
                f"{'Minute' if minuten == 1 else 'Minuten'} noch einmal probieren.", 429)
        payload = request.body()
        token = auth.login(payload.get("password", ""), request.origin,
                           request.environ.get("HTTP_USER_AGENT", "")[:80])
        if not token:
            uebrig = auth.attempts_left(request.origin)
            # Erst kurz vor der Sperre darauf hinweisen - vorher verunsichert es nur.
            hinweis = (f" Noch {uebrig} Versuche." if uebrig <= 5 else "")
            raise ApiError("Passwort stimmt nicht." + hinweis, 401)
        return json_response({"ok": True},
                             headers=[("Set-Cookie", auth.cookie_header(token, request.secure))])

    if path == "/api/logout" and request.method == "POST":
        auth.logout(request.cookie)
        return json_response({"ok": True},
                             headers=[("Set-Cookie", auth.clear_cookie_header(request.secure))])

    if path == "/calendar.ics" or re.fullmatch(r"/calendar/[\w-]+\.ics", path):
        person = None if path == "/calendar.ics" else path.rsplit("/", 1)[1].removesuffix(".ics")
        return _calendar(request, person)

    # Die Login-Seite und ihre Bausteine müssen ohne Anmeldung laden.
    if request.method in ("GET", "HEAD") and not path.startswith("/api/"):
        if not auth.is_signed_in(request.cookie) and path not in (
                "/", "/share", "/index.html", "/style.css", "/app.js", "/icon.svg",
                "/icon-192.png", "/icon-512.png", "/manifest.webmanifest", "/sw.js"):
            return Response(404, b"Nicht gefunden", "text/plain; charset=utf-8")
        return serve_static(path)

    # --- ab hier nur angemeldet ---
    if not auth.is_signed_in(request.cookie):
        raise ApiError("Bitte anmelden.", 401)

    if path == "/api/export" and request.method == "GET":
        data = json.dumps(db.export_all(), ensure_ascii=False, indent=2).encode("utf-8")
        stamp = db.export_all()["exportedAt"][:10]
        return Response(200, data, "application/json; charset=utf-8",
                        [("Content-Disposition",
                          f'attachment; filename="familie-todos-{stamp}.json"')])

    # Erst alle Routen sammeln, deren Muster passt: derselbe Pfad kommt
    # mehrfach vor (etwa PATCH und DELETE auf /api/todos/<id>). Bei der ersten
    # Pfadübereinstimmung abzubrechen hieße, dass nur die zuerst eingetragene
    # Methode erreichbar ist.
    matched = [(method, m, handler) for method, pattern, handler in ROUTES
               if (m := re.fullmatch(pattern, path))]

    for method, match, handler in matched:
        if method != request.method:
            continue
        limit = MAX_IMPORT_BODY if path == "/api/import" else MAX_BODY
        payload = request.body(limit) if request.method in ("POST", "PATCH", "PUT") else {}
        return json_response(handler(match, payload))

    if matched:
        erlaubt = ", ".join(sorted({method for method, _, _ in matched}))
        raise ApiError(f"Methode nicht erlaubt. Möglich: {erlaubt}.", 405)

    raise ApiError("Unbekannte Route.", 404)


STATUS_TEXT = {
    200: "200 OK", 400: "400 Bad Request", 401: "401 Unauthorized",
    403: "403 Forbidden", 404: "404 Not Found", 405: "405 Method Not Allowed",
    413: "413 Payload Too Large", 429: "429 Too Many Requests",
    500: "500 Internal Server Error",
}


def application(environ, start_response):
    request = Request(environ)
    try:
        response = _handle(request)
    except ApiError as exc:
        response = json_response({"error": str(exc)}, exc.status)
    except Exception:
        traceback.print_exc()
        response = json_response({"error": "Interner Fehler - siehe Server-Log."}, 500)

    headers = [
        ("Content-Type", response.content_type),
        ("Content-Length", str(len(response.body))),
        ("Cache-Control", "no-store"),
        ("X-Content-Type-Options", "nosniff"),
        ("Referrer-Policy", "same-origin"),
        # Verhindert, dass die Seite in eine fremde Seite eingebettet wird -
        # sonst koennte dort ein unsichtbarer Rahmen Klicks abfangen.
        ("X-Frame-Options", "DENY"),
        # Alles kommt vom eigenen Server; nichts wird von aussen nachgeladen.
        ("Content-Security-Policy",
         "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
         "script-src 'self'; connect-src 'self'; frame-ancestors 'none'; "
         "base-uri 'none'; form-action 'self'"),
    ]
    if request.secure:
        # Der Browser merkt sich, diese Adresse nur noch verschluesselt zu
        # oeffnen - schuetzt vor dem Abfangen im fremden WLAN.
        headers.append(("Strict-Transport-Security", "max-age=15552000"))
    headers.extend(response.headers)
    start_response(STATUS_TEXT.get(response.status, f"{response.status} Status"), headers)
    if request.method == "HEAD":
        return [b""]
    return [response.body]


# Die Konfiguration wird sofort geprüft - das braucht kein Netz und soll den
# Start verweigern, bevor eine ungeschützte App online geht.
auth.check_startup()

# Die Datenbank dagegen erst beim ersten Zugriff. Beim Import darauf zu warten
# hieße: Faehrt die Datenbank gerade hoch, oeffnet der Server nie seinen Port,
# und der Hoster bricht den Start ab ("No open ports detected").
_booted = False
_boot_lock = threading.Lock()


def ensure_booted() -> None:
    global _booted
    if _booted:
        return
    with _boot_lock:
        if _booted:
            return
        db.init()
        db.purge_sessions()
        _booted = True
