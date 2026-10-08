"""Gemeinsame Konstanten und kleine Helfer."""

from __future__ import annotations

import datetime as dt
import re
import unicodedata

# --- Zeithorizonte ------------------------------------------------------

# Was der Nutzer beim Einwerfen auswählt. offset_days ist die Fälligkeit,
# wenn im Text kein Datum steht - ein genannter Termin ("Montag", "bis
# Monatsende") hat immer Vorrang vor dem Horizont.
HORIZONS = {
    "now": {"label": "Jetzt", "offset_days": 0},
    "soon": {"label": "Bald", "offset_days": 3},
    "weeks": {"label": "In Wochen", "offset_days": 14},
    "months": {"label": "In Monaten", "offset_days": 60},
}

# Reine Plausibilitätsgrenze gegen ausgerutschte Modelle (etwa das falsche Jahr).
MAX_FUTURE_DAYS = 730
DEFAULT_HORIZON = "soon"

PRIORITIES = ("low", "normal", "high")

# Nicht jede Liste ist eine Aufgabenliste. Wünsche und Medien haben keinen
# Termindruck - sie dürfen nicht in "Bald" oder "Überfällig" auftauchen und
# gehören auch nicht in den Kalender.
LIST_KINDS = {
    "tasks": {"label": "Aufgaben", "dated": True},
    # Termine haben eine feste Uhrzeit und gehören in den Familienkalender -
    # deshalb eine eigene Art, auch wenn sie technisch Aufgaben mit Datum sind.
    "appointments": {"label": "Termine", "dated": True},
    "wishes": {"label": "Wünsche", "dated": False},
    "media": {"label": "Bücher, Filme, Podcasts", "dated": False},
}
DEFAULT_LIST_KIND = "tasks"

# Geschätzter Aufwand in Minuten. Stufen statt freier Eingabe: niemand weiß,
# ob Wäsche 23 oder 27 Minuten dauert, und zum Vergleichen reicht die
# Größenordnung. 0 heißt "nicht eingeschätzt".
EFFORTS = [0, 5, 10, 15, 30, 45, 60, 90, 120, 180, 240]


def effort_label(minutes: int) -> str:
    minutes = int(minutes or 0)
    if minutes <= 0:
        return "ohne Angabe"
    if minutes < 60:
        return f"{minutes} Min"
    hours, rest = divmod(minutes, 60)
    return f"{hours} h" if rest == 0 else f"{hours}:{rest:02d} h"


def snap_effort(minutes) -> int:
    """Auf die nächste Stufe runden - Modelle liefern gern krumme Werte."""
    try:
        value = int(round(float(minutes)))
    except (TypeError, ValueError):
        return 0
    if value <= 0:
        return 0
    return min(EFFORTS[1:], key=lambda step: abs(step - value))

# Wiederkehrende Aufgaben. Beim Abhaken legt die App den nächsten Termin an -
# es gibt also immer genau einen offenen Eintrag pro Aufgabe statt hundert
# Vorratstermine in der Zukunft.
REPEATS = {
    "": {"label": "einmalig"},
    "daily": {"label": "täglich", "days": 1},
    "weekdays": {"label": "werktags", "days": 1},   # Wochenende wird übersprungen
    "weekly": {"label": "wöchentlich", "days": 7},
    "biweekly": {"label": "alle 2 Wochen", "days": 14},
    "monthly": {"label": "monatlich", "months": 1},
    "quarterly": {"label": "vierteljährlich", "months": 3},
    "yearly": {"label": "jährlich", "months": 12},
}

# inbox = wartet auf Bestätigung, open = eingeordnet, done = erledigt
STATUSES = ("inbox", "open", "done")

SOON_WINDOW_DAYS = 7  # was im Tab "Bald fällig" auftaucht


def today() -> dt.date:
    return dt.date.today()


def iso_date(d: dt.date) -> str:
    return d.isoformat()


def parse_date(value: str | None) -> dt.date | None:
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value.strip()[:10])
    except (ValueError, AttributeError):
        return None


def now_ts() -> str:
    return dt.datetime.now().replace(microsecond=0).isoformat()


_UMLAUTS = {"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"}


def slugify(text: str) -> str:
    """'Kindergarten Emma' -> 'kindergarten-emma' (umlautfest)."""
    text = (text or "").strip().lower()
    for src, dst in _UMLAUTS.items():
        text = text.replace(src, dst)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "eintrag"


def due_date_for(horizon: str, base: dt.date | None = None) -> dt.date:
    """Standard-Fälligkeit, wenn das LLM kein konkretes Datum liefert."""
    spec = HORIZONS.get(horizon, HORIZONS[DEFAULT_HORIZON])
    return (base or today()) + dt.timedelta(days=spec["offset_days"])


def add_months(date: dt.date, months: int) -> dt.date:
    """Monate addieren, ohne über das Monatsende zu stolpern (31.01. + 1)."""
    month = date.month - 1 + months
    year = date.year + month // 12
    month = month % 12 + 1
    day = min(date.day, [31, 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
                         else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return dt.date(year, month, day)


def next_occurrence(rule: str, last_due: str | None = None) -> str | None:
    """Der nächste Termin einer wiederkehrenden Aufgabe.

    Gerechnet wird ab dem späteren von altem Termin und heute: Wer den Müll
    drei Tage zu spät rausbringt, soll ihn nicht sofort wieder als überfällig
    vorfinden.
    """
    spec = REPEATS.get(rule or "")
    if not spec or rule == "":
        return None

    base = parse_date(last_due) or today()
    if base < today():
        base = today()

    if "months" in spec:
        following = add_months(base, spec["months"])
    else:
        following = base + dt.timedelta(days=spec["days"])

    if rule == "weekdays":
        while following.weekday() >= 5:   # Samstag und Sonntag überspringen
            following += dt.timedelta(days=1)

    return iso_date(following)


def clamp_due_date(value: str | None, horizon: str) -> str:
    """Fälligkeit bestimmen.

    Nennt der Text einen Termin, gilt der - wer "am Montag" schreibt, meint
    Montag, auch wenn er vorher "Jetzt" angetippt hat. Ohne Termin im Text
    entscheidet der Horizont. Geklemmt wird nur gegen Unsinn.
    """
    base = today()
    proposed = parse_date(value)
    if proposed is None:
        return iso_date(due_date_for(horizon, base))
    delta = (proposed - base).days
    if delta > MAX_FUTURE_DAYS:
        return iso_date(due_date_for(horizon, base))
    # Vergangene Termine auf heute ziehen, statt sie sofort überfällig zu machen.
    if delta < 0:
        return iso_date(base)
    return iso_date(proposed)
