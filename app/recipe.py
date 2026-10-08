"""Rezeptvorschlag zu einer Essensidee.

Nutzt denselben Anbieterweg wie die Einordnung. Bewusst ein eigener Aufruf
und kein Teil des Einwerfens: Ein Rezept will man dann, wenn man kochen will -
nicht bei jeder Idee, die einem durch den Kopf geht. Das spart Geld und hält
die Einordnung schnell.
"""

from __future__ import annotations

from .classify import PROVIDERS, provider_chain
from .llm.base import LLMError

SCHEMA = {
    "type": "object",
    "properties": {
        "titel": {"type": "string", "description": "Name des Gerichts."},
        "dauer_minuten": {"type": "integer", "description": "Zubereitungszeit."},
        "portionen": {"type": "integer", "description": "Für wie viele Personen."},
        "zutaten": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Je ein Eintrag mit Menge, etwa: 500 g Kartoffeln.",
        },
        "schritte": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Arbeitsschritte in Reihenfolge, je ein kurzer Satz.",
        },
        "hinweis": {
            "type": "string",
            "description": "Ein Satz zu Varianten oder Vorbereitung. Sonst leer.",
        },
    },
    "required": ["titel", "dauer_minuten", "portionen", "zutaten", "schritte", "hinweis"],
    "additionalProperties": False,
}

SYSTEM = """Du schlägst einem Familienhaushalt ein Rezept vor.

- Antworte auf Deutsch.
- Alltagstauglich: Zutaten, die es im normalen Supermarkt gibt.
- Mengen auf die genannte Personenzahl rechnen.
- Die Schritte so knapp halten, dass man sie beim Kochen überfliegen kann.
- Wünsche aus den Hinweisen ernst nehmen (kalorienarm, vegetarisch,
  Unverträglichkeiten, Zeitnot) und das Rezept entsprechend wählen."""


def suggest(dish: str, people: int, notes: str, config: dict) -> tuple[dict, str]:
    """Gibt (Rezept, verwendeter Anbieter) zurück."""
    kette = [name for name in provider_chain(config) if name in PROVIDERS]
    if not kette:
        raise LLMError(
            "Dafuer wird ein Sprachmodell gebraucht. Unter 'Mehr' einen Anbieter "
            "einrichten oder Ollama starten."
        )

    user = (
        f"Gericht oder Idee: {dish}\n"
        f"Personen: {people}\n"
        f"Besonderes: {notes.strip() or 'nichts'}"
    )

    probleme = []
    for name in kette:
        try:
            return PROVIDERS[name](SYSTEM, user, SCHEMA, config), name
        except LLMError as exc:
            probleme.append(f"{name}: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            probleme.append(f"{name}: unerwartete Antwort ({exc})")

    raise LLMError("Kein Anbieter hat geantwortet. " + " · ".join(probleme))
