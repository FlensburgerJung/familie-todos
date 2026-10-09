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

# Zu jedem Treffer die Abteilung nennen zu müssen, zwingt das Modell zu einer
# Einzelentscheidung je Posten. Ohne das füllt es die beiden Listen einfach
# auf - ein Akkuschrauber landet dann in der Drogerie, weil ihn nichts
# ausdrücklich ausschließt. Die Abteilung hilft nebenbei im Laden beim Suchen.
POSTEN_LISTE = {
    "type": "array",
    "items": {
        "type": "object",
        "properties": {
            "nr": {"type": "integer", "description": "Die Nummer des Postens."},
            "abteilung": {
                "type": "string",
                "description": "In welcher Abteilung dieses Geschäfts der Posten "
                               "steht. Ein bis drei Wörter, etwa: Haarpflege, "
                               "Babybedarf, Schrauben, Molkereiprodukte.",
            },
        },
        "required": ["nr", "abteilung"],
        "additionalProperties": False,
    },
}

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
            **POSTEN_LISTE,
            "description": "Nur Posten, für die man dieses Geschäft tatsächlich "
                           "aufsucht. Meist sind das wenige oder gar keine.",
        },
        "unsicher": {
            **POSTEN_LISTE,
            "description": "Nur Posten, bei denen es wirklich an der Filialgröße "
                           "hängt. Keine Ablage für Zweifelsfälle - im Zweifel "
                           "ganz weglassen.",
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

Die wichtigste Regel: Die meisten Posten gehören in KEINE der beiden Listen.
Nichts zurückzugeben ist der Normalfall und völlig richtig. Eine lange Liste
ist fast immer falsch.

Der Maßstab ist nicht, ob es den Posten dort theoretisch gibt, sondern ob ein
normaler Mensch ihn dort kaufen würde. Ein Baumarkt führt Arbeitsjacken - eine
Chino kauft dort trotzdem niemand. Eine große Drogerie führt Puddingpulver -
zum Einkaufen geht man deshalb nicht dorthin.

- Antworte auf Deutsch.
- Gib je Treffer die Nummer und die Abteilung an, in der er dort steht. Kannst
  du keine plausible Abteilung benennen, gehört der Posten nicht in die Liste.
- `posten`: wofür man dieses Geschäft tatsächlich aufsucht.
- `unsicher`: nur, wenn es wirklich an der Filialgröße hängt. Keine Ablage für
  Zweifelsfälle - im Zweifel ganz weglassen.
- Deutsche Ketten kennst du: dm, Rossmann, Müller und Budnikowsky (Budni) sind
  Drogerien; Edeka, Rewe, Aldi, Lidl, Penny und Kaufland Supermärkte; Obi,
  Bauhaus, Hornbach und Toom Baumärkte; Saturn und MediaMarkt Elektronik.
- Eine Drogerie heißt: Körperpflege, Kosmetik, Wasch- und Putzmittel,
  Babybedarf, Hygiene, freiverkäufliche Arznei. NICHT: Kleidung, Schuhe,
  Werkzeug, Baumaterial, Technik, Möbel, frische Lebensmittel. Haltbare
  Lebensmittel und Süßes führen Drogerien zwar, aber dafür geht man nicht hin -
  weglassen.
- Ein Baumarkt heißt: Werkzeug, Material, Farbe, Garten, Sanitär, Elektroteile.
  NICHT: Alltagskleidung, Lebensmittel, Heimtextilien, Decken. Arbeitskleidung,
  Regenzeug und Gummistiefel führt ein Baumarkt zwar - dafür geht man aber
  nicht hin. Solche Posten gehören nach `unsicher`, nie nach `posten`.
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
