"""Anmeldung mit einem gemeinsamen Familienpasswort.

Aktiv, sobald die Umgebungsvariable APP_PASSWORD gesetzt ist - online also
immer, zuhause standardmäßig nicht. Läuft die App auf Render ohne Passwort,
verweigert sie den Start: eine offene Todo-Liste im Internet wäre schlimmer
als eine, die nicht hochkommt.
"""

from __future__ import annotations

import datetime as dt
import http.cookies
import os
import secrets
import threading

from . import db

COOKIE_NAME = "familie_todos"
SESSION_DAYS = 90

# Anmeldeversuche je Absender bremsen, damit das Passwort nicht durchprobiert
# werden kann. Im Speicher gehalten - reicht für eine Instanz.
#
# Bewusst grosszuegig: Ein geteiltes Familienpasswort tippt man auch mal
# daneben, und alle im selben Haushalt teilen sich nach aussen eine IP-Adresse.
# Zehn Minuten Aussperrung nach einem Vertipper waere unbrauchbar; gegen das
# maschinelle Durchprobieren langer Passwoerter reichen diese Werte allemal.
MAX_ATTEMPTS = 20
WINDOW_SECONDS = 300

_attempts: dict[str, list[float]] = {}
_attempts_lock = threading.Lock()


def password() -> str:
    return (os.environ.get("APP_PASSWORD") or "").strip()


def enabled() -> bool:
    return bool(password())


def is_hosted() -> bool:
    """Läuft die App bei einem Hoster statt zuhause?"""
    return bool(os.environ.get("RENDER") or os.environ.get("PORT")
                or os.environ.get("FLY_APP_NAME"))


def check_startup() -> None:
    """Verhindert den Start einer ungeschützten App im Internet."""
    if is_hosted() and not enabled():
        raise SystemExit(
            "\n  Abbruch: Diese App läuft bei einem Hoster, aber APP_PASSWORD ist nicht\n"
            "  gesetzt. Ohne Passwort wären die Familienlisten öffentlich lesbar.\n"
            "  In den Umgebungsvariablen des Dienstes ein APP_PASSWORD hinterlegen.\n"
        )


# --- Bremse gegen Durchprobieren ---------------------------------------

def _now() -> float:
    return dt.datetime.now().timestamp()


def too_many_attempts(origin: str) -> bool:
    return seconds_until_retry(origin) > 0


def seconds_until_retry(origin: str) -> int:
    """Wie lange noch gesperrt? 0 heißt: Versuch ist erlaubt."""
    with _attempts_lock:
        recent = [t for t in _attempts.get(origin, []) if _now() - t < WINDOW_SECONDS]
        _attempts[origin] = recent
        if len(recent) < MAX_ATTEMPTS:
            return 0
        # Sobald der älteste Versuch aus dem Fenster fällt, geht es weiter.
        return max(1, int(WINDOW_SECONDS - (_now() - min(recent))))


def attempts_left(origin: str) -> int:
    with _attempts_lock:
        recent = [t for t in _attempts.get(origin, []) if _now() - t < WINDOW_SECONDS]
        return max(0, MAX_ATTEMPTS - len(recent))


def note_attempt(origin: str) -> None:
    with _attempts_lock:
        _attempts.setdefault(origin, []).append(_now())


def clear_attempts(origin: str) -> None:
    with _attempts_lock:
        _attempts.pop(origin, None)


def clear_all_attempts() -> int:
    """Alle Sperren aufheben - fuer den Fall, dass sich jemand ausgesperrt hat.

    Darf nur von einem Angemeldeten ausgeloest werden: Wer drin ist, kennt das
    Passwort ohnehin, also entsteht dadurch keine zusaetzliche Angriffsflaeche.
    """
    with _attempts_lock:
        anzahl = len(_attempts)
        _attempts.clear()
        return anzahl


# --- Sitzungen ----------------------------------------------------------

def login(candidate: str, origin: str, label: str = "") -> str | None:
    """Prüft das Passwort und gibt bei Erfolg ein Sitzungstoken zurück."""
    if not secrets.compare_digest((candidate or "").strip(), password()):
        note_attempt(origin)
        return None
    clear_attempts(origin)
    token = secrets.token_urlsafe(32)
    expires = (dt.datetime.now() + dt.timedelta(days=SESSION_DAYS)).replace(microsecond=0)
    db.create_session(token, expires.isoformat(), label[:80])
    return token


def token_from_cookie(header: str | None) -> str:
    if not header:
        return ""
    jar = http.cookies.SimpleCookie()
    try:
        jar.load(header)
    except http.cookies.CookieError:
        return ""
    morsel = jar.get(COOKIE_NAME)
    return morsel.value if morsel else ""


def is_signed_in(cookie_header: str | None) -> bool:
    if not enabled():
        return True
    token = token_from_cookie(cookie_header)
    return bool(token) and db.session_valid(token)


def logout(cookie_header: str | None) -> None:
    token = token_from_cookie(cookie_header)
    if token:
        db.delete_session(token)


def cookie_header(token: str, secure: bool) -> str:
    parts = [
        f"{COOKIE_NAME}={token}",
        "Path=/",
        f"Max-Age={SESSION_DAYS * 86400}",
        "HttpOnly",
        "SameSite=Lax",
    ]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)


def clear_cookie_header(secure: bool) -> str:
    parts = [f"{COOKIE_NAME}=", "Path=/", "Max-Age=0", "HttpOnly", "SameSite=Lax"]
    if secure:
        parts.append("Secure")
    return "; ".join(parts)
