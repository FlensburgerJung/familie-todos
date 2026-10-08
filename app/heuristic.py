"""Regelbasierte Einordnung ohne LLM.

Zwei Aufgaben: echter Offline-Betrieb, wenn kein Modell erreichbar ist, und
Sicherheitsnetz, wenn ein Anbieter gerade ausfällt. Sie rät schlechter als ein
Modell - deshalb markiert sie ihre Treffer mit niedriger Sicherheit, sodass
das Ergebnis in der Inbox landet und bestätigt wird.
"""

from __future__ import annotations

import re

from .constants import PRIORITIES

# Signalwörter, die unabhängig von den Listen-Keywords etwas verraten.
URGENT_WORDS = {"dringend", "sofort", "asap", "eilt", "wichtig", "heute noch", "notfall"}
LOW_WORDS = {"irgendwann", "gelegentlich", "vielleicht", "wenn zeit ist", "kein stress"}

# Reihenfolge zählt: "jeden zweiten montag" muss vor "jeden montag" greifen.
REPEAT_PHRASES = [
    ("biweekly", ["alle zwei wochen", "alle 2 wochen", "vierzehntägig", "14-tägig",
                  "jede zweite woche"]),
    ("quarterly", ["vierteljährlich", "alle drei monate", "alle 3 monate", "quartalsweise"]),
    ("yearly", ["jährlich", "jedes jahr", "einmal im jahr"]),
    ("monthly", ["monatlich", "jeden monat", "einmal im monat", "jeden ersten"]),
    ("weekdays", ["werktags", "jeden werktag", "an werktagen", "unter der woche"]),
    ("weekly", ["wöchentlich", "jede woche", "einmal die woche", "jeden montag",
                "jeden dienstag", "jeden mittwoch", "jeden donnerstag", "jeden freitag",
                "jeden samstag", "jeden sonntag"]),
    ("daily", ["täglich", "jeden tag", "jeden abend", "jeden morgen", "immer abends",
               "immer morgens"]),
]


def detect_repeat(haystack: str) -> str:
    for rule, phrases in REPEAT_PHRASES:
        if any(phrase in haystack for phrase in phrases):
            return rule
    return ""


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zäöüß0-9]+", (text or "").lower())


def _score(needles: list[str], haystack: str, words: set[str]) -> int:
    """Wie gut passen Stichwörter auf den Text? Mehrwortbegriffe zählen doppelt."""
    score = 0
    for needle in needles:
        needle = (needle or "").strip().lower()
        if not needle:
            continue
        if " " in needle:
            if needle in haystack:
                score += 2
        elif needle in words:
            score += 1
        elif len(needle) > 4 and needle in haystack:
            # Deutsche Komposita: "Müll" trifft auch in "Mülltonne".
            score += 1
    return score


# Ohne Modell lässt sich der Aufwand nur grob raten - lieber wenige, sichere
# Fälle abdecken als bei allem daneben zu liegen.
EFFORT_HINTS = [
    (5, ["müll", "mülltonne", "rausstellen", "abholen", "anrufen", "mail", "e-mail"]),
    (10, ["spülmaschine", "wäsche aufhängen", "bett", "gießen", "füttern", "staubsauger leeren"]),
    (30, ["staubsaugen", "putzen", "aufräumen", "bügeln", "kochen", "termin vereinbaren"]),
    (45, ["einkaufen", "besorgen", "supermarkt", "formular", "antrag", "schreiben"]),
    (120, ["großputz", "umräumen", "streichen", "reparieren", "ausflug", "renovieren"]),
]


def guess_effort(haystack: str) -> int:
    for minutes, words in reversed(EFFORT_HINTS):
        if any(word in haystack for word in words):
            return minutes
    return 0


def classify(text: str, horizon: str, lists: list[dict], people: list[dict]) -> dict:
    haystack = (text or "").lower()
    words = set(_tokens(text))

    best_list, best_list_score = "", 0
    for entry in lists:
        score = _score(entry.get("keywords", []), haystack, words)
        score += _score([entry["name"]], haystack, words) * 2
        if score > best_list_score:
            best_list, best_list_score = entry["id"], score

    best_person, best_person_score = "", 0
    for person in people:
        score = _score(person.get("skills", []), haystack, words)
        # Direkte Namensnennung schlägt jede Kompetenz.
        if person["name"].lower() in haystack:
            score += 5
        if score > best_person_score:
            best_person, best_person_score = person["id"], score

    priority = "normal"
    if any(word in haystack for word in URGENT_WORDS) or horizon == "now":
        priority = "high"
    elif any(word in haystack for word in LOW_WORDS) or horizon == "months":
        priority = "low"

    # Titel: erste Zeile, gekürzt, ohne Füllwörter am Anfang.
    title = re.sub(r"^(ich muss|wir müssen|bitte|nicht vergessen:?|todo:?)\s*", "",
                   (text or "").strip(), flags=re.IGNORECASE)
    title = title.split("\n")[0].strip()
    if len(title) > 80:
        title = title[:77].rstrip() + "..."

    # Sicherheit bleibt absichtlich unter der Schwelle, sobald etwas fehlt.
    confidence = 0.25
    if best_list_score >= 2:
        confidence = 0.55
    if best_list_score >= 4:
        confidence = 0.65

    question = ""
    if not best_list:
        question = "Zu welcher Liste gehört das?"

    return {
        "title": title or (text or "").strip()[:80] or "Ohne Titel",
        "list": best_list,
        "new_list": "",
        "new_list_emoji": "",
        "assignee": best_person if best_person_score >= 1 else "",
        "due_date": "",
        "priority": priority if priority in PRIORITIES else "normal",
        "repeat": detect_repeat(haystack),
        "minutes": guess_effort(haystack),
        "note": "",
        "tags": [],
        "confidence": confidence,
        "question": question,
    }
