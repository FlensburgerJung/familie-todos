"""Aus einem hingeworfenen Satz wird ein eingeordnetes Todo.

Der Ablauf ist für alle Anbieter derselbe: gleicher Prompt, gleiches Schema,
gleiche Nachbearbeitung. Nur der HTTP-Aufruf dahinter unterscheidet sich.
"""

from __future__ import annotations

import datetime as dt

from . import heuristic
from .constants import (
    DEFAULT_HORIZON,
    EFFORTS,
    LIST_KINDS,
    HORIZONS,
    PRIORITIES,
    REPEATS,
    clamp_due_date,
    iso_date,
    snap_effort,
    today,
)
from .llm import anthropic, mistral, ollama, openai
from .llm.base import LLMError

# Reihenfolge für "auto": erst was konfiguriert ist, am Ende immer die Regeln.
AUTO_ORDER = ["anthropic", "mistral", "openai", "ollama"]

PROVIDERS = {
    "anthropic": anthropic.classify,
    "mistral": mistral.classify,
    "openai": openai.classify,
    "ollama": ollama.classify,
}

# Alle Felder sind Pflicht und nie null - leerer String heißt "weiß ich nicht".
# Das hält das Schema über alle vier Anbieter hinweg identisch.
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {
            "type": "string",
            "description": "Kurzer, klarer Titel im Imperativ, max. 80 Zeichen.",
        },
        "list": {
            "type": "string",
            "description": "ID einer bestehenden Liste. Leer lassen, wenn keine passt.",
        },
        "new_list": {
            "type": "string",
            "description": "Nur wenn wirklich keine bestehende Liste passt: "
                           "Name einer neuen Liste. Sonst leer.",
        },
        "new_list_emoji": {"type": "string", "description": "Ein Emoji für die neue Liste."},
        "assignee": {
            "type": "string",
            "description": "ID der Person, die das erledigen sollte. Leer, wenn unklar.",
        },
        "due_date": {
            "type": "string",
            "description": "Fälligkeitsdatum als YYYY-MM-DD. Leer, wenn sich aus dem "
                           "Text kein konkretes Datum ergibt.",
        },
        "priority": {"type": "string", "enum": list(PRIORITIES)},
        "minutes": {
            "type": "integer",
            "enum": EFFORTS,
            "description": "Geschätzte Dauer in Minuten. 0, wenn sich das nicht "
                           "abschätzen lässt.",
        },
        "repeat": {
            "type": "string",
            "enum": list(REPEATS.keys()),
            "description": "Wiederkehrende Aufgabe? Leer lassen, wenn sie nur "
                           "einmal ansteht.",
        },
        "note": {
            "type": "string",
            "description": "Details aus dem Text, die nicht in den Titel passen. Sonst leer.",
        },
        "tags": {"type": "array", "items": {"type": "string"}},
        "confidence": {
            "type": "number",
            "description": "0 bis 1. Wie sicher ist die Einordnung insgesamt?",
        },
        "question": {
            "type": "string",
            "description": "Nur wenn etwas Wesentliches unklar ist: eine kurze Rückfrage "
                           "auf Deutsch. Sonst leer.",
        },
    },
    "required": ["title", "list", "new_list", "new_list_emoji", "assignee", "due_date",
                 "priority", "repeat", "minutes", "note", "tags", "confidence", "question"],
    "additionalProperties": False,
}

SYSTEM_PROMPT = """Du bist der Sortierer einer Familien-Todo-App. Die Familie wirft \
unsortierte Gedanken hinein, du machst daraus einen sauber eingeordneten Eintrag.

Regeln:
- Antworte immer auf Deutsch.
- Wähle genau eine bestehende Liste, wenn eine halbwegs passt. Neue Listen nur, wenn \
wirklich keine passt - dann `new_list` füllen und `list` leer lassen.
- Weise eine Person nur zu, wenn Name, Rolle oder Kompetenz das nahelegen. Einem \
Kind keine Behördengänge, Rechnungen oder Autoreparaturen. Im Zweifel leer lassen.
- Setze `due_date` nur, wenn der Text ein Datum, einen Wochentag oder eine Frist nennt \
("Freitag", "bis Monatsende", "vor dem Elternabend"); rechne den Wochentag in ein echtes \
Datum um. Sonst leer lassen - dann setzt die App den Zeithorizont ein.
- Nennt der Einwurf eine feste Uhrzeit oder einen Termin mit anderen ("Zahnarzt am \
15.10. um 14 Uhr", "Elternabend Dienstag 19 Uhr"), gehört er in die Terminliste.
- Merklisten (Wünsche, Bücher/Filme/Podcasts) sind keine Aufgaben: dort `due_date`, \
`minutes` und `repeat` leer bzw. 0 lassen und niemanden zuweisen. Ein Buchtipp hat \
keine Frist.
- `minutes` schätzen, wie lange die Aufgabe tatsächlich dauert: Müll runterbringen \
5, Spülmaschine ausräumen 10, einkaufen gehen 45, Wohnung putzen 120. Nicht die \
Wartezeit mitrechnen, nur die eigene Arbeit. 0, wenn das nicht einzuschätzen ist.
- `repeat` setzen, wenn der Text auf eine regelmäßige Aufgabe hindeutet: \
"täglich"/"jeden Tag" -> daily, "jeden Werktag" -> weekdays, "wöchentlich"/"jeden \
Montag" -> weekly, "alle zwei Wochen" -> biweekly, "monatlich" -> monthly, \
"vierteljährlich" -> quarterly, "jährlich" -> yearly. Sonst leer lassen.
- `confidence` ehrlich einschätzen: unter 0.7 heißt, die Familie bestätigt die Einordnung \
von Hand. Bei mehrdeutigen Einwürfen ist ein niedriger Wert richtig.
- `question` nur stellen, wenn eine Antwort die Einordnung wirklich ändern würde.
- Titel im Imperativ, kurz, ohne Füllwörter: "Heizung bei Hausverwaltung melden"."""


WEEKDAYS_DE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag",
               "Samstag", "Sonntag")


def _context_block(lists: list[dict], people: list[dict], horizon: str) -> str:
    horizon_spec = HORIZONS.get(horizon, HORIZONS[DEFAULT_HORIZON])
    now = today()
    default_due = iso_date(now + dt.timedelta(days=horizon_spec["offset_days"]))

    lines = [f"Heute ist {WEEKDAYS_DE[now.weekday()]}, der {iso_date(now)}."]
    lines.append(
        f"Gewählter Zeithorizont: {horizon_spec['label']}. Steht im Text kein "
        f"Termin, wird {default_due} eingetragen."
    )

    lines.append("\nBestehende Listen (ID - Name: wofür):")
    for entry in lists:
        keywords = ", ".join(entry.get("keywords", [])[:8])
        line = f"- {entry['id']} - {entry['name']}: {entry.get('description', '')}"
        kind = entry.get("kind", "tasks")
        if kind == "appointments":
            line += " [Terminliste: alles mit fester Uhrzeit gehört hierher]"
        elif kind != "tasks":
            line += f" [Merkliste ohne Termin: {LIST_KINDS[kind]['label']}]"
        if keywords:
            line += f" [Stichwörter: {keywords}]"
        lines.append(line)

    if people:
        lines.append("\nPersonen (ID - Name: Rolle; Kompetenzen):")
        for person in people:
            skills = ", ".join(person.get("skills", [])) or "keine Kompetenzen hinterlegt"
            role = person.get("role", "").strip()
            wer = f"{person['name']} ({role})" if role else person["name"]
            lines.append(f"- {person['id']} - {wer}: {skills}")
    else:
        lines.append("\nEs sind noch keine Personen angelegt - `assignee` immer leer lassen.")

    return "\n".join(lines)


def _normalize(raw: dict, horizon: str, lists: list[dict], people: list[dict]) -> dict:
    """Modellantwort in etwas verwandeln, dem die App vertrauen kann."""
    list_ids = {entry["id"] for entry in lists}
    person_ids = {person["id"] for person in people}

    def text(key: str) -> str:
        value = raw.get(key, "")
        return value.strip() if isinstance(value, str) else ""

    list_id = text("list")
    if list_id not in list_ids:
        list_id = ""

    new_list = text("new_list") if not list_id else ""

    assignee = text("assignee")
    if assignee not in person_ids:
        assignee = ""

    priority = text("priority").lower()
    if priority not in PRIORITIES:
        priority = "normal"

    repeat = text("repeat").lower()
    if repeat not in REPEATS:
        repeat = ""

    minutes = snap_effort(raw.get("minutes"))

    tags = raw.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    tags = [str(tag).strip() for tag in tags if str(tag).strip()][:6]

    try:
        confidence = float(raw.get("confidence", 0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = min(max(confidence, 0.0), 1.0)

    title = text("title") or "Ohne Titel"
    if len(title) > 120:
        title = title[:117].rstrip() + "..."

    question = text("question")

    # Ein Vorschlag für eine neue Liste wird immer bestätigt - so wächst die
    # Struktur bewusst und nicht durch Zufallstreffer des Modells.
    if new_list:
        confidence = min(confidence, 0.5)
        if not question:
            question = f"Neue Liste „{new_list}“ anlegen?"
    elif not list_id:
        confidence = min(confidence, 0.4)
        if not question:
            question = "Zu welcher Liste gehört das?"

    return {
        "title": title,
        "list": list_id,
        "new_list": new_list,
        "new_list_emoji": text("new_list_emoji")[:4] or "📋",
        "assignee": assignee,
        "due_date": clamp_due_date(text("due_date"), horizon),
        "priority": priority,
        "repeat": repeat,
        "minutes": minutes,
        "note": text("note"),
        "tags": tags,
        "confidence": round(confidence, 2),
        "question": question,
    }


def provider_chain(config: dict) -> list[str]:
    """Welche Anbieter in welcher Reihenfolge versucht werden."""
    choice = (config.get("provider") or "auto").lower()
    if choice in PROVIDERS:
        # Eine ausdrückliche Wahl ist eine Vorliebe, kein Ausschluss: fällt der
        # Anbieter aus, ordnet ein lokales Modell immer noch besser ein als
        # bloße Stichwortsuche.
        chain = [choice]
        if choice != "ollama" and ollama.is_available(config):
            chain.append("ollama")
        return chain
    if choice == "heuristic":
        return []
    chain = []
    for name in AUTO_ORDER:
        if name == "ollama":
            if ollama.is_available(config):
                chain.append(name)
        elif config.get(f"{name}_api_key"):
            chain.append(name)
    return chain


def classify(text: str, horizon: str, lists: list[dict], people: list[dict],
             config: dict) -> tuple[dict, str, list[str]]:
    """Gibt (Einordnung, verwendete Engine, Fehlermeldungen) zurück."""
    if horizon not in HORIZONS:
        horizon = DEFAULT_HORIZON

    system = SYSTEM_PROMPT
    user = (
        f"{_context_block(lists, people, horizon)}\n\n"
        f"Neuer Einwurf der Familie:\n\"\"\"\n{text.strip()}\n\"\"\""
    )

    problems: list[str] = []
    for name in provider_chain(config):
        try:
            raw = PROVIDERS[name](system, user, SCHEMA, config)
            return _normalize(raw, horizon, lists, people), name, problems
        except LLMError as exc:
            problems.append(f"{name}: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            problems.append(f"{name}: unerwartete Antwort ({exc})")

    fallback = heuristic.classify(text, horizon, lists, people)
    fallback["due_date"] = clamp_due_date("", horizon)
    return fallback, "heuristic", problems
