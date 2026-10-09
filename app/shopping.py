"""„Ich bin bei …" - was von den Einkaufszetteln hier zu bekommen ist.

Die Einkaufszettel sind nach Anlass sortiert: täglicher Bedarf, Baumarkt,
persönlich. Im Laden steht man aber vor der umgekehrten Frage - nicht „was
steht auf dem Baumarktzettel", sondern „was von allem, was wir brauchen,
gibt es hier". Shampoo steht beim täglichen Bedarf, ist aber bei Rossmann
zu haben; Klebeband steht im Baumarkt, gibt es aber auch bei Budni.

Statt eine Tabelle „welcher Laden führt was" zu pflegen, wird das Modell
gefragt. Es kennt die gängigen Ketten, und bei einem unbekannten Laden sagt
es das lieber, als zu raten. Gepflegt werden muss dafür nichts.
"""

from __future__ import annotations

from .classify import PROVIDERS, provider_chain
from .llm.base import LLMError

# Mehr Posten gehen nicht in einen Aufruf. Wer 80 Dinge auf den Zetteln hat,
# bekommt die ersten 60 geprüft - alles andere wäre teuer und unübersichtlich.
MAX_POSTEN = 60

SCHEMA = {
    "type": "object",
    "properties": {
        "laden": {
            "type": "string",
            "description": "Die Art des Geschäfts, NICHT sein Name. Ein Wort, "
                           "etwa: Drogerie, Supermarkt, Baumarkt, Apotheke, "
                           "Elektronikmarkt. Kennst du das Geschäft nicht, "
                           "schreibe 'unbekannt'.",
        },
        "posten": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Die Nummern der Posten, die es in diesem Geschäft "
                           "mit hoher Wahrscheinlichkeit gibt. Leer, wenn keiner passt.",
        },
        "unsicher": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Nummern von Posten, die es dort geben könnte, aber "
                           "nicht sicher. Leer lassen, wenn es keine gibt.",
        },
        "hinweis": {
            "type": "string",
            "description": "Ein kurzer Satz, wenn etwas zu sagen ist - etwa dass "
                           "das Geschäft unbekannt ist oder nichts passt. Sonst leer.",
        },
    },
    "required": ["laden", "posten", "unsicher", "hinweis"],
    "additionalProperties": False,
}

SYSTEM = """Du hilfst beim Einkaufen. Jemand steht in einem Geschäft und will \
wissen, welche Posten von seinen Einkaufszetteln er dort gleich mitnehmen kann.

- Antworte auf Deutsch.
- Du bekommst nummerierte Posten. Gib nur Nummern zurück, keine Namen.
- `posten`: was es in diesem Geschäft mit hoher Wahrscheinlichkeit gibt.
- `unsicher`: was es dort geben könnte, aber je nach Filiale oder Größe nicht
  sicher. Lieber hier einsortieren als falsche Sicherheit vorgaukeln.
- Deutsche Ketten kennst du: dm, Rossmann, Müller und Budnikowsky (Budni) sind
  Drogerien; Edeka, Rewe, Aldi, Lidl, Penny und Kaufland Supermärkte; Obi,
  Bauhaus, Hornbach und Toom Baumärkte; Saturn und MediaMarkt Elektronik.
- Drogerien führen auch Grundnahrungsmittel und Babybedarf, aber keine frische
  Ware. Supermärkte führen ein kleines Drogeriesortiment. Das darf in
  `unsicher`.
- Kennst du das Geschäft nicht, setze `laden` auf "unbekannt", lass beide
  Listen leer und sag es im Hinweis. Nicht raten.
- Der Hinweis bleibt leer, wenn es nichts zu sagen gibt."""


def where_to_buy(shop: str, items: list[dict], config: dict) -> tuple[dict, str]:
    """Gibt (Ergebnis, verwendeter Anbieter) zurück.

    `items` sind Posten mit `title` und `listName`; die Reihenfolge bestimmt
    die Nummerierung, auf die sich die Antwort bezieht.
    """
    kette = [name for name in provider_chain(config) if name in PROVIDERS]
    if not kette:
        raise LLMError(
            "Dafür wird ein Sprachmodell gebraucht. Unter „Mehr“ einen Anbieter "
            "einrichten oder Ollama starten."
        )
    if not items:
        raise LLMError("Auf den Einkaufszetteln steht gerade nichts.")

    zeilen = [
        f"{nummer}. {posten['title']}"
        + (f"  (Zettel: {posten['listName']})" if posten.get("listName") else "")
        for nummer, posten in enumerate(items[:MAX_POSTEN], start=1)
    ]
    user = (f"Geschäft: {shop.strip()}\n\n"
            "Posten auf den Einkaufszetteln:\n" + "\n".join(zeilen))

    probleme = []
    for name in kette:
        try:
            return PROVIDERS[name](SYSTEM, user, SCHEMA, config), name
        except LLMError as exc:
            probleme.append(f"{name}: {exc}")
        except (ValueError, KeyError, TypeError) as exc:
            probleme.append(f"{name}: unerwartete Antwort ({exc})")

    raise LLMError("Kein Anbieter hat geantwortet. " + " · ".join(probleme))
