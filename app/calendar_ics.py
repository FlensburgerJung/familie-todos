"""ICS-Feed, damit fällige Todos im Familienkalender auftauchen.

Ganztägige Termine statt VTODO: die zeigt jeder Kalender zuverlässig an,
auch Apple Kalender und Google Kalender per Abo-URL.
"""

from __future__ import annotations

import datetime as dt

from .constants import LIST_KINDS, parse_date

PRIORITY_MARK = {"high": "❗️", "normal": "", "low": "·"}


def _escape(text: str) -> str:
    return (text or "").replace("\\", "\\\\").replace(";", "\\;") \
                       .replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """ICS erlaubt max. 75 Oktette pro Zeile; Folgezeilen beginnen mit Space."""
    raw = line.encode("utf-8")
    if len(raw) <= 73:
        return line
    chunks, current = [], b""
    for char in line:
        encoded = char.encode("utf-8")
        if len(current) + len(encoded) > 73:
            chunks.append(current.decode("utf-8"))
            current = b""
        current += encoded
    if current:
        chunks.append(current.decode("utf-8"))
    return "\r\n ".join(chunks)


def build(todos: list[dict], lists: list[dict], people: list[dict],
          name: str = "Familie ToDos") -> str:
    list_by_id = {entry["id"]: entry for entry in lists}
    person_by_id = {person["id"]: person for person in people}
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Familie ToDos//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{_escape(name)}",
        "X-PUBLISHED-TTL:PT1H",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
    ]

    for todo in todos:
        due = parse_date(todo.get("dueDate"))
        if not due or todo.get("status") == "done":
            continue

        entry = list_by_id.get(todo.get("listId") or "")
        # Wünsche und Merklisten haben keinen Termin - sie gehören nicht in
        # den Kalender, sonst steht dort jeder Buchtipp als Tagestermin.
        if entry and not LIST_KINDS.get(entry.get("kind", "tasks"), {}).get("dated", True):
            continue
        person = person_by_id.get(todo.get("assigneeId") or "")
        mark = PRIORITY_MARK.get(todo.get("priority", "normal"), "")
        prefix = f"{entry['emoji']} " if entry else "📥 "
        suffix = f" ({person['name']})" if person else ""
        summary = f"{prefix}{mark}{todo['title']}{suffix}".strip()

        description = []
        if entry:
            description.append(f"Liste: {entry['name']}")
        if person:
            description.append(f"Zuständig: {person['name']}")
        if todo.get("note"):
            description.append(todo["note"])
        if todo.get("status") == "inbox":
            description.append("Noch nicht bestätigt.")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{todo['id']}@familie-todos",
            f"DTSTAMP:{stamp}",
            f"DTSTART;VALUE=DATE:{due.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(due + dt.timedelta(days=1)).strftime('%Y%m%d')}",
            _fold(f"SUMMARY:{_escape(summary)}"),
            "TRANSP:TRANSPARENT",
        ]
        if description:
            lines.append(_fold(f"DESCRIPTION:{_escape(' | '.join(description))}"))
        if todo.get("priority") == "high":
            lines.append("PRIORITY:1")
        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
